/**
 * Backend client. Every call goes to the real CodeAtlas API; there is no mock data.
 * The base URL comes from <meta name="codeatlas-api-base"> (empty means same origin), so the
 * static frontend can be deployed separately from the API.
 */

const API_BASE = (document.querySelector('meta[name="codeatlas-api-base"]')?.content ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, { status = 0, code = "network_error", details = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function errorFromBody(status, body) {
  const error = body?.error;
  if (error?.message) return new ApiError(error.message, { status, code: error.code, details: error.details });
  if (status === 0) return new ApiError("Could not reach the CodeAtlas server. Is it running?");
  return new ApiError(`The server returned an unexpected response (HTTP ${status}).`, { status, code: "http_error" });
}

async function request(path, { method = "GET", params, signal } = {}) {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === undefined || value === null || value === "") continue;
    for (const item of Array.isArray(value) ? value : [value]) url.searchParams.append(key, String(item));
  }
  let response;
  try {
    response = await fetch(url, { method, signal, headers: { Accept: "application/json" } });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError("Could not reach the CodeAtlas server. Is it running?");
  }
  if (response.status === 204) return null;
  const body = await response.json().catch(() => null);
  if (!response.ok) throw errorFromBody(response.status, body);
  return body;
}

export const getHealth = (options) => request("/api/health", options);
export const getConfig = (options) => request("/api/config", options);
export const getProject = (id, options) => request(`/api/projects/${encodeURIComponent(id)}`, options);
export const deleteProject = (id) => request(`/api/projects/${encodeURIComponent(id)}`, { method: "DELETE" });

export function getTree(id, { nodeId, depth = 1, reveal = false, signal } = {}) {
  return request(`/api/projects/${encodeURIComponent(id)}/tree`, {
    params: { nodeId, depth, reveal: reveal ? "true" : undefined },
    signal,
  });
}

export function searchProject(id, { q, extensions = [], classifications = [], type = "all", limit = 500, signal } = {}) {
  return request(`/api/projects/${encodeURIComponent(id)}/search`, {
    params: { q, extension: extensions, classification: classifications, type, limit },
    signal,
  });
}

export const getJob = (id, options) => request(`/api/jobs/${encodeURIComponent(id)}`, options);
export const cancelJob = (id) => request(`/api/jobs/${encodeURIComponent(id)}`, { method: "DELETE" });

/**
 * Upload a ZIP with XMLHttpRequest, because fetch cannot report upload progress.
 * The progress callback receives real byte counts. Resolves with the analysis job
 * (`{ job }`), which the caller then polls with getJob().
 */
export function uploadArchive(
  file,
  { applyDefaultExclusions = true, respectGitignore = true, excludePatterns = "", includePatterns = "", onUploadProgress, onUploaded } = {},
) {
  const xhr = new XMLHttpRequest();
  const promise = new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file, file.name);
    form.append("applyDefaultExclusions", applyDefaultExclusions ? "true" : "false");
    form.append("respectGitignore", respectGitignore ? "true" : "false");
    form.append("excludePatterns", excludePatterns);
    form.append("includePatterns", includePatterns);

    xhr.open("POST", `${API_BASE}/api/projects/analyze`);
    xhr.responseType = "json";
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) onUploadProgress?.(event.loaded, event.total);
    });
    xhr.upload.addEventListener("load", () => onUploaded?.());
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response);
      else reject(errorFromBody(xhr.status, xhr.response));
    });
    xhr.addEventListener("error", () => reject(errorFromBody(0, null)));
    xhr.addEventListener("abort", () => reject(new ApiError("Upload cancelled.", { code: "cancelled" })));
    xhr.send(form);
  });
  return { promise, cancel: () => xhr.abort() };
}
