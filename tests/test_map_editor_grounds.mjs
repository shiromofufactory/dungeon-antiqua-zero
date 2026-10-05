import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../tools/map_editor/static/app.js", import.meta.url), "utf8");

// Run the actual paint functions and pointer handlers without the DOM/network shell.
function editor(baseGroundId = "ground", size = [16, 15]) {
  const state = {
    tab: "ground", groundId: "floor", groundTool: "brush", dirty: false,
    history: [], future: [], bulkSelection: [], pointerDrag: null, pointerStroke: null,
    groundPaintRect: null, siteNamesJa: {}, arrivalIdRenames: {},
    tileset: { grounds: [{ id: baseGroundId }, { id: "floor" }] },
    data: { size, grounds: Array.from({ length: size[1] }, () => Array(size[0]).fill(baseGroundId)) },
  };
  const handlers = new Map();
  let captured = false;
  let resolutions = 0;
  const context = vm.createContext({
    state, performance: { now: () => 0 },
    mapCanvas: {
      addEventListener: (type, callback) => handlers.set(type, callback),
      setPointerCapture: () => { captured = true; },
      hasPointerCapture: () => captured,
      releasePointerCapture: () => { captured = false; },
    },
    byId: () => ({}), mapCellFromPointer: (event) => event.cell,
    beginBulkDrag: () => false, drawMap() {}, renderAll() {}, updateSaveState() {}, normalizeSelections() {},
    scheduleResolution: () => { resolutions += 1; },
  });
  for (const name of [
    "changeSnapshot", "restoreChangeSnapshot", "beginChange", "undo", "redo", "normalizedCellRect",
    "paintGround", "paintGroundRectangle", "beginGroundRectangle", "updateGroundRectangle", "finishGroundRectangle",
  ]) {
    const start = source.indexOf(`function ${name}(`);
    const next = source.slice(start + 1).search(/\n(?:async )?function /);
    assert.notEqual(start, -1, name);
    assert.notEqual(next, -1, name);
    vm.runInContext(source.slice(start, start + 1 + next), context);
  }
  const start = source.indexOf('mapCanvas.addEventListener("pointerdown"');
  const end = source.indexOf('mapCanvas.addEventListener("contextmenu"', start);
  assert.notEqual(start, -1);
  assert.notEqual(end, -1);
  vm.runInContext(source.slice(start, end), context);
  const pointer = (type, cell) => handlers.get(type)({ button: 0, pointerId: 1, cell });
  const stroke = (cells, tool = "brush") => {
    state.groundTool = tool;
    pointer("pointerdown", cells[0]);
    for (const cell of cells.slice(1)) pointer("pointermove", cell);
    pointer("pointerup", cells.at(-1));
    assert.equal(captured, false);
    assert.equal(state.pointerDrag, null);
    assert.equal(state.pointerStroke, null);
  };
  return { state, context, stroke, resolutions: () => resolutions };
}

const copy = (value) => JSON.parse(JSON.stringify(value));

test("brush skips every edge and corner, even when a stroke starts on an edge", () => {
  const { state, context, stroke } = editor();
  const original = copy(state.data);
  const [width, height] = state.data.size;
  const cells = [];
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (x === 0 || y === 0 || x === width - 1 || y === height - 1) cells.push([x, y]);
    }
  }
  cells.push([1, 1], [width - 2, height - 2]);
  stroke(cells);
  const expected = copy(original);
  expected.grounds[1][1] = "floor";
  expected.grounds[height - 2][width - 2] = "floor";
  assert.deepEqual(copy(state.data), expected);
  assert.equal(state.history.length, 1);
  assert.equal(state.dirty, true);
  context.undo();
  assert.deepEqual(copy(state.data), original);
});

test("rectangle crossing all edges paints only the interior and supports one-step undo/redo", () => {
  const { state, context, stroke } = editor("sea", [32, 24]);
  const original = copy(state.data);
  stroke([[31, 23], [0, 0]], "rectangle");
  const expected = copy(original);
  for (let y = 1; y < 23; y += 1) {
    for (let x = 1; x < 31; x += 1) expected.grounds[y][x] = "floor";
  }
  assert.deepEqual(copy(state.data), expected);
  assert.equal(state.history.length, 1);
  assert.equal(state.groundPaintRect, null);
  context.undo();
  assert.deepEqual(copy(state.data), original);
  context.redo();
  assert.deepEqual(copy(state.data), expected);
});

test("partial rectangles keep both edge cells and cells outside the selection untouched", () => {
  const { state, stroke } = editor();
  const expected = copy(state.data);
  stroke([[0, 4], [3, 6]], "rectangle");
  for (let y = 4; y <= 6; y += 1) {
    for (let x = 1; x <= 3; x += 1) expected.grounds[y][x] = "floor";
  }
  assert.deepEqual(copy(state.data), expected);
});

test("edge-only brush, rectangle and single-cell rectangle leave no edit or undo entry", () => {
  for (const [tool, cells] of [
    ["brush", [[0, 0], [0, 7], [0, 14]]],
    ["rectangle", [[0, 0], [15, 0]]],
    ["rectangle", [[15, 14]]],
  ]) {
    const { state, stroke, resolutions } = editor();
    const original = copy(state.data);
    stroke(cells, tool);
    assert.deepEqual(copy(state.data), original);
    assert.equal(state.history.length, 0);
    assert.equal(state.dirty, false);
    assert.equal(resolutions(), 0);
  }
});

test("the tileset's first ground can repair invalid edges using either paint tool", () => {
  for (const tool of ["brush", "rectangle"]) {
    const { state, context, stroke } = editor("wall");
    state.data.grounds[0][0] = "floor";
    state.data.grounds[0][2] = "floor";
    const original = copy(state.data);
    stroke([[0, 0], [2, 0]], tool);
    assert.deepEqual(copy(state.data), original);
    state.groundId = "wall";
    stroke([[0, 0], [2, 0]], tool);
    assert.equal(state.data.grounds[0][0], "wall");
    assert.equal(state.data.grounds[0][2], "wall");
    assert.equal(state.history.length, 1);
    context.undo();
    assert.deepEqual(copy(state.data), original);
  }
});
