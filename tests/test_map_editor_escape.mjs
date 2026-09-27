import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../tools/map_editor/static/app.js", import.meta.url), "utf8");

test("Escape selects the hovered map cell like a right click", () => {
  const start = source.indexOf("function rightClickWithEscape(event)");
  const end = source.indexOf("\nfunction ", start + 1);
  assert.notEqual(start, -1);
  assert.notEqual(end, -1);
  const state = {
    hoveredCell: [3, 4], bulkSelection: [], pointerDrag: null, pointerStroke: null,
  };
  const selected = [];
  let dialogOpen = false;
  const context = vm.createContext({
    state,
    document: { querySelector: () => dialogOpen ? {} : null },
    bulkItemOccupiesCell: (item) => item.occupies,
    selectAnyAt: (cell) => selected.push([...cell]),
  });
  vm.runInContext(source.slice(start, end), context);
  const key = (keyName, repeat = false) => {
    let prevented = false;
    const handled = context.rightClickWithEscape({
      key: keyName, repeat, preventDefault() { prevented = true; },
    });
    return { handled, prevented };
  };

  assert.deepEqual(key("Escape"), { handled: true, prevented: true });
  assert.deepEqual(selected, [[3, 4]]);
  state.bulkSelection = [{ occupies: true }];
  key("Escape");
  assert.equal(selected.length, 1);
  state.bulkSelection = [{ occupies: false }];
  key("Escape");
  assert.deepEqual(selected.at(-1), [3, 4]);
  dialogOpen = true;
  key("Escape");
  assert.equal(selected.length, 2);
  dialogOpen = false;
  key("Escape", true);
  assert.equal(selected.length, 2);
  assert.deepEqual(key("Enter"), { handled: false, prevented: false });
});
