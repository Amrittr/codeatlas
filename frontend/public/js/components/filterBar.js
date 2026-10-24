/** Search box plus type, classification and extension filters for the file explorer. */
import { CLASSIFICATIONS } from "../labels.js";
import { h, mount } from "../utils/dom.js";
import { formatNumber } from "../utils/format.js";
import { icon } from "../utils/icons.js";

const SEARCH_DEBOUNCE_MS = 200;

export function createFilterBar({ onChange }) {
  const state = { q: "", type: "all", classification: "", extensions: new Set() };
  let debounce = 0;

  const searchInput = h("input", {
    type: "search",
    class: "field pl-9",
    placeholder: "Search files and folders…",
    "aria-label": "Search files and folders by name or path",
    autocomplete: "off",
    spellcheck: "false",
    id: "tree-search",
  });
  const typeSelect = h(
    "select",
    { class: "field w-auto", "aria-label": "Item type" },
    h("option", { value: "all" }, "Files & folders"),
    h("option", { value: "file" }, "Files only"),
    h("option", { value: "directory" }, "Folders only"),
  );
  const classificationSelect = h(
    "select",
    { class: "field w-auto", "aria-label": "Classification" },
    h("option", { value: "" }, "Any classification"),
    Object.entries(CLASSIFICATIONS).map(([value, info]) => h("option", { value }, info.label)),
  );
  const extensionSummary = h("span", {}, "Any extension");
  const extensionList = h("div", { class: "flex max-h-72 flex-col gap-0.5 overflow-y-auto py-1" });
  const extensionMenu = h(
    "details",
    { class: "relative" },
    h(
      "summary",
      { class: "field flex w-auto cursor-pointer list-none items-center gap-2 whitespace-nowrap", "aria-label": "Filter by extension" },
      extensionSummary,
      icon("chevron-down", "size-3.5 text-subtle"),
    ),
    h(
      "div",
      { class: "absolute left-0 z-30 mt-1 w-60 max-w-[calc(100vw-2rem)] rounded-xl border border-line-strong bg-raised p-2 shadow-2xl shadow-black/40" },
      extensionList,
      h(
        "button",
        {
          type: "button",
          class: "btn btn-ghost mt-1 w-full",
          onclick: () => {
            state.extensions.clear();
            for (const box of extensionList.querySelectorAll("input")) box.checked = false;
            changed();
          },
        },
        "Clear extensions",
      ),
    ),
  );
  const clearButton = h(
    "button",
    { type: "button", class: "btn btn-ghost", hidden: true, onclick: () => reset({ notify: true }) },
    icon("x", "size-3.5"),
    "Clear",
  );

  function isActive() {
    return Boolean(state.q || state.type !== "all" || state.classification || state.extensions.size);
  }

  function changed({ immediate = true } = {}) {
    clearButton.hidden = !isActive();
    extensionSummary.textContent =
      state.extensions.size === 0
        ? "Any extension"
        : state.extensions.size <= 2
          ? [...state.extensions].join(", ")
          : `${state.extensions.size} extensions`;
    clearTimeout(debounce);
    if (immediate) onChange(snapshot());
    else debounce = setTimeout(() => onChange(snapshot()), SEARCH_DEBOUNCE_MS);
  }

  function snapshot() {
    return { ...state, extensions: [...state.extensions], active: isActive() };
  }

  function reset({ notify = false } = {}) {
    state.q = "";
    state.type = "all";
    state.classification = "";
    state.extensions.clear();
    searchInput.value = "";
    typeSelect.value = "all";
    classificationSelect.value = "";
    for (const box of extensionList.querySelectorAll("input")) box.checked = false;
    extensionMenu.open = false;
    if (notify) changed();
    else {
      clearButton.hidden = true;
      extensionSummary.textContent = "Any extension";
    }
  }

  function setExtensions(extensions) {
    mount(
      extensionList,
      extensions.map((item) =>
        h(
          "label",
          { class: "flex cursor-pointer items-center gap-2 rounded-md px-2 py-1 text-sm hover:bg-hover" },
          h("input", {
            type: "checkbox",
            value: item.extension,
            class: "size-3.5 accent-accent",
            onchange: (event) => {
              if (event.target.checked) state.extensions.add(item.extension);
              else state.extensions.delete(item.extension);
              changed();
            },
          }),
          h("span", { class: "flex-1 truncate font-mono text-xs" }, item.extension),
          h("span", { class: "text-xs text-subtle tabular-nums" }, formatNumber(item.fileCount)),
        ),
      ),
    );
  }

  searchInput.addEventListener("input", () => {
    state.q = searchInput.value.trim();
    changed({ immediate: false });
  });
  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && searchInput.value) {
      event.stopPropagation();
      searchInput.value = "";
      state.q = "";
      changed();
    }
  });
  typeSelect.addEventListener("change", () => {
    state.type = typeSelect.value;
    changed();
  });
  classificationSelect.addEventListener("change", () => {
    state.classification = classificationSelect.value;
    changed();
  });
  document.addEventListener("click", (event) => {
    if (extensionMenu.open && !extensionMenu.contains(event.target)) extensionMenu.open = false;
  });

  const element = h(
    "div",
    { class: "flex flex-wrap items-center gap-2" },
    h(
      "div",
      { class: "relative min-w-48 flex-1" },
      h("span", { class: "pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-subtle" }, icon("search", "size-4")),
      searchInput,
    ),
    typeSelect,
    classificationSelect,
    extensionMenu,
    clearButton,
  );

  return { element, reset, setExtensions, focusSearch: () => searchInput.focus(), snapshot };
}
