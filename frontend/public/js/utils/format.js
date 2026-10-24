const numberFormat = new Intl.NumberFormat("en-US");

export function formatNumber(value) {
  return numberFormat.format(value ?? 0);
}

export function formatBytes(bytes) {
  if (bytes === null || bytes === undefined || Number.isNaN(bytes)) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 100 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
}

export function formatDuration(ms) {
  if (ms < 1000) return `${Math.max(0, Math.round(ms))} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 2 : 1)} s`;
  return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`;
}

export function pluralize(count, singular, plural = `${singular}s`) {
  return `${formatNumber(count)} ${count === 1 ? singular : plural}`;
}

export function percent(part, total) {
  if (!total) return 0;
  return (part / total) * 100;
}

/** Archive timestamps carry no timezone, so they are shown as recorded, without conversion. */
export function formatArchiveTimestamp(iso) {
  if (!iso) return "—";
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso);
  return match ? `${match[1]}-${match[2]}-${match[3]} ${match[4]}:${match[5]}` : iso;
}

export function formatClock(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function minutesUntil(iso, now = Date.now()) {
  return Math.max(0, Math.round((new Date(iso).getTime() - now) / 60000));
}
