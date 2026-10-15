import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../tools/map_editor/static/app.js", import.meta.url), "utf8");

test("trigger offsets remain editable with Shift and left click", () => {
  assert.doesNotMatch(source, /data-action="edit-trigger-offsets"/);
  let pointerDown;
  const calls = [];
  const state = { tab: "event", hoveredCell: null, bulkSelection: [] };
  const context = vm.createContext({
    state,
    mapCanvas: { addEventListener: (_type, callback) => { pointerDown = callback; } },
    mapCellFromPointer: () => [3, 4],
    rememberMapPointer() {},
    currentTrigger: () => ({ id: "trigger_1" }),
    toggleTriggerOffset: (cell) => calls.push(["offset", ...cell]),
    beginBulkDrag: () => { assert.fail("Shift click should edit an offset before starting a drag"); },
    handleEventCell: () => { assert.fail("Shift click should not select or create a trigger"); },
  });
  const start = source.indexOf('mapCanvas.addEventListener("pointerdown"');
  const end = source.indexOf("\n});", start);
  assert.notEqual(start, -1);
  assert.notEqual(end, -1);
  vm.runInContext(source.slice(start, end + 4), context);
  pointerDown({ button: 0, shiftKey: true });
  assert.deepEqual(calls, [["offset", 3, 4]]);
});
