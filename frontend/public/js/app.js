/**
 * CodeAtlas frontend entry point: upload flow, navigation between views, session restore.
 * Views are plain modules that render into their <section data-view>. Nothing redraws on
 * its own: each state change calls the matching render function explicitly.
 */
import { deleteProject, getConfig, getHealth, getProject, getTree } from "./api.js";
import { TreeModel } from "./components/treeModel.js";
import { $, $$, h } from "./utils/dom.js";
import { formatNumber, minutesUntil } from "./utils/format.js";
import { hydrateIcons, icon } from "./utils/icons.js";
import { createArchitectureView } from "./views/architecture.js";
import { createExplorer } from "./views/explorer.js";
import { renderOverview } from "./views/overview.js";
import { renderPlanned } from "./views/planned.js";
import { createUploadController } from "./views/upload.js";

const SESSION_KEY = "codeatlas.projectId";

const state = {
  details: null,
  model: null,
  view: "upload",
};

const els = {
  nav: $$("[data-nav]"),
  views: Object.fromEntries($$("[data-view]").map((el) => [el.dataset.view, el])),
  headerEyebrow: $("#header-eyebrow"),
  headerTitle: $("#header-title"),
  headerActions: $("#header-actions"),
  headerExpiry: $("#header-expiry"),
  serverStatus: $("#server-status"),
  serverDot: $("#server-status-dot"),
  toasts: $("#toast-region"),
};

const explorer = createExplorer({ onError: (error) => toast(error.message, "error"), onNotice: (message) => toast(message) });
els.views.explorer.append(explorer.element);

const architecture = createArchitectureView({
  onReveal: (nodeId) => {
    showView("explorer");
    explorer.reveal(nodeId);
  },
  onError: (error) => toast(error.message, "error"),
});
els.views.architecture.append(architecture.element);

const uploader = createUploadController({
  onCompleted: async (details) => {
    await openProject(details);
    showView("overview");
    toast(`Analyzed ${formatNumber(details.stats.totalFiles)} files in ${details.project.name}`);
  },
});

/* ---------- Navigation ---------- */

function showView(view) {
  state.view = view;
  const section = view.startsWith("planned-") ? "planned" : view;
  for (const [name, el] of Object.entries(els.views)) el.hidden = name !== section;
  for (const button of els.nav) {
    if (button.dataset.nav === view) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  if (section === "planned") {
    renderPlanned(els.views.planned, view);
  }
  if (view === "architecture") architecture.show();
  renderHeader();
}

function renderHeader() {
  const project = state.details?.project;
  const titles = { upload: "Analyze a project", overview: "Overview", explorer: "File Explorer", architecture: "Architecture Map" };
  if (project) {
    els.headerEyebrow.textContent = project.name;
    els.headerActions.hidden = false;
    const minutes = minutesUntil(project.expiresAt);
    els.headerExpiry.textContent = `Results kept ${minutes} more min`;
    els.headerExpiry.title = "Analysis results live only in server memory and expire automatically.";
  } else {
    els.headerEyebrow.textContent = "No project loaded";
    els.headerActions.hidden = true;
  }
  const title = titles[state.view] ?? $("h2", els.views.planned)?.textContent ?? "CodeAtlas";
  els.headerTitle.textContent = title;
  document.title = [title, project?.name, "CodeAtlas"].filter(Boolean).join(" · ");
}

for (const button of els.nav) {
  button.addEventListener("click", () => {
    if (!button.disabled) showView(button.dataset.nav);
  });
}

function setProjectNavEnabled(enabled) {
  for (const button of els.nav) {
    if (["overview", "explorer", "architecture"].includes(button.dataset.nav)) button.disabled = !enabled;
  }
}

/* ---------- Toasts ---------- */

function toast(message, tone = "info") {
  const el = h(
    "div",
    {
      class: `pointer-events-auto flex items-start gap-2 rounded-xl border px-4 py-3 text-sm shadow-xl shadow-black/40 ${
        tone === "error" ? "border-danger/40 bg-[#1d1215] text-ink" : "border-line-strong bg-raised text-ink"
      }`,
      role: tone === "error" ? "alert" : "status",
    },
    icon(tone === "error" ? "alert" : "info", `mt-0.5 size-4 ${tone === "error" ? "text-danger" : "text-accent"}`),
    h("span", {}, message),
  );
  els.toasts.append(el);
  setTimeout(() => el.remove(), 5000);
}

// Dropping a file outside the dropzone must not navigate the page away to the file.
window.addEventListener("dragover", (event) => event.preventDefault());
window.addEventListener("drop", (event) => event.preventDefault());

/* ---------- Project lifecycle ---------- */

async function openProject(details) {
  const slice = await getTree(details.project.id, { depth: 2 });
  const model = new TreeModel(slice);
  const top = model.children.get(model.rootId) ?? [];
  if (top.length === 1 && model.canExpand(top[0])) model.expand(top[0]);

  state.details = details;
  state.model = model;
  try {
    sessionStorage.setItem(SESSION_KEY, details.project.id);
  } catch {
    /* storage unavailable: the session simply will not be restored */
  }
  setProjectNavEnabled(true);
  renderOverview(els.views.overview, {
    details,
    model,
    onReveal: (nodeId) => {
      showView("explorer");
      explorer.reveal(nodeId);
    },
  });
  explorer.load(details, model);
  architecture.load(details.project.id);
}

function closeProject() {
  state.details = null;
  state.model = null;
  try {
    sessionStorage.removeItem(SESSION_KEY);
  } catch {
    /* ignore */
  }
  setProjectNavEnabled(false);
  els.views.overview.replaceChildren();
  architecture.reset();
  showView("upload");
}

$("#new-analysis").addEventListener("click", () => {
  uploader.clearError();
  showView("upload");
});

$("#discard-project").addEventListener("click", async () => {
  const id = state.details?.project.id;
  if (!id) return;
  try {
    await deleteProject(id);
    toast("Analysis deleted from the server.");
  } catch (error) {
    if (error.status !== 404) {
      toast(error.message, "error");
      return;
    }
  }
  closeProject();
});

async function restoreSession() {
  let id = null;
  try {
    id = sessionStorage.getItem(SESSION_KEY);
  } catch {
    return;
  }
  if (!id) return;
  try {
    await openProject(await getProject(id));
    showView("overview");
  } catch (error) {
    try {
      sessionStorage.removeItem(SESSION_KEY);
    } catch {
      /* ignore */
    }
    if (error.code === "project_not_found") toast("The previous analysis has expired. Upload the archive again.");
  }
}

/* ---------- Boot ---------- */

async function loadServerInfo() {
  try {
    const [health, config] = await Promise.all([getHealth(), getConfig()]);
    uploader.setConfig(config);
    els.serverStatus.textContent = `Server online · v${health.version}`;
    els.serverDot.className = "size-2 rounded-full bg-ok";
  } catch {
    els.serverStatus.textContent = "Server unreachable";
    els.serverDot.className = "size-2 rounded-full bg-danger";
    uploader.setOffline();
  }
}

hydrateIcons();
showView("upload");
setInterval(renderHeader, 60_000);
await loadServerInfo();
// A job still running from before a reload takes priority over the last finished project.
if (!uploader.resume()) await restoreSession();
