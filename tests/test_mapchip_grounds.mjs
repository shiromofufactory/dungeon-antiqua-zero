import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../tools/mapchip_metadata/static/app.js", import.meta.url), "utf8");
const copy = (value) => JSON.parse(JSON.stringify(value));

function editor() {
  const visual = {
    frame_interval: 12,
    choices: [
      { id: "default", weight: 7, frames: [{ tile: [1, 2] }, { tile: [2, 2] }] },
      { id: "alternate", weight: 0, frames: [{ tile: [3, 2] }] },
    ],
  };
  const state = {
    tab: "ground", groundIndex: 1, boundaryIndex: 1, choiceIndex: 1, frameIndex: 1,
    objectIndex: -1, objectLayer: "object_y_sorted", previewGrounds: Array(9).fill("plain"),
    data: { objects: [], grounds: [
      { id: "sea", parent_id: null, collision: "blocked", base_visual: copy(visual), boundaries: [] },
      {
        id: "plain", parent_id: "sea", collision: "passable", base_visual: copy(visual),
        boundaries: [
          { id: "north", neighbors: { n: "different", ne: "any", e: "same", se: "any", s: "same", sw: "any", w: "same", nw: "any" }, visual: copy(visual) },
          { id: "south", neighbors: { n: "same", ne: "any", e: "any", se: "any", s: "different", sw: "any", w: "same", nw: "any" }, visual: copy(visual) },
        ],
      },
    ] },
    objectOrigins: [], history: [], future: [], dirty: false,
  };
  const context = vm.createContext({
    state, clone: copy, escapeHtml: String, performance: { now: () => 0 },
    mutateObjectVisual: () => false, mutateVisual: () => false,
    activeVisual: () => context.currentVisual(), renderAll() {}, savePreviewSettings() {}, scheduleValidation() {},
    renderDefinitionList: () => "", renderVisualEditor: () => "",
  });
  for (const name of ["currentGround", "currentBoundary", "currentVisual", "currentObject", "normalizeSelectionIndexes", "uniqueId", "handleAction", "renderGroundEditor", "commit", "undo", "redo", "syncRestoredObjectLayer"]) {
    const start = source.indexOf(`function ${name}(`);
    assert.notEqual(start, -1, name);
    const next = source.slice(start + 1).search(/\n(?:async )?function /);
    assert.notEqual(next, -1, name);
    vm.runInContext(source.slice(start, start + 1 + next), context);
  }
  return { context, state, duplicate: () => context.handleAction({ dataset: { action: "duplicate-ground" } }) };
}

test("ground duplication preserves all settings and boundary order, selects the copy and supports undo/redo", () => {
  const { context, state, duplicate } = editor();
  const before = copy(state.data);
  duplicate();
  const expected = { ...before.grounds[1], id: "plain_copy" };
  assert.deepEqual(copy(state.data), { ...before, grounds: [...before.grounds, expected] });
  assert.equal(state.groundIndex, 2);
  assert.equal(state.boundaryIndex, 0);
  assert.equal(state.choiceIndex, 0);
  assert.equal(state.frameIndex, 0);
  assert.equal(state.dirty, true);
  assert.equal(state.history.length, 1);
  context.undo();
  assert.deepEqual(copy(state.data), before);
  context.redo();
  assert.deepEqual(copy(state.data), { ...before, grounds: [...before.grounds, expected] });
});

test("editing nested visuals and boundaries in the copy leaves the source unchanged", () => {
  const { context, state, duplicate } = editor();
  const before = copy(state.data.grounds);
  duplicate();
  const ground = context.currentGround();
  ground.parent_id = null;
  ground.base_visual.choices[0].frames[0].tile[0] = 9;
  ground.boundaries[0].neighbors.n = "any";
  ground.boundaries[0].visual.choices[0].weight = 1;
  ground.boundaries[0].visual.choices[0].frames[0].tile[1] = 8;
  ground.boundaries.reverse();
  assert.deepEqual(copy(state.data.grounds.slice(0, 2)), before);
});

test("repeated duplication of the same ground skips used copy IDs", () => {
  const { state, duplicate } = editor();
  for (let index = 0; index < 3; index += 1) {
    state.groundIndex = 1;
    duplicate();
  }
  assert.deepEqual(Array.from(state.data.grounds, (ground) => ground.id), ["sea", "plain", "plain_copy", "plain_copy_2", "plain_copy_3"]);
});

test("base ground can be duplicated without changing the base and the buttons are adjacent", () => {
  const { context, state, duplicate } = editor();
  state.groundIndex = 0;
  const before = copy(state.data.grounds);
  assert.match(context.renderGroundEditor(), /data-action="duplicate-ground">地面を複製<\/button>\s*<button[^>]*data-action="delete-ground" disabled/);
  duplicate();
  assert.deepEqual(copy(context.currentGround()), { ...before[0], id: "sea_copy" });
  assert.deepEqual(copy(state.data.grounds.slice(0, 2)), before);
  assert.match(context.renderGroundEditor(), /data-action="delete-ground" >地面を削除/);
});

test("duplication outside the ground tab or without a selection leaves data and history unchanged", () => {
  const { state, duplicate } = editor();
  const before = copy(state.data);
  state.tab = "boundary";
  duplicate();
  state.tab = "ground";
  state.groundIndex = -1;
  duplicate();
  assert.deepEqual(copy(state.data), before);
  assert.equal(state.history.length, 0);
  assert.equal(state.dirty, false);
});
