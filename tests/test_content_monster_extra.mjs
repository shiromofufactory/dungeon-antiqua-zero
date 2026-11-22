import assert from "node:assert/strict";
import test from "node:test";

import {
  assertValidDatasets,
  fromSheetPayload,
  loadDatasets,
  toSheetPayload,
  validateDatasets,
} from "../content/scripts/lib/data.mjs";

const datasets = await loadDatasets();

test("monster effects survive Sheets conversion and dataset validation", () => {
  const payload = toSheetPayload(datasets);
  payload.monsters[15].extra = "毒眠乱";

  const imported = { ...datasets, ...fromSheetPayload(payload) };
  assertValidDatasets(imported);
  assert.equal(imported.monsters[15].extra, "毒眠乱");
});

test("monster validation rejects unknown codes, delimiters and non-strings", () => {
  const payload = toSheetPayload(datasets);
  for (const extra of ["毒眠幻", "毒,眠", "毒\n眠", ["毒", "眠"], null]) {
    payload.monsters[15].extra = extra;
    const imported = { ...datasets, ...fromSheetPayload(payload) };
    assert.match(validateDatasets(imported).join("\n"), /monsters\.json\[15\]\.extra/);
  }
});

test("item effects still require a single item effect code", () => {
  const payload = toSheetPayload(datasets);
  for (const extra of ["毒眠", "幻"]) {
    payload.items[0].extra = extra;
    const imported = { ...datasets, ...fromSheetPayload(payload) };
    assert.match(validateDatasets(imported).join("\n"), /items\.json\[0\]\.extra/);
  }
});
