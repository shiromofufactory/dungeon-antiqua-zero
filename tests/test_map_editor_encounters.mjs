import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../tools/map_editor/static/app.js", import.meta.url), "utf8");
const detailIds = [
  "encounter-monster-level", "encounter-danger", "encounter-polarity",
  "encounter-allow-demons", "encounter-allow-humans", "encounter-allow-giants",
  "encounter-allow-large-animals",
];

function editor() {
  const original = {
    monster_level: 7, danger: "high", polarity: "yin",
    allow_demons: true, allow_humans: false, allow_giants: true, allow_large_animals: false,
  };
  const state = {
    data: { profile: "dungeon", random_encounter: { ...original } },
    history: [], future: [], dirty: false, siteNamesJa: {}, arrivalIdRenames: {},
  };
  const elements = new Map();
  const byId = (id) => {
    if (!elements.has(id)) elements.set(id, {
      value: "", checked: false, disabled: false, open: false, listeners: {},
      showModal() { this.open = true; },
      close() { this.open = false; },
      addEventListener(type, listener) { this.listeners[type] = listener; },
    });
    return elements.get(id);
  };
  const context = vm.createContext({
    state, byId, renderAll: () => {}, scheduleResolution: () => {}, normalizeSelections: () => {},
  });
  for (const name of [
    "openRandomEncounterDialog", "updateRandomEncounterControls", "beginChange", "finishChange",
    "commit", "undo", "redo", "changeSnapshot", "restoreChangeSnapshot",
  ]) {
    const start = source.indexOf(`function ${name}(`);
    assert.notEqual(start, -1, name);
    const next = source.slice(start + 1).search(/\n(?:async )?function /);
    vm.runInContext(source.slice(start, start + 1 + next), context);
  }
  vm.runInContext(source.slice(
    source.indexOf('byId("encounter-enabled").addEventListener'),
    source.indexOf('byId("delete-map-button").addEventListener'),
  ), context);
  const selectEnabled = (enabled) => {
    byId("encounter-enabled").value = String(enabled);
    byId("encounter-enabled").listeners.change();
  };
  const submit = () => byId("random-encounter-form").listeners.submit({ preventDefault() {} });
  const settings = () => JSON.parse(JSON.stringify(state.data.random_encounter));
  return { context, state, byId, original, selectEnabled, submit, settings };
}

test("legacy floor settings open with encounters enabled and their existing formation", () => {
  const { context, state, byId, original, settings } = editor();
  context.openRandomEncounterDialog();
  assert.equal(byId("encounter-enabled").value, "true");
  assert.equal(byId("encounter-monster-level").value, "7");
  assert.equal(byId("encounter-allow-demons").checked, true);
  for (const id of detailIds) assert.equal(byId(id).disabled, false);
  assert.deepEqual(settings(), original);
  assert.equal(state.dirty, false);
});

test("no encounters disables formation controls and applies without losing their values", () => {
  const { context, state, byId, original, selectEnabled, submit, settings } = editor();
  context.openRandomEncounterDialog();
  selectEnabled(false);
  for (const id of detailIds) assert.equal(byId(id).disabled, true);
  assert.deepEqual(settings(), original);
  submit();
  assert.deepEqual(settings(), { enabled: false, ...original });
  assert.equal(byId("random-encounter-dialog").open, false);
  assert.equal(state.dirty, true);
  assert.equal(state.history.length, 1);
  context.openRandomEncounterDialog();
  assert.equal(byId("encounter-enabled").value, "false");
  for (const id of detailIds) assert.equal(byId(id).disabled, true);
});

test("re-enabling encounters restores the retained formation and editable controls", () => {
  const { context, byId, original, selectEnabled, submit, settings } = editor();
  context.openRandomEncounterDialog();
  selectEnabled(false);
  submit();
  context.openRandomEncounterDialog();
  selectEnabled(true);
  for (const id of detailIds) assert.equal(byId(id).disabled, false);
  submit();
  assert.deepEqual(settings(), { enabled: true, ...original });
});

test("cancel discards encounter changes and reopening reads the saved floor settings", () => {
  const { context, state, byId, original, selectEnabled, settings } = editor();
  context.openRandomEncounterDialog();
  selectEnabled(false);
  byId("encounter-monster-level").value = "dynamic";
  byId("random-encounter-dialog").listeners.click({
    target: { dataset: { action: "close-random-encounter-dialog" } },
    currentTarget: byId("random-encounter-dialog"),
  });
  assert.deepEqual(settings(), original);
  assert.equal(state.dirty, false);
  assert.equal(state.history.length, 0);
  context.openRandomEncounterDialog();
  assert.equal(byId("encounter-enabled").value, "true");
  assert.equal(byId("encounter-monster-level").value, "7");
});

test("undo and redo restore all encounter settings in one change", () => {
  const { context, state, original, selectEnabled, submit, settings } = editor();
  context.openRandomEncounterDialog();
  selectEnabled(false);
  submit();
  context.undo();
  assert.deepEqual(settings(), original);
  assert.equal(state.history.length, 0);
  context.redo();
  assert.deepEqual(settings(), { enabled: false, ...original });
  assert.equal(state.history.length, 1);
});
