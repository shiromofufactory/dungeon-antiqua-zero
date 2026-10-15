import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../tools/map_editor/static/app.js", import.meta.url), "utf8");
const copy = (value) => JSON.parse(JSON.stringify(value));
const ids = (records) => Array.from(records, (record) => record.id);
const object = (id, origin, definition_id = "square") => ({ id, origin, definition_id, order: 0 });
const trigger = (id, anchor, offsets = [[0, 0]]) => ({ id, anchor, offsets, event_id: "story.shared" });

function editor(horizontal = "right", vertical = "down") {
  const state = {
    tab: "event", resizeHorizontal: horizontal, resizeVertical: vertical,
    history: [], future: [], siteNamesJa: {}, siteOptions: [], arrivalIdRenames: {}, bulkSelection: [],
    tileset: {
      grounds: [{ id: "base" }],
      objects: [
        { id: "square", size: [2, 2], cells: [[0, 0], [1, 0], [0, 1], [1, 1]].map((offset) => ({ offset })) },
        { id: "sparse", size: [3, 3], cells: [{ offset: [2, 2] }] },
      ],
    },
    data: {
      size: [24, 22], grounds: Array.from({ length: 22 }, (_, y) => Array.from({ length: 24 }, (_, x) => `${x},${y}`)),
      objects: [], sites: [], arrival_points: [], actors: [], event_triggers: [],
    },
  };
  const inputs = { "map-width": { value: "16" }, "map-height": { value: "15" } };
  const context = vm.createContext({
    state, MIN_MAP_WIDTH: 16, MIN_MAP_HEIGHT: 15, byId: (id) => inputs[id],
    showToast: () => assert.fail("Unexpected invalid dimensions"), scheduleResolution() {},
    renderAll: () => context.normalizeSelections(),
  });
  for (const name of [
    "actorCells", "actorIntersectsMap", "objectDefinition", "objectIntersectsMap", "currentInstance", "objectLayerEditable", "bulkItemExists", "standaloneTriggers", "normalizeSelections",
    "changeSnapshot", "restoreChangeSnapshot", "beginChange", "finishChange", "commit", "undo", "redo",
    "addPoint", "triggerAnchorPosition", "triggerPositions", "removeOutsideMapPlacements", "resizeMap",
  ]) {
    const start = source.indexOf(`function ${name}(`);
    const next = source.slice(start + 1).search(/\n(?:async )?function /);
    assert.notEqual(start, -1, name);
    assert.notEqual(next, -1, name);
    vm.runInContext(source.slice(start, start + 1 + next), context);
  }
  return { state, context, inputs };
}

for (const horizontal of ["left", "right"]) {
  for (const vertical of ["up", "down"]) {
    test(`shrinking ${horizontal}/${vertical} removes only fully outside objects and supports one-step undo/redo`, () => {
      const { state, context } = editor(horizontal, vertical);
      const dx = horizontal === "left" ? -8 : 0;
      const dy = vertical === "up" ? -7 : 0;
      const originalPosition = ([x, y]) => [x - dx, y - dy];
      state.data.objects = [
        object("inside", originalPosition([8, 8])),
        object("outside_x", originalPosition([horizontal === "left" ? -2 : 16, 8])),
        object("outside_y", originalPosition([8, vertical === "up" ? -2 : 15])),
        object("partial", originalPosition([horizontal === "left" ? -1 : 15, 8])),
      ];
      state.selectedInstanceId = "outside_x";
      state.bulkSelection = [{ kind: "object", id: "outside_x" }, { kind: "object", id: "inside" }];
      const before = copy(state.data);
      context.resizeMap();
      assert.deepEqual(ids(state.data.objects), ["inside", "partial"]);
      assert.deepEqual(copy(state.data.objects[0].origin), [8, 8]);
      assert.equal(state.data.grounds[0][0], `${-dx},${-dy}`);
      assert.deepEqual(copy(state.data.size), [16, 15]);
      assert.equal(state.selectedInstanceId, null);
      assert.deepEqual(ids(state.bulkSelection), ["inside"]);
      assert.equal(state.history.length, 1);
      assert.equal(state.dirty, true);
      const after = copy(state.data);
      context.undo();
      assert.deepEqual(copy(state.data), before);
      context.redo();
      assert.deepEqual(copy(state.data), after);
    });
  }
}

test("object bounds use actual constituent cells and retain undefined definitions and border cells", () => {
  const { state, context } = editor("left", "up");
  state.data.objects = [
    object("cell_inside", [6, 5], "sparse"), // New origin [-2,-2], sole cell [0,0].
    object("only_empty_area_inside", [22, 20], "sparse"), // New origin [14,13], sole cell [16,15].
    object("unknown", [1, 1], "missing"),
  ];
  context.resizeMap();
  assert.deepEqual(ids(state.data.objects), ["cell_inside", "unknown"]);
  assert.deepEqual(copy(state.data.objects[0].origin), [-2, -2]);
});

test("resize removes outside actors and trigger cells and cascades deleted anchors without deleting event definitions", () => {
  const { state, context } = editor();
  state.data.objects = [object("inside", [3, 3]), object("partial", [15, 5]), object("outside", [18, 4])];
  state.data.actors = [{ id: "border", position: [15, 14] }, { id: "outside", position: [4, 18] }];
  state.data.event_triggers = [
    trigger("cell_inside", { kind: "cell", position: [3, 4] }),
    trigger("cell_outside", { kind: "cell", position: [16, 4] }),
    trigger("targets_outside", { kind: "cell", position: [15, 8] }, [[1, 0], [2, 0]]),
    trigger("partial_targets", { kind: "cell", position: [15, 9] }, [[0, 0], [1, 0]]),
    trigger("outside_anchor_inside_target", { kind: "cell", position: [17, 10] }, [[-2, 0]]),
    trigger("object_partial", { kind: "object", object_id: "partial" }, [[0, 0], [1, 0]]),
    trigger("object_targets_outside", { kind: "object", object_id: "inside" }, [[20, 0]]),
    trigger("deleted_object", { kind: "object", object_id: "outside" }, [[-15, 0]]),
    trigger("actor_inside", { kind: "actor", actor_id: "border" }),
    trigger("deleted_actor", { kind: "actor", actor_id: "outside" }, [[0, -15]]),
  ];
  state.eventOptions = ["story.shared"];
  state.data.sites = [
    { id: "kept", anchor: { kind: "object", object_id: "inside" } },
    { id: "removed", anchor: { kind: "object", object_id: "outside" } },
  ];
  state.siteNamesJa = { kept: "残る拠点", removed: "削除される拠点" };
  state.siteOptions = ["kept", "removed", "other_map"];
  state.selectedActorId = "outside";
  state.selectedTriggerId = "deleted_actor";
  const before = context.changeSnapshot();
  context.resizeMap();
  assert.deepEqual(ids(state.data.actors), ["border"]);
  assert.deepEqual(ids(state.data.event_triggers), [
    "cell_inside", "partial_targets", "outside_anchor_inside_target", "object_partial", "actor_inside",
  ]);
  assert.deepEqual(copy(state.data.event_triggers[1].offsets), [[0, 0], [1, 0]]);
  assert.deepEqual(ids(state.data.sites), ["kept"]);
  assert.deepEqual(copy(state.siteNamesJa), { kept: "残る拠点" });
  assert.deepEqual(Array.from(state.siteOptions), ["kept", "other_map"]);
  assert.equal(state.selectedActorId, null);
  assert.equal(state.selectedTriggerId, null);
  assert.deepEqual(state.eventOptions, ["story.shared"]);
  context.undo();
  assert.equal(context.changeSnapshot(), before);
});

test("left/up expansion shifts all placements without removing them and fills new ground with the base", () => {
  const { state, context, inputs } = editor("left", "up");
  inputs["map-width"].value = "28";
  inputs["map-height"].value = "25";
  state.data.objects = [object("edge", [22, 20])];
  state.data.actors = [{ id: "edge", position: [23, 21] }];
  state.data.event_triggers = [trigger("edge", { kind: "cell", position: [23, 21] })];
  state.data.arrival_points = [{ id: "arrival", position: [2, 2] }];
  state.data.sites = [{ id: "site", anchor: { kind: "cell", position: [2, 2] } }];
  context.resizeMap();
  assert.deepEqual(copy(state.data.objects[0].origin), [26, 23]);
  assert.deepEqual(copy(state.data.actors[0].position), [27, 24]);
  assert.deepEqual(copy(state.data.event_triggers[0].anchor.position), [27, 24]);
  assert.deepEqual(copy(state.data.arrival_points[0].position), [6, 5]);
  assert.deepEqual(copy(state.data.sites[0].anchor.position), [6, 5]);
  assert.equal(state.data.grounds[3][4], "0,0");
  assert.equal(state.data.grounds[0][0], "base");
});

test("resize retains a character's visible head and its actor trigger, and undo restores every placement", () => {
  const { state, context } = editor();
  state.data.actors = [
    { id: "head", kind: "stationary", position: [5, 15] },
    { id: "outside", kind: "roaming", position: [5, 16] },
    { id: "prop", kind: "prop", position: [6, 15] },
  ];
  state.data.event_triggers = state.data.actors.map((actor) => trigger(actor.id, { kind: "actor", actor_id: actor.id }));
  const before = copy(state.data);
  context.resizeMap();
  assert.deepEqual(ids(state.data.actors), ["head"]);
  assert.deepEqual(ids(state.data.event_triggers), ["head"]);
  context.undo();
  assert.deepEqual(copy(state.data), before);
});
