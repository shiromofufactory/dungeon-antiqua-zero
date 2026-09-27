import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../tools/map_editor/static/app.js", import.meta.url), "utf8");

function functionSource(name) {
  const start = source.indexOf(`function ${name}(`);
  assert.notEqual(start, -1);
  const next = source.indexOf("\nfunction ", start + 1);
  assert.notEqual(next, -1);
  return source.slice(start, next);
}

test("arrival rename keeps external ID changes through edits and undo", () => {
  const state = {
    data: {
      map_id: "floor_b",
      arrival_points: [{ id: "from_a" }],
      sites: [{ destination: { map_id: "floor_b", arrival_id: "from_a" } }],
    },
    siteNamesJa: {},
    selectedArrivalId: "from_a",
    savedArrivalIds: new Set(["from_a"]),
    arrivalIdRenames: {},
  };
  const context = vm.createContext({
    state,
    currentArrival: () => state.data.arrival_points.find((arrival) => arrival.id === state.selectedArrivalId),
    commit: (mutator) => mutator(),
  });
  for (const name of ["changeSnapshot", "restoreChangeSnapshot", "updateArrivalField"]) {
    vm.runInContext(functionSource(name), context);
  }

  const original = context.changeSnapshot();
  context.updateArrivalField("id", "from_b");
  assert.equal(state.arrivalIdRenames.from_a, "from_b");
  assert.equal(state.data.sites[0].destination.arrival_id, "from_b");
  context.updateArrivalField("id", "from_c");
  assert.deepEqual(JSON.parse(JSON.stringify(state.arrivalIdRenames)), { from_a: "from_c" });

  context.restoreChangeSnapshot(original);
  assert.deepEqual(JSON.parse(JSON.stringify(state.arrivalIdRenames)), {});
  assert.equal(state.data.sites[0].destination.arrival_id, "from_a");
  state.selectedArrivalId = "from_a";
  context.updateArrivalField("id", "from_b");
  context.updateArrivalField("id", "from_a");
  assert.deepEqual(JSON.parse(JSON.stringify(state.arrivalIdRenames)), {});
});
