/**
 * Project overview dashboard. Every figure comes from the analysis response. Inferred values
 * (classification, language) are labelled as such.
 */
import { CLASSIFICATIONS, EXCLUSION_REASONS, SERIES_COLORS, SKIP_REASONS, classificationInfo } from "../labels.js";
import { h, mount } from "../utils/dom.js";
import { formatBytes, formatDuration, formatNumber, percent, pluralize } from "../utils/format.js";
import { icon } from "../utils/icons.js";

const MAX_EXTENSIONS = 12;
const MAX_STRUCTURE_ROWS = 12;

export function renderOverview(container, { details, model, onReveal }) {
  const { project, stats, exclusions, exclusionCount, skipped, skippedCount, warnings } = details;

  mount(
    container,
    h(
      "div",
      { class: "mx-auto flex w-full max-w-7xl flex-col gap-4" },
      summaryStrip(project, stats),
      warnings.length ? warningList(warnings) : null,
      h(
        "div",
        { class: "grid grid-cols-2 gap-3 md:grid-cols-4" },
        statCard("Files", formatNumber(stats.totalFiles), "file", withExcluded(`${formatNumber(stats.hiddenFileCount)} hidden`, stats.excludedFileCount)),
        statCard("Folders", formatNumber(stats.totalDirectories), "folder", withExcluded(`${formatNumber(stats.emptyDirectoryCount)} empty`, stats.excludedDirectoryCount)),
        statCard("Total size", formatBytes(stats.totalSizeBytes), "database", "sum of analyzed files"),
        statCard("File types", formatNumber(stats.fileTypeCount), "package", `max depth ${stats.maxDepth}`),
      ),
      h("p", { class: "-mb-2 text-xs text-subtle" }, "Files by role (inferred from names and extensions)"),
      h(
        "div",
        { class: "grid grid-cols-2 gap-3 md:grid-cols-4" },
        miniStat("source", stats.sourceFileCount),
        miniStat("test", stats.testFileCount),
        miniStat("config", stats.configFileCount),
        miniStat("documentation", stats.documentationFileCount),
      ),
      h(
        "div",
        { class: "grid gap-4 lg:grid-cols-5" },
        h("div", { class: "min-w-0 lg:col-span-3" }, extensionCard(stats)),
        h("div", { class: "min-w-0 lg:col-span-2" }, classificationCard(stats)),
      ),
      h(
        "div",
        { class: "grid gap-4 lg:grid-cols-2" },
        structureCard(model, onReveal),
        configCard(stats.configFiles, onReveal),
      ),
      h(
        "div",
        { class: "grid gap-4 lg:grid-cols-2" },
        exclusionCard(exclusions, exclusionCount, project.exclusionSettings, onReveal),
        generatedCard(stats.generatedFolders, stats.generatedFolderCount, onReveal),
      ),
      h(
        "div",
        { class: "grid items-start gap-4 lg:grid-cols-2" },
        largestFilesCard(stats.largestFiles, onReveal),
        skippedCount ? skippedCard(skipped, skippedCount) : null,
      ),
      h(
        "p",
        { class: "pb-4 text-xs text-subtle" },
        "Counts, paths and sizes are observed directly from the archive. Classifications and languages are inferred from file names and extensions. File contents read: .gitignore files and package manifests, plus JS/TS/Python source for the architecture map (when enabled), parsed in memory and never run.",
      ),
    ),
  );
}

function summaryStrip(project, stats) {
  const item = (label, value) =>
    h("div", { class: "min-w-0" }, h("p", { class: "kv-label" }, label), h("p", { class: "kv-value truncate" }, value));
  return h(
    "div",
    { class: "card flex flex-wrap items-center gap-x-8 gap-y-3 px-5 py-4" },
    h(
      "div",
      { class: "flex items-center gap-2" },
      icon("check", "size-5 text-ok"),
      h("span", { class: "text-sm font-medium" }, "Analysis complete"),
    ),
    item("Archive", `${project.archive.fileName} · ${formatBytes(project.archive.sizeBytes)}`),
    item("Archive entries", formatNumber(project.archive.entryCount)),
    item("Scan duration", formatDuration(project.durations.totalMs)),
    item("Indexed nodes", formatNumber(project.nodeCount)),
    item("Exclusion rules", describeRules(project.exclusionSettings)),
    item("Architecture map", project.codeAnalysis ? "Generated" : "Off"),
    item("Processing", "Server mode"),
    stats.totalFiles === 0 ? h("span", { class: "chip border-warn/40 text-warn" }, "Empty project") : null,
  );
}

function withExcluded(text, excluded) {
  return excluded ? `${text} · ${formatNumber(excluded)} excluded` : text;
}

function describeRules(settings) {
  const parts = [];
  if (settings.defaultRules) parts.push("defaults");
  if (settings.gitignore) parts.push(settings.gitignoreFiles.length ? `.gitignore ×${settings.gitignoreFiles.length}` : ".gitignore (none found)");
  const custom = settings.excludePatterns.length + settings.includePatterns.length;
  if (custom) parts.push(`${custom} custom`);
  return parts.length ? parts.join(" · ") : "None";
}

function warningList(warnings) {
  return h(
    "div",
    { class: "flex flex-col gap-2", role: "status" },
    warnings.map((warning) =>
      h(
        "div",
        { class: "flex items-start gap-3 rounded-xl border border-warn/30 bg-warn/5 px-4 py-3", dataset: { warning: warning.code } },
        icon(warning.code === "possible_secrets" ? "shield" : "info", "mt-0.5 size-4 text-warn"),
        h("p", { class: "text-sm text-muted" }, warning.message),
      ),
    ),
  );
}

function statCard(label, value, iconName, hint) {
  return h(
    "div",
    { class: "card p-4", dataset: { stat: label } },
    h("div", { class: "flex items-center justify-between" }, h("p", { class: "card-title" }, label), icon(iconName, "size-4 text-subtle")),
    h("p", { class: "mt-2 text-2xl font-semibold tracking-tight tabular-nums" }, value),
    h("p", { class: "mt-1 text-xs text-subtle" }, hint),
  );
}

function miniStat(classification, count) {
  const info = CLASSIFICATIONS[classification];
  return h(
    "div",
    { class: "flex items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3", dataset: { stat: classification } },
    icon(info.icon, `size-4 ${info.text}`),
    h("span", { class: "truncate text-sm text-muted", title: "Inferred from file names and extensions" }, info.label),
    h("span", { class: "ml-auto font-semibold tabular-nums" }, formatNumber(count)),
  );
}

function cardShell(title, subtitle, ...body) {
  return h(
    "section",
    { class: "card h-full min-w-0 p-5" },
    h("div", { class: "mb-4 flex items-baseline justify-between gap-3" }, h("h2", { class: "card-title" }, title), subtitle ? h("p", { class: "text-xs text-subtle" }, subtitle) : null),
    ...body,
  );
}

function emptyNote(text) {
  return h("p", { class: "text-sm text-subtle" }, text);
}

function extensionCard(stats) {
  const top = stats.extensions.slice(0, MAX_EXTENSIONS);
  const rest = stats.extensions.slice(MAX_EXTENSIONS);
  const max = Math.max(1, ...top.map((item) => item.fileCount));
  const restCount = rest.reduce((sum, item) => sum + item.fileCount, 0);
  return cardShell(
    "File-type distribution",
    `${pluralize(stats.fileTypeCount, "extension")}`,
    top.length === 0
      ? emptyNote("No files were analyzed.")
      : h(
          "ul",
          { class: "flex flex-col gap-2.5", "aria-label": "Files per extension" },
          top.map((item, index) =>
            h(
              "li",
              { class: "grid grid-cols-[5.5rem_1fr_auto] items-center gap-3 text-sm" },
              h("span", { class: "truncate font-mono text-xs text-muted" }, item.extension),
              h("div", { class: "meter" }, h("span", { class: SERIES_COLORS[index % SERIES_COLORS.length], style: { width: `${Math.max(2, percent(item.fileCount, max))}%` } })),
              h(
                "span",
                { class: "w-28 text-right text-xs text-subtle tabular-nums" },
                h("span", { class: "text-ink" }, formatNumber(item.fileCount)),
                ` · ${formatBytes(item.sizeBytes)}`,
              ),
            ),
          ),
          rest.length ? h("li", { class: "pt-1 text-xs text-subtle" }, `+ ${pluralize(rest.length, "more extension")} (${pluralize(restCount, "file")})`) : null,
        ),
  );
}

function classificationCard(stats) {
  const total = stats.totalFiles;
  return cardShell(
    "File classification",
    "inferred",
    total === 0
      ? emptyNote("No files were analyzed.")
      : [
          h(
            "div",
            { class: "flex h-2.5 overflow-hidden rounded-full bg-raised", role: "img", "aria-label": "Share of files per classification" },
            stats.classifications.map((item) =>
              h("span", { class: classificationInfo(item.classification).color, style: { width: `${percent(item.fileCount, total)}%` } }),
            ),
          ),
          h(
            "ul",
            { class: "mt-4 grid grid-cols-2 gap-x-4 gap-y-2" },
            stats.classifications.map((item) => {
              const info = classificationInfo(item.classification);
              return h(
                "li",
                { class: "flex items-center gap-2 text-sm" },
                h("span", { class: `size-2 rounded-full ${info.color}` }),
                h("span", { class: "text-muted" }, info.label),
                h("span", { class: "ml-auto tabular-nums" }, formatNumber(item.fileCount)),
              );
            }),
          ),
          h("h3", { class: "card-title mt-6 mb-3" }, "Detected languages"),
          stats.languages.length
            ? h(
                "ul",
                { class: "flex flex-wrap gap-1.5" },
                stats.languages.slice(0, 16).map((item) =>
                  h("li", { class: "chip" }, item.language, h("span", { class: "text-subtle tabular-nums" }, formatNumber(item.fileCount))),
                ),
              )
            : emptyNote("No known language extensions."),
        ],
  );
}

function structureRoot(model) {
  const top = model.children.get(model.rootId) ?? [];
  const only = top.length === 1 ? model.get(top[0]) : null;
  if (only && only.type === "directory" && !only.excluded && model.children.has(only.id)) return only;
  return model.get(model.rootId);
}

function structureCard(model, onReveal) {
  const base = structureRoot(model);
  const childIds = model.children.get(base.id) ?? [];
  const items = childIds.map((id) => model.get(id)).filter(Boolean);
  const max = Math.max(1, ...items.map((item) => (item.type === "directory" ? item.descendantFileCount : 1)));
  return cardShell(
    "Top-level structure",
    base.path ? `${base.name}/` : "archive root",
    items.length === 0
      ? emptyNote("This folder is empty.")
      : h(
          "ul",
          { class: "flex flex-col" },
          items.slice(0, MAX_STRUCTURE_ROWS).map((item) => {
            const isDir = item.type === "directory";
            const hasFiles = isDir && !item.excluded && item.descendantFileCount > 0;
            const right = !isDir
              ? formatBytes(item.sizeBytes)
              : item.excluded
                ? "excluded"
                : item.childCount === 0
                  ? "empty"
                  : pluralize(item.descendantFileCount, "file");
            return h(
              "li",
              {},
              h(
                "button",
                {
                  type: "button",
                  class: "grid w-full grid-cols-[1fr_6rem_auto] items-center gap-3 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-hover",
                  onclick: () => onReveal(item.id),
                  title: `Show ${item.path} in the file explorer`,
                },
                h(
                  "span",
                  { class: "flex min-w-0 items-center gap-2" },
                  icon(isDir ? (item.excluded ? "ban" : "folder") : classificationInfo(item.classification).icon, `size-4 ${isDir ? (item.excluded ? "text-subtle" : "text-accent") : "text-subtle"}`),
                  h("span", { class: `truncate ${item.excluded ? "text-subtle italic" : ""}` }, item.name),
                ),
                hasFiles
                  ? h("div", { class: "meter" }, h("span", { class: "bg-accent", style: { width: `${Math.max(2, percent(item.descendantFileCount, max))}%` } }))
                  : h("span"),
                h("span", { class: "w-24 text-right text-xs text-subtle tabular-nums" }, right),
              ),
            );
          }),
          items.length > MAX_STRUCTURE_ROWS ? h("li", { class: "px-2 pt-1 text-xs text-subtle" }, `+ ${pluralize(items.length - MAX_STRUCTURE_ROWS, "more item")}`) : null,
        ),
  );
}

function fileLinkList(items, onReveal, renderRight) {
  return h(
    "ul",
    { class: "flex flex-col" },
    items.map((item) =>
      h(
        "li",
        {},
        h(
          "button",
          {
            type: "button",
            class: "flex w-full items-center gap-3 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-hover",
            onclick: () => onReveal(item.nodeId),
            title: `Show ${item.path} in the file explorer`,
          },
          h("span", { class: "min-w-0 flex-1 truncate font-mono text-xs text-muted" }, item.path),
          renderRight(item),
        ),
      ),
    ),
  );
}

function configCard(configFiles, onReveal) {
  return cardShell(
    "Configuration & manifests",
    configFiles.length ? pluralize(configFiles.length, "file") : null,
    configFiles.length
      ? fileLinkList(configFiles.slice(0, 14), onReveal, (item) => h("span", { class: "chip shrink-0" }, item.label))
      : emptyNote("No well-known configuration files were found."),
    configFiles.length > 14 ? h("p", { class: "mt-2 px-2 text-xs text-subtle" }, `+ ${pluralize(configFiles.length - 14, "more")}`) : null,
    h("p", { class: "mt-3 text-xs text-subtle" }, "Recognised by file name. A manifest does not prove the tool is actively used."),
  );
}

function exclusionCard(exclusions, total, settings, onReveal) {
  const active = settings.defaultRules || settings.gitignore || settings.excludePatterns.length;
  return cardShell(
    "Excluded paths",
    total ? pluralize(total, "path") : null,
    exclusions.length
      ? h(
          "ul",
          { class: "flex flex-col" },
          exclusions.slice(0, 40).map((item) =>
            h(
              "li",
              {},
              h(
                "button",
                {
                  type: "button",
                  class: "flex w-full items-center gap-3 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-hover",
                  onclick: () => onReveal(item.nodeId),
                  title: `Show ${item.path} in the file explorer`,
                },
                icon(item.type === "directory" ? "folder" : "file", "size-3.5 shrink-0 text-subtle"),
                h("span", { class: "min-w-0 flex-1 truncate font-mono text-xs text-muted" }, item.path),
                h("span", { class: "chip max-w-[45%] shrink-0 truncate", title: item.rule ?? "" }, item.rule ?? EXCLUSION_REASONS[item.reason] ?? item.reason),
                item.entryCount === null
                  ? null
                  : h("span", { class: "w-16 shrink-0 text-right text-xs text-subtle tabular-nums" }, pluralize(item.entryCount, "entry", "entries")),
              ),
            ),
          ),
        )
      : emptyNote(active ? "Nothing matched the exclusion rules. Every path was analyzed." : "Exclusions were turned off for this analysis."),
    total > Math.min(40, exclusions.length) ? h("p", { class: "mt-2 px-2 text-xs text-subtle" }, `Showing ${formatNumber(Math.min(40, exclusions.length))} of ${formatNumber(total)}. Search the explorer to find the rest.`) : null,
    h("p", { class: "mt-3 text-xs text-subtle" }, "Excluded paths were not extracted or analyzed. They are still listed in the tree."),
  );
}

function generatedCard(folders, total, onReveal) {
  return cardShell(
    "Likely generated folders",
    total ? pluralize(total, "folder") : "inferred",
    folders.length
      ? h(
          "ul",
          { class: "flex flex-col gap-1" },
          folders.slice(0, 20).map((item) =>
            h(
              "li",
              {},
              h(
                "button",
                {
                  type: "button",
                  class: "flex w-full flex-col gap-0.5 rounded-lg px-2 py-1.5 text-left hover:bg-hover",
                  onclick: () => onReveal(item.nodeId),
                  title: `Show ${item.path} in the file explorer`,
                  dataset: { generated: item.path },
                },
                h(
                  "span",
                  { class: "flex w-full items-center gap-2 text-sm" },
                  icon("package", "size-3.5 shrink-0 text-cls-generated"),
                  h("span", { class: "min-w-0 flex-1 truncate font-mono text-xs text-muted" }, item.path),
                  h("span", { class: "chip shrink-0" }, `${item.confidence} confidence`),
                  h("span", { class: "w-16 shrink-0 text-right text-xs text-subtle tabular-nums" }, pluralize(item.fileCount, "file")),
                ),
                h("span", { class: "pl-5.5 text-xs text-subtle" }, item.reason),
              ),
            ),
          ),
        )
      : emptyNote("No build-output or generated folders were detected."),
    h(
      "p",
      { class: "mt-3 text-xs text-subtle" },
      "Judged from file names (bundles, source maps, compiled files) and conventional folder names. These folders are still analyzed. Their files count as Generated.",
    ),
  );
}

function largestFilesCard(files, onReveal) {
  return cardShell(
    "Largest files",
    null,
    files.length
      ? fileLinkList(files, onReveal, (item) => h("span", { class: "shrink-0 text-xs text-subtle tabular-nums" }, formatBytes(item.sizeBytes)))
      : emptyNote("No files were analyzed."),
  );
}

function skippedCard(skipped, skippedCount) {
  return h(
    "details",
    { class: "card group p-5" },
    h(
      "summary",
      { class: "flex cursor-pointer list-none items-center gap-2" },
      icon("chevron-right", "size-4 text-subtle transition-transform group-open:rotate-90"),
      h("h2", { class: "card-title" }, "Skipped archive entries"),
      h("span", { class: "chip ml-auto" }, formatNumber(skippedCount)),
    ),
    h(
      "ul",
      { class: "mt-4 flex flex-col gap-1" },
      skipped.map((item) =>
        h(
          "li",
          { class: "flex items-center gap-3 px-2 py-1 text-sm" },
          h("span", { class: "min-w-0 flex-1 truncate font-mono text-xs text-muted" }, item.path),
          h("span", { class: "chip shrink-0" }, SKIP_REASONS[item.reason] ?? item.reason),
        ),
      ),
    ),
    skippedCount > skipped.length ? h("p", { class: "mt-2 px-2 text-xs text-subtle" }, `Showing the first ${formatNumber(skipped.length)}.`) : null,
    h("p", { class: "mt-3 px-2 text-xs text-subtle" }, "Skipped entries were not extracted and do not appear in the tree."),
  );
}
