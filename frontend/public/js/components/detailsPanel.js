/** Metadata for the selected file or folder, with observed facts and inferences kept apart. */
import { EXCLUSION_REASONS, classificationInfo } from "../labels.js";
import { h, mount } from "../utils/dom.js";
import { formatArchiveTimestamp, formatBytes, formatNumber, pluralize } from "../utils/format.js";
import { icon } from "../utils/icons.js";

export function createDetailsPanel({ onSelectParent, onShowInTree, onCopied }) {
  const element = h("div", { class: "flex h-full min-h-0 flex-col overflow-y-auto p-5", "aria-live": "polite", id: "details-panel" });
  showEmpty();

  function showEmpty() {
    mount(
      element,
      h(
        "div",
        { class: "flex flex-1 flex-col items-center justify-center text-center" },
        icon("locate", "size-6 text-subtle"),
        h("p", { class: "mt-3 text-sm text-muted" }, "Select a file or folder"),
        h("p", { class: "mt-1 text-xs text-subtle" }, "Use the mouse, or arrow keys inside the tree."),
      ),
    );
  }

  function show(node, { isRoot, filtered, parent }) {
    if (!node) return showEmpty();
    const isDirectory = node.type === "directory";
    const info = isDirectory ? null : classificationInfo(node.classification);

    mount(
      element,
      h(
        "div",
        { class: "flex items-start gap-3" },
        h(
          "div",
          { class: "flex size-9 shrink-0 items-center justify-center rounded-lg border border-line bg-raised" },
          isDirectory ? icon(node.excluded ? "ban" : "folder", `size-4 ${node.excluded ? "text-subtle" : "text-accent"}`) : icon(info.icon, `size-4 ${info.text}`),
        ),
        h(
          "div",
          { class: "min-w-0" },
          h("h2", { class: "text-base font-semibold break-all", id: "details-name" }, node.name),
          h("p", { class: "text-xs text-subtle" }, isRoot ? "Archive root" : isDirectory ? "Folder" : "File"),
        ),
      ),
      pathBlock(node, isRoot),
      node.excluded ? excludedBanner(node) : null,
      node.generated ? generatedBanner(node) : null,
      section("Observed", isDirectory ? directoryFacts(node) : fileFacts(node)),
      isDirectory ? null : section("Inferred", inferredFacts(node, info), "From the file name and extension. The file's contents were not read."),
      h(
        "div",
        { class: "mt-5 flex flex-wrap gap-2" },
        parent
          ? h("button", { type: "button", class: "btn btn-ghost", onclick: () => onSelectParent(parent.id), id: "select-parent" }, icon("corner-up", "size-3.5"), "Parent folder")
          : null,
        filtered
          ? h("button", { type: "button", class: "btn btn-ghost", onclick: () => onShowInTree(node.id), id: "show-in-tree" }, icon("list-tree", "size-3.5"), "Show in full tree")
          : null,
      ),
      isDirectory
        ? null
        : h(
            "p",
            { class: "mt-auto flex items-center gap-2 pt-6 text-xs text-subtle" },
            h("span", { class: "badge-planned" }, "Planned"),
            "Source viewing and symbol details arrive with code parsing.",
          ),
    );
  }

  function pathBlock(node, isRoot) {
    const path = isRoot ? "/" : node.path;
    return h(
      "div",
      { class: "mt-4 flex items-center gap-2 rounded-lg border border-line bg-raised px-3 py-2" },
      h("code", { class: "min-w-0 flex-1 font-mono text-xs break-all text-muted", id: "details-path" }, path),
      h(
        "button",
        {
          type: "button",
          class: "tree-toggle size-7",
          title: "Copy path",
          "aria-label": "Copy path",
          onclick: async () => {
            try {
              await navigator.clipboard.writeText(path);
              onCopied?.("Path copied");
            } catch {
              onCopied?.("Could not access the clipboard");
            }
          },
        },
        icon("copy", "size-3.5"),
      ),
    );
  }

  return { element, show, showEmpty };
}

function section(title, rows, note) {
  return h(
    "section",
    { class: "mt-5" },
    h("h3", { class: "card-title mb-2" }, title),
    h("dl", { class: "grid grid-cols-[7.5rem_1fr] gap-x-3 gap-y-2" }, rows),
    note ? h("p", { class: "mt-2 text-xs text-subtle" }, note) : null,
  );
}

function row(label, value) {
  return [h("dt", { class: "kv-label pt-0.5" }, label), h("dd", { class: "kv-value min-w-0 break-words" }, value)];
}

function fileFacts(node) {
  const size =
    node.sizeBytes === null
      ? "Not extracted"
      : `${formatBytes(node.sizeBytes)}${node.sizeBytes >= 1024 ? ` (${formatNumber(node.sizeBytes)} bytes)` : ""}`;
  return [
    row("Size", size),
    row("Extension", node.extension ? h("code", { class: "font-mono text-xs" }, node.extension) : "none"),
    row("Modified", h("span", { title: "As recorded in the archive. ZIP timestamps carry no time zone." }, formatArchiveTimestamp(node.modifiedAt))),
    row("Hidden", node.hidden ? "Yes (dot-file)" : "No"),
    row("Depth", String(node.depth)),
  ];
}

function directoryFacts(node) {
  if (node.excluded) {
    return [row("Contents", "Not analyzed"), row("Depth", String(node.depth))];
  }
  return [
    row("Direct children", formatNumber(node.childCount)),
    row("Files (all levels)", formatNumber(node.descendantFileCount)),
    row("Folders (all levels)", formatNumber(node.descendantDirectoryCount)),
    row("Total size", formatBytes(node.sizeBytes)),
    row("Depth", String(node.depth)),
  ];
}

function inferredFacts(node, info) {
  return [
    row(
      "Classification",
      h(
        "span",
        { class: "flex flex-wrap items-center gap-1.5" },
        h("span", { class: `chip ${info.text}` }, info.label),
        h("span", { class: "chip" }, `${node.classificationConfidence} confidence`),
      ),
    ),
    row("Reason", node.classificationReason),
    row("Language", node.language ?? "Not recognised"),
  ];
}

function generatedBanner(node) {
  return h(
    "div",
    { class: "mt-4 flex gap-3 rounded-lg border border-line-strong bg-raised p-3", id: "details-generated" },
    icon("package", "mt-0.5 size-4 shrink-0 text-cls-generated"),
    h(
      "div",
      { class: "min-w-0 text-xs leading-relaxed text-muted" },
      h("p", {}, `Likely generated output (${node.generatedConfidence} confidence, inferred). Its files are classified as Generated but still analyzed.`),
      h("p", { class: "mt-1 text-ink" }, node.generatedReason),
    ),
  );
}

function excludedBanner(node) {
  const reason = EXCLUSION_REASONS[node.excludedReason] ?? node.excludedReason;
  const entries = node.excludedEntryCount;
  let consequence;
  if (node.type === "file") consequence = "This file was not analyzed and is not counted in the statistics.";
  else if (entries === null || entries === undefined) consequence = "Its contents were not scanned.";
  else consequence = `${pluralize(entries, "archive entry", "archive entries")} inside it were not extracted or analyzed.`;
  return h(
    "div",
    { class: "mt-4 flex gap-3 rounded-lg border border-warn/30 bg-warn/5 p-3", id: "details-excluded" },
    icon("ban", "mt-0.5 size-4 shrink-0 text-warn"),
    h(
      "div",
      { class: "min-w-0 text-xs leading-relaxed text-muted" },
      h("p", {}, `Excluded (${reason}). ${consequence}`),
      node.excludedRule ? h("code", { class: "mt-1 block font-mono break-all text-ink" }, node.excludedRule) : null,
    ),
  );
}
