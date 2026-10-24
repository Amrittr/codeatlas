/**
 * Virtualised, keyboard-accessible tree view over a TreeModel.
 *
 * Only the rows inside the viewport (plus overscan) exist in the DOM, so a tree with
 * tens of thousands of visible rows still renders a few dozen elements. Rows are
 * rebuilt on scroll and resize in a requestAnimationFrame callback.
 */
import { classificationInfo } from "../labels.js";
import { h } from "../utils/dom.js";
import { formatBytes, pluralize } from "../utils/format.js";
import { icon } from "../utils/icons.js";

const ROW_HEIGHT = 28;
const INDENT = 16;
const OVERSCAN = 10;

const domId = (nodeId) => `tree-row-${nodeId}`;

export function createFileTree({ label, onSelect, loadChildren, onError }) {
  const viewport = h("div", {
    class: "tree-viewport h-full min-h-0 py-1",
    role: "tree",
    "aria-label": label,
    tabindex: "0",
  });
  const spacer = h("div", { class: "relative w-full" });
  viewport.append(spacer);

  let model = null;
  let rows = [];
  let matchIds = new Set();
  let selectedId = null;
  let activeIndex = 0;
  let frame = 0;
  const loading = new Set();

  function setModel(nextModel, { matches = [] } = {}) {
    model = nextModel;
    matchIds = new Set(matches);
    refresh();
  }

  function refresh() {
    rows = model ? model.visibleRows() : [];
    spacer.style.height = `${rows.length * ROW_HEIGHT}px`;
    const selectedIndex = rows.findIndex((row) => row.id === selectedId);
    if (selectedIndex >= 0) activeIndex = selectedIndex;
    activeIndex = Math.min(Math.max(activeIndex, 0), Math.max(rows.length - 1, 0));
    scheduleRender();
  }

  function scheduleRender() {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(render);
  }

  function render() {
    const first = Math.max(0, Math.floor(viewport.scrollTop / ROW_HEIGHT) - OVERSCAN);
    const last = Math.min(rows.length, Math.ceil((viewport.scrollTop + viewport.clientHeight) / ROW_HEIGHT) + OVERSCAN);
    const fragment = document.createDocumentFragment();
    for (let index = first; index < last; index += 1) fragment.append(renderRow(rows[index], index));
    spacer.replaceChildren(fragment);
    const active = rows[activeIndex];
    if (active && activeIndex >= first && activeIndex < last) viewport.setAttribute("aria-activedescendant", domId(active.id));
    else viewport.removeAttribute("aria-activedescendant");
  }

  function renderRow(row, index) {
    const node = model.get(row.id);
    const isDirectory = node.type === "directory";
    const expandable = model.canExpand(node.id);
    const expanded = model.isExpanded(node.id);
    const classes = ["tree-row"];
    if (index === activeIndex) classes.push("is-active");
    if (matchIds.has(node.id)) classes.push("is-match");
    if (node.excluded) classes.push("is-excluded");

    let toggle;
    if (loading.has(node.id)) toggle = h("span", { class: "tree-toggle" }, h("span", { class: "spinner size-3" }));
    else if (expandable) toggle = h("span", { class: "tree-toggle", "data-toggle": "" }, icon(expanded ? "chevron-down" : "chevron-right", "size-3.5"));
    else toggle = h("span", { class: "tree-toggle pointer-events-none" });

    const nodeIcon = isDirectory
      ? icon(node.excluded ? "ban" : expanded ? "folder-open" : "folder", `size-4 ${node.excluded ? "text-subtle" : "text-accent"}`)
      : icon(classificationInfo(node.classification).icon, `size-4 ${node.excluded ? "text-subtle" : classificationInfo(node.classification).text}`);

    const meta = isDirectory
      ? node.excluded
        ? "excluded"
        : node.id === model.rootId || node.descendantFileCount
          ? pluralize(node.descendantFileCount, "file")
          : node.childCount === 0
            ? "empty"
            : ""
      : node.excluded
        ? "excluded"
        : formatBytes(node.sizeBytes);

    return h(
      "div",
      {
        id: domId(node.id),
        class: classes.join(" "),
        role: "treeitem",
        "aria-level": row.level,
        "aria-setsize": row.size,
        "aria-posinset": row.pos,
        "aria-selected": String(node.id === selectedId),
        "aria-expanded": isDirectory && expandable ? String(expanded) : undefined,
        "aria-label": node.name || "project root",
        title: node.excludedRule ? `${node.path} (excluded: ${node.excludedRule})` : node.path || node.name,
        dataset: { index: String(index), id: node.id },
        style: { top: `${index * ROW_HEIGHT}px`, paddingLeft: `${6 + (row.level - 1) * INDENT}px` },
      },
      toggle,
      nodeIcon,
      h("span", { class: `tree-name min-w-0 flex-1 truncate ${node.id === model.rootId ? "font-semibold text-ink" : ""}` }, node.name),
      node.hidden && !isDirectory ? h("span", { class: "chip hidden sm:inline-flex" }, "hidden") : null,
      node.generated
        ? h("span", { class: "chip text-cls-generated", title: `Likely generated (${node.generatedConfidence} confidence): ${node.generatedReason}` }, "generated")
        : null,
      h("span", { class: "shrink-0 font-mono text-[11px] text-subtle tabular-nums" }, meta),
    );
  }

  async function toggle(id) {
    if (!model?.canExpand(id)) return;
    if (model.isExpanded(id)) {
      model.collapse(id);
      refresh();
      return;
    }
    if (model.needsChildren(id)) {
      loading.add(id);
      refresh();
      try {
        model.ingest(await loadChildren(id));
      } catch (error) {
        onError?.(error);
        return;
      } finally {
        loading.delete(id);
      }
    }
    model.expand(id);
    refresh();
  }

  function select(id, { scroll = true, notify = true } = {}) {
    if (!model?.get(id)) return;
    selectedId = id;
    const index = rows.findIndex((row) => row.id === id);
    if (index >= 0) {
      activeIndex = index;
      if (scroll) ensureVisible(index);
    }
    scheduleRender();
    if (notify) onSelect?.(model.get(id));
  }

  function ensureVisible(index) {
    const top = index * ROW_HEIGHT;
    if (top < viewport.scrollTop) viewport.scrollTop = top;
    else if (top + ROW_HEIGHT > viewport.scrollTop + viewport.clientHeight) {
      viewport.scrollTop = top + ROW_HEIGHT - viewport.clientHeight;
    }
  }

  function moveTo(index) {
    if (!rows.length) return;
    select(rows[Math.min(Math.max(index, 0), rows.length - 1)].id);
  }

  viewport.addEventListener("scroll", scheduleRender, { passive: true });
  new ResizeObserver(scheduleRender).observe(viewport);

  // Rows are re-created between clicks, so double-click is detected by hand rather than via
  // the dblclick event, which may target a detached element.
  let lastClick = { id: null, time: 0 };
  spacer.addEventListener("click", (event) => {
    const rowEl = event.target.closest(".tree-row");
    if (!rowEl) return;
    const id = rowEl.dataset.id;
    const now = performance.now();
    const isDoubleClick = lastClick.id === id && now - lastClick.time < 400;
    lastClick = { id, time: isDoubleClick ? 0 : now };
    if (event.target.closest("[data-toggle]")) toggle(id);
    else {
      select(id, { scroll: false });
      if (isDoubleClick && model.isDirectory(id)) toggle(id);
    }
    viewport.focus({ preventScroll: true });
  });

  viewport.addEventListener("keydown", (event) => {
    if (!rows.length) return;
    const row = rows[activeIndex];
    const id = row?.id;
    const pageSize = Math.max(1, Math.floor(viewport.clientHeight / ROW_HEIGHT) - 1);
    const handlers = {
      ArrowDown: () => moveTo(activeIndex + 1),
      ArrowUp: () => moveTo(activeIndex - 1),
      PageDown: () => moveTo(activeIndex + pageSize),
      PageUp: () => moveTo(activeIndex - pageSize),
      Home: () => moveTo(0),
      End: () => moveTo(rows.length - 1),
      ArrowRight: () => {
        if (model.canExpand(id) && !model.isExpanded(id)) toggle(id);
        else if (model.isExpanded(id)) moveTo(activeIndex + 1);
      },
      ArrowLeft: () => {
        if (model.isExpanded(id) && id !== model.rootId) toggle(id);
        else {
          const parentIndex = rows.findIndex((item) => item.id === model.get(id)?.parentId);
          if (parentIndex >= 0) moveTo(parentIndex);
        }
      },
      Enter: () => (model.canExpand(id) ? toggle(id) : select(id)),
      " ": () => (model.canExpand(id) ? toggle(id) : select(id)),
    };
    const handler = handlers[event.key];
    if (!handler) return;
    event.preventDefault();
    handler();
  });

  return {
    element: viewport,
    setModel,
    refresh,
    select,
    toggle,
    get selectedId() {
      return selectedId;
    },
    clearSelection() {
      selectedId = null;
      scheduleRender();
    },
    scrollToTop() {
      viewport.scrollTop = 0;
    },
  };
}
