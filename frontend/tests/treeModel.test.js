import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { TreeModel } from "../public/js/components/treeModel.js";

const dir = (id, parentId, depth, childCount, extra = {}) => ({ id, parentId, depth, type: "directory", name: id, childCount, ...extra });
const file = (id, parentId, depth) => ({ id, parentId, depth, type: "file", name: id });

function fullTree() {
  return new TreeModel({
    rootId: "root",
    nodes: [
      dir("root", null, 0, 3),
      dir("src", "root", 1, 2),
      dir("node_modules", "root", 1, 0, { excluded: true }),
      file("README.md", "root", 1),
      dir("components", "src", 2, 1),
      file("index.js", "src", 2),
    ],
    children: { root: ["src", "node_modules", "README.md"], src: ["components", "index.js"] },
  });
}

const ids = (model) => model.visibleRows().map((row) => row.id);

describe("TreeModel", () => {
  it("starts with the root expanded and children collapsed", () => {
    assert.deepEqual(ids(fullTree()), ["root", "src", "node_modules", "README.md"]);
  });

  it("expands and collapses loaded directories", () => {
    const model = fullTree();
    model.expand("src");
    assert.deepEqual(ids(model), ["root", "src", "components", "index.js", "node_modules", "README.md"]);
    model.collapse("src");
    assert.deepEqual(ids(model), ["root", "src", "node_modules", "README.md"]);
  });

  it("never collapses the root", () => {
    const model = fullTree();
    model.collapse("root");
    assert.equal(model.visibleRows().length, 4);
  });

  it("reports ARIA level and set position for each row", () => {
    const model = fullTree();
    model.expand("src");
    const row = model.visibleRows().find((item) => item.id === "index.js");
    assert.deepEqual(row, { id: "index.js", level: 3, pos: 2, size: 2 });
  });

  it("marks unloaded directories as needing children only in lazy mode", () => {
    const model = fullTree();
    assert.equal(model.canExpand("components"), true);
    assert.equal(model.needsChildren("components"), true);
    model.expand("components"); // not loaded yet: no-op
    assert.equal(model.isExpanded("components"), false);

    model.ingest({ nodes: [file("Button.jsx", "components", 3)], children: { components: ["Button.jsx"] } });
    model.expand("src");
    model.expand("components");
    assert.ok(ids(model).includes("Button.jsx"));
  });

  it("does not expand excluded or empty directories", () => {
    const model = fullTree();
    assert.equal(model.canExpand("node_modules"), false);
    assert.equal(model.canExpand("README.md"), false);
  });

  it("non-lazy models only expand into provided children", () => {
    const model = new TreeModel(
      { rootId: "root", nodes: [dir("root", null, 0, 3), dir("src", "root", 1, 2)], children: { root: ["src"] } },
      { lazy: false },
    );
    assert.equal(model.canExpand("src"), false);
  });

  it("expandLoaded respects a depth limit and collapseAll resets", () => {
    const model = fullTree();
    model.ingest({ nodes: [file("Button.jsx", "components", 3)], children: { components: ["Button.jsx"] } });
    model.expandLoaded(2);
    assert.ok(model.isExpanded("src"));
    assert.ok(!model.isExpanded("components"));
    model.collapseAll();
    assert.deepEqual([...model.expanded], ["root"]);
  });

  it("finds ancestors and reveals a deep node", () => {
    const model = fullTree();
    model.ingest({ nodes: [file("Button.jsx", "components", 3)], children: { components: ["Button.jsx"] } });
    assert.deepEqual(model.ancestors("Button.jsx"), ["root", "src", "components"]);
    model.expandAncestors("Button.jsx");
    assert.ok(ids(model).includes("Button.jsx"));
  });
});
