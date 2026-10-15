import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../tools/map_editor/static/app.js", import.meta.url), "utf8");
const copy = (value) => JSON.parse(JSON.stringify(value));

function editor({ zoom = 1, size = [32, 24] } = {}) {
  const state = {
    data: { size, grounds: Array.from({ length: size[1] }, () => Array(size[0]).fill("base")) },
    tab: "ground", groundId: "floor", groundTool: "rectangle", zoom, paused: false,
    dirty: false, history: [], future: [], bulkSelection: [], siteNamesJa: {}, arrivalIdRenames: {},
    pointerDrag: null, pointerStroke: null, dragPointer: null, dragScrollTime: null,
    groundPaintRect: null, selectionRect: null,
  };
  const handlers = new Map();
  const windowHandlers = new Map();
  const documentHandlers = new Map();
  const movements = [];
  let scrollLeft = 0;
  let scrollTop = 0;
  let captured = null;
  let time = 0;
  let draws = 0;
  const viewport = {
    clientLeft: 1, clientTop: 1, clientWidth: 128, clientHeight: 96,
    getBoundingClientRect: () => ({ left: 100, top: 80 }),
    get scrollLeft() { return scrollLeft; },
    set scrollLeft(value) { scrollLeft = Math.max(0, Math.min(value, size[0] * 16 * zoom - 128)); },
    get scrollTop() { return scrollTop; },
    set scrollTop(value) { scrollTop = Math.max(0, Math.min(value, size[1] * 16 * zoom - 96)); },
  };
  const canvas = {
    width: size[0] * 16 * zoom, height: size[1] * 16 * zoom,
    getBoundingClientRect() {
      return { left: 101 - scrollLeft, top: 81 - scrollTop, bottom: 81 - scrollTop + this.height, width: this.width, height: this.height };
    },
    addEventListener: (kind, handler) => handlers.set(kind, handler),
    setPointerCapture: (id) => { captured = id; },
    hasPointerCapture: (id) => captured === id,
    releasePointerCapture: (id) => { captured = null; handlers.get("lostpointercapture")?.({ pointerId: id }); },
  };
  const document = { hidden: false, addEventListener: (kind, handler) => documentHandlers.set(kind, handler) };
  const context = vm.createContext({
    state, CELL_SIZE: 16, mapCanvas: canvas, document,
    window: { addEventListener: (kind, handler) => windowHandlers.set(kind, handler) },
    byId: (id) => id === "map-scroll" ? viewport : id === "map-canvas" ? canvas : {},
    performance: { now: () => time }, requestAnimationFrame() {},
    drawMap: () => { draws += 1; }, renderAll() {}, updateSaveState() {}, normalizeSelections() {},
    scheduleResolution() {}, beginBulkDrag: () => false, currentSingleSelectionItem: () => null,
    clearSingleSelections() {}, clearBulkSelection() {}, showToast() {}, selectAnyAt() {},
    rangeSelectionItems: () => [],
    dragObjectTo: (cell) => movements.push(["object", ...cell]),
    dragSiteAnchorTo: (cell) => movements.push(["site_anchor", ...cell]),
    dragBulkTo: (cell) => movements.push(["bulk", ...cell]),
  });
  for (const name of [
    "changeSnapshot", "restoreChangeSnapshot", "beginChange", "undo", "redo", "normalizedCellRect",
    "paintGround", "paintGroundRectangle", "beginGroundRectangle", "updateGroundRectangle", "finishGroundRectangle",
    "mapScrollBounds", "mapCellFromPointer", "rememberMapPointer", "stopMapAutoScroll", "mapDragScrollAmount",
    "updateMapAutoScroll", "updateMapPointer", "cancelMapPointer", "animationLoop",
    "beginRangeSelection", "updateRangeSelection",
  ]) {
    const start = source.indexOf(`function ${name}(`);
    assert.notEqual(start, -1, name);
    const next = source.slice(start + 1).search(/\n(?:async )?function /);
    assert.notEqual(next, -1, name);
    vm.runInContext(source.slice(start, start + 1 + next), context);
  }
  const start = source.indexOf('mapCanvas.addEventListener("pointerdown"');
  const end = source.indexOf('window.addEventListener("keydown"', start);
  vm.runInContext(source.slice(start, end), context);
  let last = { clientX: 125, clientY: 105, pointerId: 1, button: 0, preventDefault() {} };
  const pointer = (kind, x = last.clientX, y = last.clientY, button = last.button) => {
    last = { ...last, clientX: x, clientY: y, button };
    handlers.get(kind)(last);
  };
  const frame = (delta = 16) => { time += delta; context.animationLoop(time); };
  return { state, context, viewport, pointer, frame, handlers, windowHandlers, documentHandlers, document,
    movements, draws: () => draws };
}

test("actor drags can target one row below the canvas when its lower edge is visible", () => {
  const { state, context, viewport } = editor();
  viewport.scrollTop = 10000;
  const event = { clientX: 125, clientY: 190 };
  assert.deepEqual(copy(context.mapCellFromPointer(event, true)), [1, 23]);
  state.pointerDrag = { descriptors: [{ kind: "actor", id: "elder" }] };
  assert.deepEqual(copy(context.mapCellFromPointer(event, true)), [1, 24]);
  state.pointerDrag = { kind: "range_selection", draggableItem: { kind: "actor", id: "elder" } };
  assert.deepEqual(copy(context.mapCellFromPointer(event, true)), [1, 24]);
  viewport.scrollTop = 0;
  assert.deepEqual(copy(context.mapCellFromPointer(event, true)), [1, 5]);
});

test("a stationary pointer outside the viewport scrolls a rectangle and one undo restores its fill", () => {
  const { state, context, viewport, pointer, frame } = editor();
  const original = copy(state.data);
  pointer("pointerdown");
  frame();
  pointer("pointermove", 260, 200);
  assert.equal(state.groundPaintRect.right, 7);
  assert.equal(state.groundPaintRect.bottom, 5);
  for (let i = 0; i < 30; i += 1) frame();
  assert.ok(viewport.scrollLeft > 0 && viewport.scrollTop > 0);
  assert.ok(state.groundPaintRect.right > 7 && state.groundPaintRect.bottom > 5);
  const rect = copy(state.groundPaintRect);
  assert.deepEqual(copy(state.data), original);
  pointer("pointerup");
  assert.equal(state.history.length, 1);
  assert.equal(state.data.grounds[rect.bottom][rect.right], "floor");
  assert.equal(state.data.grounds[rect.bottom][rect.right + 1], "base");
  const stopped = [viewport.scrollLeft, viewport.scrollTop];
  frame();
  assert.deepEqual([viewport.scrollLeft, viewport.scrollTop], stopped);
  assert.equal(state.dragPointer, null);
  context.undo();
  assert.deepEqual(copy(state.data), original);
});

test("scrolling stops inside the viewport and handles all directions and map edges", () => {
  const { state, viewport, pointer, frame } = editor();
  pointer("pointerdown");
  frame();
  pointer("pointermove", 1000, 1000);
  for (let i = 0; i < 200; i += 1) frame();
  assert.equal(viewport.scrollLeft, 32 * 16 - 128);
  assert.equal(viewport.scrollTop, 24 * 16 - 96);
  assert.equal(state.groundPaintRect.right, 31);
  assert.equal(state.groundPaintRect.bottom, 23);
  pointer("pointermove", 160, 120);
  const stopped = [viewport.scrollLeft, viewport.scrollTop];
  frame();
  assert.deepEqual([viewport.scrollLeft, viewport.scrollTop], stopped);
  pointer("pointermove", 0, 0);
  for (let i = 0; i < 200; i += 1) frame();
  assert.equal(viewport.scrollLeft, 0);
  assert.equal(viewport.scrollTop, 0);
  assert.deepEqual(copy(state.hoveredCell), [0, 0]);
});

test("idle pointers and maps smaller than the viewport do not scroll", () => {
  for (const options of [{}, { size: [4, 3] }]) {
    const { state, viewport, pointer, frame } = editor(options);
    pointer("pointermove", 1000, 1000);
    frame();
    frame();
    assert.equal(viewport.scrollLeft, 0);
    assert.equal(viewport.scrollTop, 0);
    if (options.size) {
      pointer("pointerdown", 125, 105);
      frame();
      pointer("pointermove", 1000, 1000);
      for (let i = 0; i < 10; i += 1) frame();
      assert.equal(viewport.scrollLeft, 0);
      assert.equal(viewport.scrollTop, 0);
      assert.deepEqual(copy(state.hoveredCell), [3, 2]);
    }
  }
});

test("brushes paint the cells exposed by auto scrolling and retain one undo unit", () => {
  const { state, context, pointer, frame } = editor();
  const original = copy(state.data);
  state.groundTool = "brush";
  pointer("pointerdown", 125, 105);
  frame();
  pointer("pointermove", 260, 105);
  for (let i = 0; i < 20; i += 1) frame();
  const [lastX, lastY] = state.hoveredCell;
  for (let x = 7; x <= lastX; x += 1) assert.equal(state.data.grounds[lastY][x], "floor");
  pointer("pointerup");
  assert.equal(state.history.length, 1);
  context.undo();
  assert.deepEqual(copy(state.data), original);
});

test("auto scrolling continues while map animation is paused and respects zoom", () => {
  const { state, viewport, pointer, frame, draws } = editor({ zoom: 2 });
  state.paused = true;
  pointer("pointerdown");
  frame();
  pointer("pointermove", 260, 105);
  const before = draws();
  for (let i = 0; i < 20; i += 1) frame();
  assert.ok(viewport.scrollLeft > 0);
  assert.ok(draws() > before);
  assert.equal(state.hoveredCell[0], Math.floor((127 + viewport.scrollLeft) / 32));
});

test("range selections and all placement drag modes follow the newly exposed cells", () => {
  for (const kind of ["range_selection", "object", "site_anchor", "bulk", "single_selection"]) {
    const { state, pointer, frame, movements } = editor();
    pointer("pointerdown", 125, 105, 2);
    if (kind !== "range_selection") state.pointerDrag = { kind, pointerId: 1 };
    frame();
    pointer("pointermove", 260, 200, 2);
    for (let i = 0; i < 20; i += 1) frame();
    if (kind === "range_selection") {
      assert.ok(state.selectionRect.right > 7 && state.selectionRect.bottom > 5);
    } else {
      assert.ok(movements.at(-1)[1] > 7 && movements.at(-1)[2] > 5, kind);
    }
  }
});

test("cancel, capture loss, window blur and a hidden page stop scrolling and cancel rectangle previews", () => {
  for (const stop of ["pointercancel", "lostpointercapture", "blur", "visibilitychange"]) {
    const { state, viewport, pointer, frame, handlers, windowHandlers, documentHandlers, document } = editor();
    const original = copy(state.data);
    pointer("pointerdown");
    frame();
    pointer("pointermove", 260, 200);
    frame();
    if (stop === "blur") windowHandlers.get(stop)();
    else if (stop === "visibilitychange") { document.hidden = true; documentHandlers.get(stop)(); }
    else handlers.get(stop)();
    const stopped = [viewport.scrollLeft, viewport.scrollTop];
    frame();
    assert.deepEqual([viewport.scrollLeft, viewport.scrollTop], stopped);
    assert.deepEqual(copy(state.data), original);
    assert.equal(state.pointerDrag, null);
    assert.equal(state.groundPaintRect, null);
    assert.equal(state.dragPointer, null);
    assert.equal(state.history.length, 0);
  }
});

test("a second pointer cannot replace, end or cancel the active drag", () => {
  const { state, viewport, pointer, frame, handlers } = editor();
  pointer("pointerdown");
  frame();
  pointer("pointermove", 260, 200);
  const other = { pointerId: 2, clientX: 130, clientY: 110, button: 0 };
  for (const kind of ["pointerdown", "pointermove", "pointerup", "pointercancel", "lostpointercapture"]) {
    handlers.get(kind)(other);
    assert.equal(state.pointerDrag.pointerId, 1, kind);
    assert.equal(state.dragPointer.pointerId, 1, kind);
  }
  frame();
  assert.ok(viewport.scrollLeft > 0 && viewport.scrollTop > 0);
});
