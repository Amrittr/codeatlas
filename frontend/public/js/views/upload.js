/**
 * Upload page controller: analysis options, the upload itself, and tracking the background
 * analysis job until it finishes. A job in progress survives a page reload (its id is kept
 * in sessionStorage). The chosen options are remembered per browser in localStorage.
 */
import { ApiError, cancelJob, getJob, getProject, uploadArchive } from "../api.js";
import { $ } from "../utils/dom.js";
import { formatBytes, formatNumber } from "../utils/format.js";

const JOB_KEY = "codeatlas.jobId";
const OPTIONS_KEY = "codeatlas.analysisOptions";
const POLL_INTERVAL_MS = 400;

const PHASES = {
  queued: "Waiting for a free analysis slot",
  inspecting: "Checking the archive structure",
  planning: "Validating entries and applying exclusion rules",
  extracting: "Extracting files safely",
  scanning: "Scanning the folder structure",
  indexing: "Computing statistics",
  done: "Finishing",
};

const ERROR_TITLES = {
  unsupported_file_type: "Not a ZIP archive",
  invalid_archive: "Invalid or corrupted archive",
  unsafe_archive: "Archive rejected for safety",
  upload_too_large: "Archive too large",
  archive_uncompressed_too_large: "Archive expands too much",
  suspected_decompression_bomb: "Archive rejected for safety",
  too_many_files: "Too many files",
  too_many_entries: "Too many archive entries",
  too_many_directories: "Too many folders",
  archive_too_deep: "Folders nested too deeply",
  analysis_timeout: "Analysis timed out",
  invalid_patterns: "Invalid custom rules",
  server_busy: "Server busy",
  cancelled: "Analysis cancelled",
  job_not_found: "Analysis no longer available",
  network_error: "Server unreachable",
};

const storage = {
  get(area, key) {
    try {
      return window[area].getItem(key);
    } catch {
      return null;
    }
  },
  set(area, key, value) {
    try {
      if (value === null) window[area].removeItem(key);
      else window[area].setItem(key, value);
    } catch {
      /* storage unavailable: this convenience is simply skipped */
    }
  },
};

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function patternLines(text) {
  return text.split("\n").map((line) => line.trim()).filter((line) => line && !line.startsWith("#"));
}

export function createUploadController({ onCompleted }) {
  const els = {
    dropzone: $("#dropzone"),
    fileInput: $("#file-input"),
    options: $("#analysis-options"),
    applyExclusions: $("#apply-exclusions"),
    respectGitignore: $("#respect-gitignore"),
    excludePatterns: $("#exclude-patterns"),
    includePatterns: $("#include-patterns"),
    customRules: $("#custom-rules"),
    customRulesCount: $("#custom-rules-count"),
    exclusionNames: $("#exclusion-names"),
    limitsHint: $("#limits-hint"),
    progress: $("#upload-progress"),
    progressLabel: $("#progress-label"),
    progressDetail: $("#progress-detail"),
    progressMeter: $("#progress-meter"),
    progressBar: $("#progress-bar"),
    cancel: $("#cancel-upload"),
    error: $("#upload-error"),
    errorTitle: $("#upload-error-title"),
    errorMessage: $("#upload-error-message"),
  };

  let config = null;
  let upload = null; // XHR handle while bytes are being sent
  let jobId = null; // job being tracked
  let trackingToken = 0;

  /* ----- options ----- */

  function readOptions() {
    return {
      applyDefaultExclusions: els.applyExclusions.checked,
      respectGitignore: els.respectGitignore.checked,
      excludePatterns: els.excludePatterns.value,
      includePatterns: els.includePatterns.value,
    };
  }

  function restoreOptions() {
    let saved = null;
    try {
      saved = JSON.parse(storage.get("localStorage", OPTIONS_KEY) ?? "null");
    } catch {
      saved = null;
    }
    if (!saved) return;
    els.applyExclusions.checked = saved.applyDefaultExclusions !== false;
    els.respectGitignore.checked = saved.respectGitignore !== false;
    els.excludePatterns.value = typeof saved.excludePatterns === "string" ? saved.excludePatterns : "";
    els.includePatterns.value = typeof saved.includePatterns === "string" ? saved.includePatterns : "";
    if (els.excludePatterns.value || els.includePatterns.value) els.customRules.open = true;
  }

  function onOptionsChanged() {
    storage.set("localStorage", OPTIONS_KEY, JSON.stringify(readOptions()));
    const count = patternLines(els.excludePatterns.value).length + patternLines(els.includePatterns.value).length;
    els.customRulesCount.hidden = count === 0;
    els.customRulesCount.textContent = String(count);
  }

  for (const input of [els.applyExclusions, els.respectGitignore, els.excludePatterns, els.includePatterns]) {
    input.addEventListener("input", onOptionsChanged);
    input.addEventListener("change", onOptionsChanged);
  }

  /* ----- errors and progress ----- */

  function showError(error) {
    els.errorTitle.textContent = ERROR_TITLES[error.code] ?? "Analysis failed";
    els.errorMessage.textContent = error.message || "Something went wrong.";
    els.error.dataset.code = error.code ?? "";
    els.error.hidden = false;
  }

  function setBusy(active) {
    els.progress.hidden = !active;
    els.dropzone.classList.toggle("pointer-events-none", active);
    els.dropzone.classList.toggle("opacity-60", active);
    els.fileInput.disabled = active;
    els.options.disabled = active;
  }

  function showProgress(label, detail, fraction) {
    els.progressLabel.textContent = label;
    els.progressDetail.textContent = detail;
    els.progressMeter.hidden = fraction === null;
    if (fraction !== null) els.progressBar.style.width = `${Math.round(Math.min(1, Math.max(0, fraction)) * 100)}%`;
  }

  function showJobProgress(job) {
    const { phase, current, total, unit } = job.progress;
    const label = `${PHASES[phase] ?? "Analyzing"}…`;
    if (total) {
      showProgress(label, `${formatNumber(current)} of ${formatNumber(total)} ${unit ?? ""}`.trim(), current / total);
    } else {
      // No total known for this phase: show no percentage rather than invent one.
      showProgress(label, job.fileName, null);
    }
    els.progress.dataset.phase = phase;
  }

  /* ----- validation ----- */

  function validate(file) {
    const fail = (code, message) => new ApiError(message, { code });
    if (!file) return fail("unsupported_file_type", "No file was selected.");
    if (!/\.zip$/i.test(file.name)) return fail("unsupported_file_type", "Choose a .zip archive. Other archive formats are not supported yet.");
    if (file.size === 0) return fail("invalid_archive", "The file is empty.");
    const max = config?.limits.maxUploadBytes;
    if (max && file.size > max) {
      return fail("upload_too_large", `The file is ${formatBytes(file.size)}; the server accepts archives up to ${formatBytes(max)}.`);
    }
    const maxPatterns = config?.patternLimits?.maxPatterns ?? 100;
    for (const [label, text] of [["Also exclude", els.excludePatterns.value], ["Always include", els.includePatterns.value]]) {
      if (patternLines(text).length > maxPatterns) return fail("invalid_patterns", `${label}: at most ${maxPatterns} patterns are allowed.`);
    }
    return null;
  }

  /* ----- upload and job tracking ----- */

  async function start(file) {
    els.error.hidden = true;
    const problem = validate(file);
    if (problem) {
      showError(problem);
      return;
    }
    setBusy(true);
    showProgress(`Uploading ${file.name}`, formatBytes(file.size), 0);
    upload = uploadArchive(file, {
      ...readOptions(),
      onUploadProgress: (loaded, total) => {
        showProgress(`Uploading ${file.name}`, `${Math.round((loaded / total) * 100)}% · ${formatBytes(loaded)} of ${formatBytes(total)}`, loaded / total);
      },
      onUploaded: () => showProgress("Upload complete. Starting analysis…", file.name, null),
    });
    try {
      const { job } = await upload.promise;
      upload = null;
      await track(job.id);
    } catch (error) {
      upload = null;
      setBusy(false);
      showError(error);
    } finally {
      els.fileInput.value = "";
    }
  }

  async function track(id) {
    jobId = id;
    const token = ++trackingToken;
    storage.set("sessionStorage", JOB_KEY, id);
    setBusy(true);
    try {
      for (;;) {
        const { job } = await getJob(id);
        if (token !== trackingToken) return;
        if (job.status === "completed") {
          showProgress("Loading results…", job.fileName, 1);
          const details = await getProject(job.projectId);
          finish();
          await onCompleted(details);
          return;
        }
        if (job.status === "failed") {
          finish();
          showError(new ApiError(job.error.message, { code: job.error.code, status: job.error.statusCode }));
          return;
        }
        if (job.status === "cancelled") {
          finish();
          showError(new ApiError("The analysis was cancelled. Its uploaded files have been deleted.", { code: "cancelled" }));
          return;
        }
        showJobProgress(job);
        await sleep(POLL_INTERVAL_MS);
      }
    } catch (error) {
      if (token !== trackingToken) return;
      finish();
      showError(error);
    }
  }

  function finish() {
    jobId = null;
    trackingToken += 1;
    storage.set("sessionStorage", JOB_KEY, null);
    setBusy(false);
  }

  els.cancel.addEventListener("click", async () => {
    if (upload) {
      upload.cancel();
      return;
    }
    if (!jobId) return;
    els.cancel.disabled = true;
    showProgress("Cancelling…", "Stopping at the next safe point", null);
    try {
      await cancelJob(jobId);
    } catch (error) {
      showError(error);
    } finally {
      els.cancel.disabled = false;
    }
  });

  els.fileInput.addEventListener("change", () => start(els.fileInput.files[0]));
  els.dropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    els.dropzone.classList.add("is-dragging");
  });
  els.dropzone.addEventListener("dragleave", (event) => {
    if (!els.dropzone.contains(event.relatedTarget)) els.dropzone.classList.remove("is-dragging");
  });
  els.dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    els.dropzone.classList.remove("is-dragging");
    const files = event.dataTransfer?.files;
    if (files?.length > 1) {
      showError(new ApiError("Drop a single .zip archive.", { code: "unsupported_file_type" }));
      return;
    }
    if (files?.length === 1) start(files[0]);
  });

  restoreOptions();
  onOptionsChanged();

  return {
    setConfig(nextConfig) {
      config = nextConfig;
      const { limits } = config;
      els.limitsHint.textContent = `ZIP up to ${formatBytes(limits.maxUploadBytes)} · ${formatNumber(limits.maxFiles)} analyzed files · ${formatBytes(limits.maxUncompressedBytes)} extracted`;
      els.exclusionNames.textContent = config.defaultExclusions.map((rule) => rule.name).join(", ");
    },
    setOffline() {
      els.limitsHint.textContent = "The CodeAtlas server is not reachable. Start it, then reload this page.";
    },
    /** Resume tracking a job that was running before a page reload. Returns true if one was found. */
    resume() {
      const id = storage.get("sessionStorage", JOB_KEY);
      if (!id) return false;
      track(id);
      return true;
    },
    clearError() {
      els.error.hidden = true;
    },
  };
}
