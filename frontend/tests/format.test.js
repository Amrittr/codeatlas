import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { formatArchiveTimestamp, formatBytes, formatDuration, percent, pluralize } from "../public/js/utils/format.js";

describe("format helpers", () => {
  it("formats bytes with binary units", () => {
    assert.equal(formatBytes(0), "0 B");
    assert.equal(formatBytes(1023), "1023 B");
    assert.equal(formatBytes(1536), "1.5 KB");
    assert.equal(formatBytes(150 * 1024 * 1024), "150 MB");
    assert.equal(formatBytes(null), "—");
  });

  it("formats durations", () => {
    assert.equal(formatDuration(42), "42 ms");
    assert.equal(formatDuration(1500), "1.50 s");
    assert.equal(formatDuration(125000), "2 min 5 s");
  });

  it("pluralizes with thousands separators", () => {
    assert.equal(pluralize(1, "file"), "1 file");
    assert.equal(pluralize(12000, "file"), "12,000 files");
    assert.equal(pluralize(2, "entry", "entries"), "2 entries");
  });

  it("keeps archive timestamps as recorded", () => {
    assert.equal(formatArchiveTimestamp("2024-05-17T12:30:00"), "2024-05-17 12:30");
    assert.equal(formatArchiveTimestamp(null), "—");
  });

  it("computes safe percentages", () => {
    assert.equal(percent(1, 4), 25);
    assert.equal(percent(1, 0), 0);
  });
});
