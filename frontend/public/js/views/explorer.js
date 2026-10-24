/**
 * File explorer: filter bar + virtualised tree + details panel.
 *
 * Two tree models take turns in the same view. The full model loads lazily from
 * /tree. The filtered model is rebuilt from /search on every query and holds only the
 * matches and their ancestors. Expansion state of the full tree survives searching.
 */
import { getTree, searchProject } from "../api.js";
import { createDetailsPanel } from "../components/detailsPanel.js";
import { createFileTree } from "../components/fileTree.js";
import { createFilterBar } from "../components/filterBar.js";
import { TreeModel } from "../components/treeModel.js";
import { h } from "../utils/dom.js";
import { formatNumber, pluralize } from "../utils/format.js";
import { icon } from "../utils/icons.js";

const EXPAND_ALL_NODE_LIMIT = 5000;
const LARGE_PROJECT_EXPAND_DEPTH = 3;
const FULL_DEPTH = 1024;
const SEARCH_LIMIT = 500;

export function createExplorer({ onError, onNotice }) {
  let projectId = null;
  let details = null;
  let fullModel = null;
  let filteredModel = null;
  let searchAbort = null;
  let searchSeq = 0;

  const status = h("p", { class: "min-w-0 flex-1 truncate text-xs text-subtle", "aria-live": "polite", id: "tree-status" });
  const filterBar = createFilterBar({ onChange: runSearch });
  const detailsPanel = createDetailsPanel({
    onSelectParent: (id) => tree.select(id),
    onShowInTree: (id) => reveal(id),
    onCopied: onNotice,
  });
  const tree = createFileTree({
    label: "Project files",
    onSelect: (node) => showDetails(node),
    loadChildren: (id) => getTree(projectId, { nodeId: id, depth: 1 }),
    onError,
  });

  const emptyState = h(
    "div",
    { class: "flex flex-1 flex-col items-center justify-center p-8 text-center", hidden: true, id: "tree-empty" },
    icon("search", "size-6 text-subtle"),
    h("p", { class: "mt-3 text-sm text-muted", id: "tree-empty-text" }, "No matches"),
    h("button", { type: "button", class: "btn btn-ghost mt-3", onclick: () => clearFilters() }, "Clear filters"),
  );
  const expandButton = h("button", { type: "button", class: "btn btn-ghost px-2", title: "Expand all", "aria-label": "Expand all", onclick: () => expandAll() }, icon("expand", "size-4"));
  const collapseButton = h("button", { type: "button", class: "btn btn-ghost px-2", title: "Collapse all", "aria-label": "Collapse all", onclick: () => collapseAll() }, icon("collapse", "size-4"));

  const element = h(
    "div",
    { class: "grid min-h-0 w-full flex-1 gap-4 lg:grid-cols-[minmax(0,1fr)_23rem]" },
    h(
      "section",
      // No overflow-hidden on the card itself, so the extension dropdown can extend past it.
      { class: "card flex h-[70vh] min-h-0 min-w-0 flex-col lg:h-[calc(100vh-7.5rem)]", "aria-label": "Project tree" },
      h("div", { class: "relative z-10 border-b border-line p-3" }, filterBar.element),
      h("div", { class: "flex items-center gap-2 border-b border-line px-3 py-1.5" }, status, expandButton, collapseButton),
      h("div", { class: "flex min-h-0 flex-1 flex-col overflow-hidden rounded-b-xl" }, tree.element, emptyState),
    ),
    h("aside", { class: "card min-h-[18rem] overflow-hidden lg:h-[calc(100vh-7.5rem)]", "aria-label": "Selection details" }, detailsPanel.element),
  );

  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && !element.closest("[hidden]") && !["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement?.tagName)) {
      event.preventDefault();
      filterBar.focusSearch();
    }
  });

  function load(nextDetails, model) {
    details = nextDetails;
    projectId = nextDetails.project.id;
    fullModel = model;
    filteredModel = null;
    filterBar.setExtensions(nextDetails.stats.extensions);
    filterBar.reset();
    tree.clearSelection();
    showFullTree();
    tree.scrollToTop();
    detailsPanel.showEmpty();
  }

  function activeModel() {
    return filteredModel ?? fullModel;
  }

  function showDetails(node) {
    const model = activeModel();
    detailsPanel.show(node, {
      isRoot: node.id === model.rootId,
      filtered: Boolean(filteredModel),
      parent: node.parentId ? model.get(node.parentId) : null,
    });
  }

  function showFullTree() {
    filteredModel = null;
    tree.element.hidden = false;
    emptyState.hidden = true;
    tree.setModel(fullModel);
    const stats = details.stats;
    const excluded = stats.excludedFileCount + stats.excludedDirectoryCount;
    status.textContent = `Full tree · ${pluralize(stats.totalFiles, "file")} in ${pluralize(stats.totalDirectories, "folder")}${
      excluded ? ` · ${formatNumber(excluded)} excluded` : ""
    }`;
  }

  async function runSearch(filters) {
    searchAbort?.abort();
    if (!filters.active) {
      showFullTree();
      if (tree.selectedId && fullModel.get(tree.selectedId)) tree.select(tree.selectedId);
      return;
    }
    const seq = ++searchSeq;
    searchAbort = new AbortController();
    status.textContent = "Searching…";
    try {
      const result = await searchProject(projectId, {
        q: filters.q,
        type: filters.type,
        classifications: filters.classification ? [filters.classification] : [],
        extensions: filters.extensions,
        limit: SEARCH_LIMIT,
        signal: searchAbort.signal,
      });
      if (seq !== searchSeq) return;
      filteredModel = new TreeModel(result, { lazy: false });
      filteredModel.expandLoaded();
      const empty = result.totalMatches === 0;
      tree.element.hidden = empty;
      emptyState.hidden = !empty;
      emptyState.querySelector("#tree-empty-text").textContent = filters.q
        ? `No files or folders match “${filters.q}” with the current filters.`
        : "Nothing matches the current filters.";
      tree.setModel(filteredModel, { matches: result.matchIds });
      tree.scrollToTop();
      status.textContent = result.truncated
        ? `Showing the first ${formatNumber(result.matchIds.length)} of ${formatNumber(result.totalMatches)} matches. Refine the search to see the rest.`
        : pluralize(result.totalMatches, "match", "matches");
      if (result.matchIds.length) tree.select(result.matchIds[0], { scroll: false });
    } catch (error) {
      if (error.name === "AbortError") return;
      status.textContent = "Search failed";
      onError(error);
    }
  }

  function clearFilters() {
    filterBar.reset();
    showFullTree();
  }

  /** Show a node in the full tree, loading its ancestors' children first. */
  async function reveal(nodeId) {
    if (filteredModel) clearFilters();
    try {
      const slice = await getTree(projectId, { nodeId, depth: 1, reveal: true });
      fullModel.ingest(slice);
      fullModel.expandAncestors(nodeId);
      tree.setModel(fullModel);
      tree.select(nodeId);
      tree.element.focus({ preventScroll: true });
    } catch (error) {
      onError(error);
    }
  }

  async function expandAll() {
    const model = activeModel();
    if (filteredModel) {
      model.expandLoaded();
      tree.refresh();
      return;
    }
    const small = details.project.nodeCount <= EXPAND_ALL_NODE_LIMIT;
    expandButton.disabled = true;
    try {
      const slice = await getTree(projectId, { depth: small ? FULL_DEPTH : LARGE_PROJECT_EXPAND_DEPTH });
      model.ingest(slice);
      model.expandLoaded(small ? Infinity : LARGE_PROJECT_EXPAND_DEPTH);
      tree.refresh();
      if (!small) onNotice(`Large project: expanded the first ${LARGE_PROJECT_EXPAND_DEPTH} levels. Open deeper folders individually.`);
    } catch (error) {
      onError(error);
    } finally {
      expandButton.disabled = false;
    }
  }

  function collapseAll() {
    activeModel().collapseAll();
    tree.refresh();
    tree.scrollToTop();
  }

  return { element, load, reveal, focusTree: () => tree.element.focus() };
}
