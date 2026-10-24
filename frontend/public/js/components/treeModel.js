/**
 * Client-side tree state: a cache of nodes received from the API plus expansion state.
 * Pure data, with no DOM access, so it can be unit-tested under Node.
 *
 * `lazy` models (the full tree) treat a directory as expandable when the server reports
 * children, even if they have not been fetched yet. Non-lazy models (search results) only
 * expand into the children they were given.
 */
export class TreeModel {
  constructor({ rootId, nodes = [], children = {} }, { lazy = true } = {}) {
    this.rootId = rootId;
    this.lazy = lazy;
    this.nodes = new Map();
    this.children = new Map();
    this.expanded = new Set([rootId]);
    this.ingest({ nodes, children });
  }

  ingest({ nodes = [], children = {} }) {
    for (const node of nodes) this.nodes.set(node.id, node);
    for (const [id, childIds] of Object.entries(children)) this.children.set(id, childIds);
  }

  get(id) {
    return this.nodes.get(id);
  }

  get size() {
    return this.nodes.size;
  }

  isDirectory(id) {
    return this.nodes.get(id)?.type === "directory";
  }

  hasLoadedChildren(id) {
    return this.children.has(id);
  }

  canExpand(id) {
    const node = this.nodes.get(id);
    if (!node || node.type !== "directory" || node.excluded) return false;
    if (this.children.has(id)) return this.children.get(id).length > 0;
    return this.lazy && node.childCount > 0;
  }

  needsChildren(id) {
    return this.lazy && this.canExpand(id) && !this.children.has(id);
  }

  isExpanded(id) {
    return this.expanded.has(id);
  }

  expand(id) {
    if (this.canExpand(id) && this.children.has(id)) this.expanded.add(id);
  }

  collapse(id) {
    if (id !== this.rootId) this.expanded.delete(id);
  }

  collapseAll() {
    this.expanded = new Set([this.rootId]);
  }

  /** Expand every loaded directory, optionally only down to `maxDepth` (node depth, root = 0). */
  expandLoaded(maxDepth = Infinity) {
    for (const [id, node] of this.nodes) {
      if (node.type === "directory" && node.depth < maxDepth && this.children.has(id) && this.canExpand(id)) {
        this.expanded.add(id);
      }
    }
  }

  ancestors(id) {
    const chain = [];
    let parent = this.nodes.get(id)?.parentId;
    while (parent) {
      chain.unshift(parent);
      parent = this.nodes.get(parent)?.parentId;
    }
    return chain;
  }

  expandAncestors(id) {
    for (const ancestor of this.ancestors(id)) this.expand(ancestor);
  }

  /**
   * Flatten the expanded tree into rows for rendering. The root is the first row (level 1).
   * Each row carries ARIA set position data because only a window of rows is in the DOM.
   */
  visibleRows() {
    const rows = [];
    if (!this.nodes.has(this.rootId)) return rows;
    const stack = [{ id: this.rootId, level: 1, pos: 1, size: 1 }];
    while (stack.length) {
      const row = stack.pop();
      rows.push(row);
      if (!this.expanded.has(row.id)) continue;
      const childIds = this.children.get(row.id) ?? [];
      for (let index = childIds.length - 1; index >= 0; index -= 1) {
        if (!this.nodes.has(childIds[index])) continue;
        stack.push({ id: childIds[index], level: row.level + 1, pos: index + 1, size: childIds.length });
      }
    }
    return rows;
  }
}
