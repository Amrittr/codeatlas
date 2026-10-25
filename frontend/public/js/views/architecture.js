/**
 * Architecture map: the generated component diagram (Cytoscape canvas) plus an accessible
 * list view of the same data, and a details panel showing the evidence behind every role
 * and connection. Every number and arrow comes from GET /api/projects/{id}/architecture.
 */
import { getArchitecture, getComponent } from "../api.js";
import { CONFIDENCE_LABELS, EXTERNAL_COLUMN, ROLES } from "../labels.js";
import { h, mount } from "../utils/dom.js";
import { formatNumber, pluralize } from "../utils/format.js";
import { icon } from "../utils/icons.js";

const NODE_GAP_X = 240; // horizontal spacing between boxes in a layer
const LAYER_GAP_Y = 130; // vertical spacing between layers
const SUBROW_GAP_Y = 82; // spacing between wrapped rows inside one layer
const MAX_PER_ROW = 5;
const MAX_FIT_ZOOM = 1.1;
const KIND_LABELS = {
  static: "import",
  require: "require()",
  dynamic: "dynamic import()",
  reexport: "re-export",
  type: "type-only import",
  python: "Python import",
  http: "HTTP (inferred)",
};

let cytoscapeModule = null;
async function loadCytoscape() {
  cytoscapeModule ??= import("../../vendor/cytoscape.esm.min.mjs").then((module) => module.default);
  return cytoscapeModule;
}

const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

export function createArchitectureView({ onReveal, onError }) {
  let projectId = null;
  let data = null;
  let cy = null;
  let mode = "map";
  let selection = null; // { type: "component" | "external" | "connection", id }
  let requestSeq = 0;

  const element = h("div", { class: "mx-auto flex w-full max-w-[1600px] min-h-0 flex-1 flex-col gap-4", id: "architecture-view" });

  /* ---------- loading ---------- */

  async function load(id) {
    projectId = id;
    data = null;
    selection = null;
    destroyGraph();
    const seq = ++requestSeq;
    mount(element, stateCard("Building the map view…", "spinner"));
    try {
      const result = await getArchitecture(id);
      if (seq !== requestSeq) return;
      data = result;
      render();
    } catch (error) {
      if (seq !== requestSeq) return;
      mount(element, stateCard(error.message || "The architecture map could not be loaded.", "alert"));
      onError?.(error);
    }
  }

  /** Call when the view becomes visible: Cytoscape needs a laid-out container. */
  async function show() {
    if (!data || data.status !== "available" || mode !== "map") return;
    if (cy) {
      cy.resize();
      return;
    }
    await drawGraph();
  }

  /* ---------- page ---------- */

  function render() {
    if (data.status !== "available" || data.components.length === 0) {
      const message =
        data.status === "disabled"
          ? "Code analysis was turned off for this upload, so no source files were read and no map was generated. Upload again with “Map the architecture” checked."
          : "No source code was found to map. The project may contain only documentation, data or configuration files, or every code file was excluded.";
      mount(element, stateCard(message, "network"), notesCard());
      return;
    }
    const roleChips = [...new Set(data.components.map((c) => c.role))].map((role) =>
      h("span", { class: "chip" }, h("span", { class: "size-2 rounded-full", style: { backgroundColor: cssVar(ROLES[role]?.token ?? "--color-cls-other") } }), ROLES[role]?.label ?? role),
    );
    const toggle = (value, label, iconName) =>
      h(
        "button",
        {
          type: "button",
          class: `btn px-3 ${mode === value ? "btn-primary" : "btn-ghost"}`,
          "aria-pressed": String(mode === value),
          onclick: () => setMode(value),
          dataset: { mode: value },
        },
        icon(iconName, "size-3.5"),
        label,
      );

    mount(
      element,
      h(
        "div",
        { class: "card flex flex-wrap items-center gap-x-6 gap-y-3 px-5 py-3" },
        h(
          "div",
          { class: "min-w-0" },
          h("p", { class: "text-sm font-medium" }, "Generated architecture map"),
          h(
            "p",
            { class: "text-xs text-subtle", id: "architecture-summary" },
            `${pluralize(data.components.length, "component")} · ${pluralize(data.connections.length, "connection")} · ${formatNumber(data.summary.parsedFiles)} of ${formatNumber(data.summary.codeFiles)} code files parsed`,
          ),
        ),
        data.frameworks.length
          ? h("div", { class: "flex flex-wrap gap-1.5" }, data.frameworks.slice(0, 6).map((f) => h("span", { class: "chip", title: `${f.importingFiles} importing file(s)` }, f.name)))
          : null,
        h(
          "div",
          { class: "ml-auto flex items-center gap-2" },
          toggle("map", "Map", "network"),
          toggle("list", "List", "list-tree"),
          mode === "map" ? h("button", { type: "button", class: "btn btn-ghost px-2", title: "Fit to screen", "aria-label": "Fit to screen", onclick: () => fit() }, icon("expand", "size-4")) : null,
        ),
      ),
      h(
        "div",
        { class: "grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,1fr)_24rem]" },
        h(
          "section",
          { class: "card relative flex min-h-[28rem] min-w-0 flex-col overflow-hidden lg:h-[calc(100vh-14rem)]", "aria-label": "Architecture map" },
          mode === "map"
            ? [
                h("div", { class: "min-h-0 flex-1", id: "architecture-canvas", role: "img", "aria-label": "Diagram of components and their connections. Use the List view for a text version." }),
                legend(roleChips),
              ]
            : listView(),
        ),
        h("aside", { class: "card min-h-[18rem] overflow-y-auto p-5 lg:h-[calc(100vh-14rem)]", "aria-label": "Map details", id: "architecture-details", "aria-live": "polite" }),
      ),
      notesCard(),
    );
    renderDetails();
    if (mode === "map" && !element.closest("[hidden]")) drawGraph();
  }

  function setMode(next) {
    if (mode === next) return;
    mode = next;
    destroyGraph();
    render();
  }

  function legend(roleChips) {
    return h(
      "div",
      { class: "flex flex-wrap items-center gap-2 border-t border-line px-4 py-2 text-[11px] text-subtle" },
      roleChips,
      h("span", { class: "ml-2 inline-flex items-center gap-1" }, h("span", { class: "inline-block h-0 w-5 border-t-2 border-line-strong" }), "import"),
      h("span", { class: "inline-flex items-center gap-1" }, h("span", { class: "inline-block h-0 w-5 border-t-2 border-dashed border-accent" }), "HTTP (inferred)"),
      h("span", { class: "inline-flex items-center gap-1" }, h("span", { class: "inline-block size-3 rounded border border-dashed border-muted" }), "low-confidence role"),
    );
  }

  function stateCard(message, iconName) {
    return h(
      "div",
      { class: "card flex flex-col items-center justify-center gap-3 p-10 text-center" },
      iconName === "spinner" ? h("span", { class: "spinner size-6" }) : icon(iconName, "size-6 text-subtle"),
      h("p", { class: "max-w-xl text-sm text-muted" }, message),
    );
  }

  function notesCard() {
    const s = data?.summary;
    return h(
      "details",
      { class: "card group p-5", open: data?.status !== "available" ? true : undefined },
      h(
        "summary",
        { class: "flex cursor-pointer list-none items-center gap-2" },
        icon("chevron-right", "size-4 text-subtle transition-transform group-open:rotate-90"),
        h("h2", { class: "card-title" }, "How this map was made"),
      ),
      h("ul", { class: "mt-3 flex list-disc flex-col gap-1.5 pl-5 text-sm text-muted" }, (data?.notes ?? []).map((note) => h("li", {}, note))),
      s && data.status === "available"
        ? h(
            "p",
            { class: "mt-3 text-xs text-subtle" },
            `${formatNumber(s.imports)} imports found · ${formatNumber(s.internalImports)} resolved inside the project · ${formatNumber(s.externalPackages)} external packages · ${formatNumber(s.unresolvedImports)} unresolved · ${formatNumber(s.parseErrors)} files with syntax errors`,
          )
        : null,
    );
  }

  /* ---------- graph ---------- */

  function nameOf(id) {
    return data.components.find((c) => c.id === id)?.name ?? data.externals.find((x) => x.id === id)?.name ?? id;
  }

  /**
   * Layers run top to bottom in the order a request flows: UI and tests → API/server →
   * business logic → shared/data → external services. Wide layers wrap into extra rows.
   */
  function layoutPositions() {
    const columns = new Map();
    const degree = new Map();
    for (const connection of data.connections) {
      degree.set(connection.source, (degree.get(connection.source) ?? 0) + 1);
      degree.set(connection.target, (degree.get(connection.target) ?? 0) + 1);
    }
    const place = (id, column) => {
      if (!columns.has(column)) columns.set(column, []);
      columns.get(column).push(id);
    };
    for (const component of data.components) place(component.id, ROLES[component.role]?.column ?? 2);
    for (const external of data.externals) place(external.id, EXTERNAL_COLUMN);
    const positions = {};
    let y = 0;
    for (const column of [...columns.keys()].sort((a, b) => a - b)) {
      const ids = columns.get(column);
      ids.sort((a, b) => (degree.get(b) ?? 0) - (degree.get(a) ?? 0) || nameOf(a).localeCompare(nameOf(b)));
      for (let start = 0; start < ids.length; start += MAX_PER_ROW) {
        const row = ids.slice(start, start + MAX_PER_ROW);
        const offset = ((row.length - 1) * NODE_GAP_X) / 2;
        row.forEach((id, index) => {
          positions[id] = { x: index * NODE_GAP_X - offset, y };
        });
        y += SUBROW_GAP_Y;
      }
      y += LAYER_GAP_Y - SUBROW_GAP_Y;
    }
    return positions;
  }

  async function drawGraph() {
    const container = element.querySelector("#architecture-canvas");
    if (!container || cy) return;
    let cytoscape;
    try {
      cytoscape = await loadCytoscape();
    } catch (error) {
      mount(container, stateCard("The map renderer could not be loaded. The List view shows the same data.", "alert"));
      onError?.(error);
      return;
    }
    if (!container.isConnected || cy) return;
    const positions = layoutPositions();
    const maxCount = Math.max(1, ...data.connections.map((c) => c.importCount || 1));
    const elements = [
      ...data.components.map((c) => ({
        group: "nodes",
        data: {
          id: c.id,
          kind: "component",
          label: `${c.name}\n${ROLES[c.role]?.label ?? c.role} · ${pluralize(c.fileCount, "file")}`,
          color: cssVar(ROLES[c.role]?.token ?? "--color-cls-other"),
          confidence: c.confidence,
        },
        position: positions[c.id],
      })),
      ...data.externals.map((x) => ({
        group: "nodes",
        data: { id: x.id, kind: "external", label: `${x.name}\n${x.services.map((s) => s.split(" (")[0]).slice(0, 3).join(", ")}`, color: cssVar("--color-subtle"), confidence: "high" },
        position: positions[x.id],
      })),
      ...data.connections.map((c) => ({
        group: "edges",
        data: {
          id: c.id,
          source: c.source,
          target: c.target,
          http: c.kinds.length === 1 && c.kinds[0] === "http",
          width: 1.2 + 3.5 * Math.sqrt((c.importCount || 1) / maxCount),
        },
      })),
    ];
    const font = getComputedStyle(document.body).fontFamily;
    cy = cytoscape({
      container,
      elements,
      layout: { name: "preset", fit: true, padding: 40 },
      minZoom: 0.15,
      maxZoom: 2.5,
      boxSelectionEnabled: false,
      style: [
        {
          selector: "node",
          style: {
            shape: "round-rectangle",
            width: 210,
            height: 58,
            "background-color": cssVar("--color-raised"),
            "border-width": 2,
            "border-color": "data(color)",
            label: "data(label)",
            color: cssVar("--color-ink"),
            "font-family": font,
            "font-size": 11,
            "text-wrap": "wrap",
            "text-max-width": 190,
            "text-valign": "center",
            "text-halign": "center",
          },
        },
        { selector: 'node[confidence = "low"]', style: { "border-style": "dashed" } },
        { selector: 'node[kind = "external"]', style: { shape: "barrel", "background-color": cssVar("--color-surface"), color: cssVar("--color-muted") } },
        {
          selector: "edge",
          style: {
            width: "data(width)",
            "curve-style": "bezier",
            "line-color": cssVar("--color-line-strong"),
            "target-arrow-color": cssVar("--color-line-strong"),
            "target-arrow-shape": "triangle",
            "arrow-scale": 0.9,
          },
        },
        {
          selector: "edge[?http]",
          style: {
            "line-style": "dashed",
            "line-color": cssVar("--color-accent"),
            "target-arrow-color": cssVar("--color-accent"),
            label: "HTTP",
            "font-size": 9,
            color: cssVar("--color-accent"),
            "text-background-color": cssVar("--color-surface"),
            "text-background-opacity": 1,
            "text-background-padding": 2,
          },
        },
        { selector: "node:selected", style: { "border-width": 4, "border-color": cssVar("--color-accent-strong") } },
        { selector: "edge:selected", style: { "line-color": cssVar("--color-accent-strong"), "target-arrow-color": cssVar("--color-accent-strong"), width: 4 } },
        { selector: ".faded", style: { opacity: 0.18 } },
      ],
    });
    if (cy.zoom() > MAX_FIT_ZOOM) {
      cy.zoom(MAX_FIT_ZOOM);
      cy.center();
    }
    container.dataset.renderedNodes = String(cy.nodes().length);
    container.dataset.renderedEdges = String(cy.edges().length);
    cy.on("tap", "node", (event) => {
      const node = event.target;
      select(node.data("kind") === "external" ? "external" : "component", node.id(), { fromGraph: true });
    });
    cy.on("tap", "edge", (event) => select("connection", event.target.id(), { fromGraph: true }));
    cy.on("tap", (event) => {
      if (event.target === cy) select(null, null, { fromGraph: true });
    });
    if (selection) highlight();
  }

  function fit() {
    if (!cy) return;
    cy.fit(undefined, 40);
    if (cy.zoom() > MAX_FIT_ZOOM) {
      cy.zoom(MAX_FIT_ZOOM);
      cy.center();
    }
  }

  function destroyGraph() {
    cy?.destroy();
    cy = null;
  }

  function highlight() {
    if (!cy) return;
    cy.elements().removeClass("faded").unselect();
    if (!selection) return;
    const target = cy.getElementById(selection.id);
    if (target.empty()) return;
    target.select();
    const keep = target.isNode() ? target.closedNeighborhood() : target.union(target.connectedNodes());
    cy.elements().not(keep).addClass("faded");
  }

  /* ---------- selection & details ---------- */

  function select(type, id, { fromGraph = false } = {}) {
    selection = type ? { type, id } : null;
    if (!fromGraph) highlight();
    else if (cy) {
      cy.elements().removeClass("faded");
      if (selection) {
        const target = cy.getElementById(id);
        const keep = target.isNode() ? target.closedNeighborhood() : target.union(target.connectedNodes());
        cy.elements().not(keep).addClass("faded");
      }
    }
    renderDetails();
    for (const button of element.querySelectorAll("[data-select-id]")) {
      button.setAttribute("aria-current", String(button.dataset.selectId === id));
    }
  }

  function renderDetails() {
    const panel = element.querySelector("#architecture-details");
    if (!panel) return;
    if (!selection) return mount(panel, overviewDetails());
    if (selection.type === "component") return mount(panel, componentDetails(data.components.find((c) => c.id === selection.id)));
    if (selection.type === "external") return mount(panel, externalDetails(data.externals.find((x) => x.id === selection.id)));
    return mount(panel, connectionDetails(data.connections.find((c) => c.id === selection.id)));
  }

  function locationLink(path, nodeId, line) {
    if (!path) return null;
    const text = line ? `${path}:${line}` : path;
    return nodeId
      ? h("button", { type: "button", class: "block max-w-full truncate text-left font-mono text-[11px] text-accent hover:underline", title: `Show ${path} in the file explorer`, onclick: () => onReveal(nodeId), dataset: { evidenceLink: path } }, text)
      : h("span", { class: "block truncate font-mono text-[11px] text-subtle" }, text);
  }

  function heading(title, subtitle) {
    return h("div", { class: "mb-4" }, h("h2", { class: "text-base font-semibold break-words", id: "architecture-details-title" }, title), subtitle ? h("p", { class: "text-xs text-subtle" }, subtitle) : null);
  }

  function section(title, ...children) {
    return h("section", { class: "mt-5" }, h("h3", { class: "card-title mb-2" }, title), ...children);
  }

  function overviewDetails() {
    return h(
      "div",
      {},
      heading("Select a component or arrow", "Click a box or an arrow to see the evidence behind it."),
      section(
        "Detected frameworks",
        data.frameworks.length
          ? h(
              "ul",
              { class: "flex flex-col gap-2" },
              data.frameworks.map((f) =>
                h(
                  "li",
                  { class: "text-sm" },
                  h("span", { class: "font-medium" }, f.name),
                  h("span", { class: "ml-2 chip" }, CONFIDENCE_LABELS[f.confidence]),
                  h(
                    "p",
                    { class: "text-xs text-subtle" },
                    [f.importingFiles ? `imported by ${pluralize(f.importingFiles, "file")}` : "not imported by analyzed code", f.declaredIn.length ? `declared in ${f.declaredIn.join(", ")}` : null]
                      .filter(Boolean)
                      .join(" · "),
                  ),
                ),
              ),
            )
          : h("p", { class: "text-sm text-subtle" }, "No known frameworks were found in imports or manifests."),
      ),
      section(
        "Languages parsed",
        h("p", { class: "text-sm text-muted" }, data.summary.languages.map((l) => `${l.language} (${formatNumber(l.fileCount)})`).join(" · ")),
      ),
    );
  }

  function componentDetails(component) {
    const outgoing = data.connections.filter((c) => c.source === component.id);
    const incoming = data.connections.filter((c) => c.target === component.id);
    const role = ROLES[component.role];
    const filesSection = h("div", { class: "text-sm text-subtle" }, "Loading files…");
    getComponent(projectId, component.id)
      .then((details) => {
        mount(
          filesSection,
          h(
            "ul",
            { class: "flex flex-col gap-1" },
            details.files.slice(0, 25).map((file) =>
              h(
                "li",
                { class: "flex items-center gap-2" },
                h("div", { class: "min-w-0 flex-1" }, locationLink(file.path, file.nodeId)),
                h("span", { class: "shrink-0 text-[11px] text-subtle tabular-nums", title: "imports inside the project / imported by" }, `↗${file.importsInternal} ↙${file.importedBy}`),
              ),
            ),
          ),
          details.totalFiles > 25 ? h("p", { class: "mt-1 text-xs text-subtle" }, `+ ${pluralize(details.totalFiles - 25, "more file")}`) : null,
        );
      })
      .catch(() => mount(filesSection, h("p", { class: "text-sm text-subtle" }, "Files could not be loaded.")));

    return h(
      "div",
      { dataset: { component: component.name } },
      heading(component.name, component.packageName && !component.name.startsWith(component.packageName) ? `package ${component.packageName}` : component.path || "archive root"),
      h(
        "div",
        { class: "flex flex-wrap gap-1.5" },
        h("span", { class: "chip text-ink", style: { borderColor: cssVar(role?.token ?? "--color-cls-other") } }, role?.label ?? component.role),
        h("span", { class: `chip ${component.confidence === "low" ? "border-dashed" : ""}`, id: "component-confidence" }, CONFIDENCE_LABELS[component.confidence]),
        h("span", { class: "chip" }, pluralize(component.fileCount, "file")),
      ),
      component.nodeId
        ? h("button", { type: "button", class: "btn btn-ghost mt-3", onclick: () => onReveal(component.nodeId) }, icon("list-tree", "size-3.5"), "Show folder in explorer")
        : null,
      section(
        "Why this role",
        h(
          "ul",
          { class: "flex flex-col gap-2", id: "component-evidence" },
          component.evidence.map((item) => h("li", { class: "text-sm text-muted" }, item.detail, locationLink(item.path, item.nodeId, item.line))),
        ),
        component.confidence === "low"
          ? h("p", { class: "mt-2 text-xs text-subtle" }, "Only naming conventions support this role, so treat it as a hypothesis.")
          : null,
      ),
      component.frameworks.length ? section("Frameworks used", h("div", { class: "flex flex-wrap gap-1.5" }, component.frameworks.map((f) => h("span", { class: "chip" }, f)))) : null,
      component.entryPoints.length
        ? section("Entry points", h("ul", { class: "flex flex-col gap-1" }, component.entryPoints.map((e) => h("li", { class: "text-sm text-muted" }, e.reason, locationLink(e.path, e.nodeId)))))
        : null,
      section("Depends on", connectionList(outgoing, "target")),
      section("Used by", connectionList(incoming, "source")),
      section("Most connected files", filesSection),
    );
  }

  function connectionList(connections, end) {
    if (!connections.length) return h("p", { class: "text-sm text-subtle" }, "None found.");
    return h(
      "ul",
      { class: "flex flex-col gap-1" },
      connections.map((c) =>
        h(
          "li",
          {},
          h(
            "button",
            { type: "button", class: "flex w-full items-center gap-2 rounded-md px-1 py-0.5 text-left text-sm hover:bg-hover", onclick: () => select("connection", c.id) },
            h("span", { class: "min-w-0 flex-1 truncate" }, nameOf(c[end])),
            h("span", { class: "chip shrink-0" }, c.kinds.includes("http") && c.kinds.length === 1 ? "HTTP" : pluralize(c.importCount, "import")),
          ),
        ),
      ),
    );
  }

  function externalDetails(external) {
    const users = data.connections.filter((c) => c.target === external.id);
    return h(
      "div",
      {},
      heading(external.name, "External service, detected from imported client libraries"),
      section("Services", h("ul", { class: "flex flex-col gap-1" }, external.services.map((s) => h("li", { class: "text-sm text-muted" }, s)))),
      section("Used by", connectionList(users, "source")),
    );
  }

  function connectionDetails(connection) {
    const httpOnly = connection.kinds.length === 1 && connection.kinds[0] === "http";
    return h(
      "div",
      {},
      heading(`${nameOf(connection.source)} → ${nameOf(connection.target)}`, httpOnly ? "HTTP calls (inferred)" : pluralize(connection.importCount, "import") + ` in ${pluralize(connection.fileCount, "file")}`),
      h(
        "div",
        { class: "flex flex-wrap gap-1.5" },
        connection.kinds.map((kind) => h("span", { class: "chip" }, KIND_LABELS[kind] ?? kind)),
        h("span", { class: "chip" }, CONFIDENCE_LABELS[connection.confidence]),
      ),
      httpOnly
        ? h("p", { class: "mt-3 text-xs text-subtle" }, "Matched by URL path: the client references a path that the server declares as a route. Static analysis cannot prove the request reaches this server at runtime.")
        : null,
      section(
        "Evidence",
        h(
          "ul",
          { class: "flex flex-col gap-2", id: "connection-evidence" },
          connection.evidence.map((e) =>
            h("li", { class: "text-sm text-muted" }, h("code", { class: "font-mono text-xs text-ink" }, e.specifier), h("span", { class: "text-xs text-subtle" }, ` → ${e.target}`), locationLink(e.path, e.nodeId, e.line)),
          ),
        ),
        connection.importCount > connection.evidence.length
          ? h("p", { class: "mt-1 text-xs text-subtle" }, `Showing ${connection.evidence.length} of ${formatNumber(connection.importCount)}.`)
          : null,
      ),
    );
  }

  /* ---------- list view (accessible alternative to the canvas) ---------- */

  function listView() {
    const byRole = new Map();
    for (const component of data.components) {
      if (!byRole.has(component.role)) byRole.set(component.role, []);
      byRole.get(component.role).push(component);
    }
    const item = (id, type, name, meta, confidence) =>
      h(
        "li",
        {},
        h(
          "button",
          {
            type: "button",
            class: "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm hover:bg-hover aria-[current=true]:bg-accent-soft",
            onclick: () => select(type, id),
            dataset: { selectId: id, listItem: name },
            "aria-current": String(selection?.id === id),
          },
          h("span", { class: `min-w-0 flex-1 truncate ${confidence === "low" ? "italic" : ""}` }, name),
          h("span", { class: "shrink-0 text-xs text-subtle" }, meta),
        ),
      );
    return h(
      "div",
      { class: "min-h-0 flex-1 overflow-y-auto p-4", id: "architecture-list" },
      [...byRole.entries()]
        .sort((a, b) => (ROLES[a[0]]?.column ?? 2) - (ROLES[b[0]]?.column ?? 2))
        .map(([role, components]) =>
          h(
            "section",
            { class: "mb-4" },
            h("h3", { class: "card-title mb-1 px-3" }, ROLES[role]?.label ?? role),
            h(
              "ul",
              {},
              components.map((c) => {
                const out = data.connections.filter((x) => x.source === c.id).length;
                const incoming = data.connections.filter((x) => x.target === c.id).length;
                return item(c.id, "component", c.name, `${pluralize(c.fileCount, "file")} · ${out} out · ${incoming} in · ${c.confidence}`, c.confidence);
              }),
            ),
          ),
        ),
      data.externals.length
        ? h("section", { class: "mb-4" }, h("h3", { class: "card-title mb-1 px-3" }, "External services"), h("ul", {}, data.externals.map((x) => item(x.id, "external", x.name, x.services.map((s) => s.split(" (")[0]).join(", ")))))
        : null,
      h(
        "section",
        {},
        h("h3", { class: "card-title mb-1 px-3" }, "Connections"),
        h("ul", {}, data.connections.map((c) => item(c.id, "connection", `${nameOf(c.source)} → ${nameOf(c.target)}`, c.kinds.includes("http") && c.kinds.length === 1 ? "HTTP (inferred)" : pluralize(c.importCount, "import")))),
      ),
    );
  }

  return { element, load, show, reset: () => { projectId = null; data = null; destroyGraph(); element.replaceChildren(); } };
}
