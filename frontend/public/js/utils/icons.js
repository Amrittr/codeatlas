/**
 * Inline SVG icons (paths adapted from the ISC-licensed Lucide set), built with
 * createElementNS so no markup string is ever parsed.
 */
const SVG_NS = "http://www.w3.org/2000/svg";

const p = (d) => ["path", { d }];
const circle = (cx, cy, r) => ["circle", { cx, cy, r }];
const rect = (x, y, width, height, rx = 2) => ["rect", { x, y, width, height, rx }];
const FILE_OUTLINE = [p("M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"), p("M14 2v4a2 2 0 0 0 2 2h4")];

const ICONS = {
  "chevron-right": [p("m9 18 6-6-6-6")],
  "chevron-down": [p("m6 9 6 6 6-6")],
  folder: [p("M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z")],
  "folder-open": [
    p("m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"),
  ],
  file: FILE_OUTLINE,
  "file-code": [...FILE_OUTLINE, p("m10 13-2 2 2 2"), p("m14 17 2-2-2-2")],
  "file-text": [...FILE_OUTLINE, p("M10 9H8"), p("M16 13H8"), p("M16 17H8")],
  flask: [
    p("M10 2v7.527a2 2 0 0 1-.211.896L4.72 20.55a1 1 0 0 0 .9 1.45h12.76a1 1 0 0 0 .9-1.45l-5.069-10.127A2 2 0 0 1 14 9.527V2"),
    p("M8.5 2h7"),
    p("M7 16h10"),
  ],
  sliders: [
    p("M21 4h-7"), p("M10 4H3"), p("M21 12h-9"), p("M8 12H3"), p("M21 20h-5"), p("M12 20H3"),
    p("M14 2v4"), p("M8 10v4"), p("M16 18v4"),
  ],
  image: [rect(3, 3, 18, 18), circle(9, 9, 2), p("m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21")],
  database: [["ellipse", { cx: 12, cy: 5, rx: 9, ry: 3 }], p("M3 5V19A9 3 0 0 0 21 19V5"), p("M3 12A9 3 0 0 0 21 12")],
  package: [
    p("m7.5 4.27 9 5.15"),
    p("M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"),
    p("m3.3 7 8.7 5 8.7-5"),
    p("M12 22V12"),
  ],
  search: [circle(11, 11, 8), p("m21 21-4.3-4.3")],
  upload: [p("M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"), p("m17 8-5-5-5 5"), p("M12 3v12")],
  x: [p("M18 6 6 18"), p("m6 6 12 12")],
  dashboard: [rect(3, 3, 7, 9, 1), rect(14, 3, 7, 5, 1), rect(14, 12, 7, 9, 1), rect(3, 16, 7, 5, 1)],
  "list-tree": [p("M21 12h-8"), p("M21 6H8"), p("M21 18h-8"), p("M3 6v4c0 1.1.9 2 2 2h3"), p("M3 10v6c0 1.1.9 2 2 2h3")],
  network: [
    rect(16, 16, 6, 6, 1), rect(2, 16, 6, 6, 1), rect(9, 2, 6, 6, 1),
    p("M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3"), p("M12 12V8"),
  ],
  "git-fork": [
    circle(12, 18, 3), circle(6, 6, 3), circle(18, 6, 3),
    p("M18 9v2c0 .6-.4 1-1 1H7c-.6 0-1-.4-1-1V9"), p("M12 12v3"),
  ],
  message: [p("M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z")],
  settings: [p("M20 7h-9"), p("M14 17H5"), circle(17, 17, 3), circle(7, 7, 3)],
  alert: [p("m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"), p("M12 9v4"), p("M12 17h.01")],
  info: [circle(12, 12, 10), p("M12 16v-4"), p("M12 8h.01")],
  check: [circle(12, 12, 10), p("m9 12 2 2 4-4")],
  copy: [rect(8, 8, 14, 14), p("M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2")],
  "corner-up": [p("M14 9 9 4 4 9"), p("M20 20h-7a4 4 0 0 1-4-4V4")],
  plus: [p("M5 12h14"), p("M12 5v14")],
  trash: [p("M3 6h18"), p("M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"), p("M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2")],
  shield: [
    p("M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"),
  ],
  ban: [circle(12, 12, 10), p("m4.9 4.9 14.2 14.2")],
  expand: [p("m7 15 5 5 5-5"), p("m7 9 5-5 5 5")],
  collapse: [p("m7 20 5-5 5 5"), p("m7 4 5 5 5-5")],
  locate: [circle(12, 12, 3), p("M12 2v3"), p("M12 19v3"), p("M2 12h3"), p("M19 12h3")],
};

export function icon(name, className = "size-4") {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("class", `shrink-0 ${className}`);
  for (const [tag, attrs] of ICONS[name] ?? ICONS.file) {
    const child = document.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attrs)) child.setAttribute(key, String(value));
    svg.append(child);
  }
  return svg;
}

/** Replace placeholder `<span data-icon="name">` elements in static markup. */
export function hydrateIcons(root = document) {
  for (const placeholder of root.querySelectorAll("[data-icon]")) {
    placeholder.replaceWith(icon(placeholder.dataset.icon, placeholder.className || "size-4"));
  }
}
