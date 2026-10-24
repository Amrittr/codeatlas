/** Pages for features on the roadmap. They describe the plan and do not pretend to work. */
import { h, mount } from "../utils/dom.js";
import { icon } from "../utils/icons.js";

const PLANNED = {
  "planned-architecture": {
    title: "Architecture Map",
    icon: "network",
    phase: "Phase 7",
    summary: "An interactive map of the project's main components (frontend, backend, API routes, data access, authentication, background jobs), built from imports, framework conventions and configuration.",
    points: [
      "Components identified from evidence, not from folder names alone",
      "Uncertain classifications labelled as hypotheses",
      "Navigate from a module to its source files and dependencies",
    ],
  },
  "planned-dependencies": {
    title: "Dependency Graph",
    icon: "git-fork",
    phase: "Phase 6",
    summary: "A graph of import and export relationships between files and modules, rendered with Cytoscape.js. Every edge points back to the source line it came from.",
    points: [
      "Static, evidence-backed relationships only. Nothing is guessed from similar names",
      "Neighbourhood exploration and filtering for large graphs",
      "Dynamic behaviour that static analysis cannot prove is marked as unknown",
    ],
  },
  "planned-assistant": {
    title: "Codebase Assistant",
    icon: "message",
    phase: "Phase 8",
    summary: "Ask questions such as “where is authentication implemented?” and get answers grounded in the indexed repository, with file paths and line references.",
    points: [
      "Retrieval over symbols, configuration and dependency records, never the whole repo",
      "Clear separation between direct evidence and interpretation",
      "Honest “not enough evidence” answers",
    ],
  },
  "planned-settings": {
    title: "Project Settings",
    icon: "settings",
    phase: "Phase 2 and later",
    summary: "Configurable exclusion rules, .gitignore support, scan limits and data-retention controls for each project.",
    points: ["Custom include and exclude rules", "Respect .gitignore where appropriate", "Explicit retention and deletion policies"],
  },
};

export function renderPlanned(container, key) {
  const page = PLANNED[key];
  mount(
    container,
    h(
      "div",
      { class: "card p-8" },
      h(
        "div",
        { class: "flex items-center gap-3" },
        h("div", { class: "flex size-11 items-center justify-center rounded-xl border border-line bg-raised text-subtle" }, icon(page.icon, "size-5")),
        h("div", {}, h("h2", { class: "text-xl font-semibold tracking-tight" }, page.title), h("p", { class: "text-xs text-subtle" }, `Not available yet · ${page.phase}`)),
        h("span", { class: "badge-planned ml-auto" }, "Planned"),
      ),
      h("p", { class: "mt-5 leading-relaxed text-muted" }, page.summary),
      h("ul", { class: "mt-5 flex flex-col gap-2" }, page.points.map((point) => h("li", { class: "flex gap-2 text-sm text-muted" }, h("span", { class: "mt-2 size-1.5 shrink-0 rounded-full bg-subtle" }), point))),
      h("p", { class: "mt-6 text-xs text-subtle" }, "This release covers secure ZIP analysis, project statistics and the file explorer. See docs/IMPLEMENTATION_PLAN.md for the roadmap."),
    ),
  );
  return page.title;
}
