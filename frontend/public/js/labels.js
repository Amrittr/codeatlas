/** Human-readable labels and colours for values defined by the backend schema. */

export const CLASSIFICATIONS = {
  source: { label: "Source", color: "bg-cls-source", text: "text-cls-source", icon: "file-code" },
  test: { label: "Test", color: "bg-cls-test", text: "text-cls-test", icon: "flask" },
  config: { label: "Config", color: "bg-cls-config", text: "text-cls-config", icon: "sliders" },
  documentation: { label: "Docs", color: "bg-cls-documentation", text: "text-cls-documentation", icon: "file-text" },
  data: { label: "Data", color: "bg-cls-data", text: "text-cls-data", icon: "database" },
  asset: { label: "Asset", color: "bg-cls-asset", text: "text-cls-asset", icon: "image" },
  generated: { label: "Generated", color: "bg-cls-generated", text: "text-cls-generated", icon: "package" },
  other: { label: "Other", color: "bg-cls-other", text: "text-cls-other", icon: "file" },
};

export const EXCLUSION_REASONS = {
  archive_metadata: "macOS archive metadata",
  version_control: "Version-control internals",
  dependencies: "Installed dependencies",
  virtual_environment: "Python virtual environment",
  cache: "Tool cache",
  build_cache: "Framework build cache",
  gitignore: ".gitignore",
  custom: "Custom rule",
};

export const CONFIDENCE_LABELS = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence (hypothesis)",
};

export const SKIP_REASONS = {
  symlink_not_followed: "Symbolic link (not followed)",
  special_file: "Device, pipe or socket",
  encrypted: "Password-protected entry",
  case_collision: "Differs only by letter case from another entry",
  duplicate_entry: "Duplicate entry",
  path_conflict: "A file and a folder share this path",
  file_too_large: "Exceeds the per-file size limit",
  unsupported_compression: "Unsupported compression method",
  corrupt_entry: "Corrupted data",
  unsafe_name: "Name contains control characters",
  name_too_long: "Name longer than 255 bytes",
  path_too_long: "Path too long",
  permission_denied: "Permission denied",
  unreadable: "Could not be read",
};

/** Architecture roles: label, CSS colour token (also read by the canvas renderer), map column. */
export const ROLES = {
  frontend: { label: "Frontend / UI", token: "--color-cls-source", column: 0 },
  tests: { label: "Tests", token: "--color-cls-test", column: 0 },
  api: { label: "API & routes", token: "--color-cls-documentation", column: 1 },
  backend: { label: "Backend server", token: "--color-cls-data", column: 1 },
  service: { label: "Business logic", token: "--color-accent-strong", column: 2 },
  auth: { label: "Authentication", token: "--color-cls-asset", column: 2 },
  jobs: { label: "Background jobs", token: "--color-cls-config", column: 2 },
  module: { label: "Module", token: "--color-cls-other", column: 2 },
  shared: { label: "Shared library", token: "--color-cls-generated", column: 3 },
  config: { label: "Configuration", token: "--color-cls-config", column: 3 },
  data: { label: "Data access", token: "--color-warn", column: 3 },
};

export const EXTERNAL_COLUMN = 4;

/** Bar colours for the extension chart, cycled by rank. */
export const SERIES_COLORS = [
  "bg-cls-source", "bg-cls-documentation", "bg-cls-test", "bg-cls-config",
  "bg-cls-data", "bg-cls-asset", "bg-accent-strong", "bg-cls-generated",
];

export function classificationInfo(value) {
  return CLASSIFICATIONS[value] ?? CLASSIFICATIONS.other;
}
