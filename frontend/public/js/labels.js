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

/** Bar colours for the extension chart, cycled by rank. */
export const SERIES_COLORS = [
  "bg-cls-source", "bg-cls-documentation", "bg-cls-test", "bg-cls-config",
  "bg-cls-data", "bg-cls-asset", "bg-accent-strong", "bg-cls-generated",
];

export function classificationInfo(value) {
  return CLASSIFICATIONS[value] ?? CLASSIFICATIONS.other;
}
