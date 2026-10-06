import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../tools/map_editor/static/app.js", import.meta.url), "utf8");
const layers = ["object", "object_y_sorted", "object_foreground", "object_overlay"];

// Exercise the production functions without booting the editor's DOM/network shell.
function editor() {
  const definitions = layers.map((layer, index) => ({
    id: `definition_${index}`, default_draw_group: layer, size: [1, 1],
    cells: [{ offset: [0, 0], tile: [index, 0] }],
  }));
  const state = {
    tab: "object", objectLayer: "object_y_sorted", objectId: definitions[1].id,
    selectedInstanceId: null, bulkSelection: [], zoom: 1,
    flagOptions: [{ flag_id: "story.open", note: "扉が開いた" }, { flag_id: "story.done", note: "完了" }],
    tileset: { objects: definitions, grounds: [] },
    data: {
      size: [16, 15],
      objects: definitions.map((definition, index) => ({ id: `instance_${index}`, definition_id: definition.id, origin: [2, 2], order: index })),
      sites: [], arrival_points: [], actors: [{ id: "elder", position: [2, 2] }], event_triggers: [],
    },
  };
  const pane = { innerHTML: "" };
  const context = vm.createContext({
    state, OBJECT_LAYERS: [...layers.map((layer) => [layer, layer]), ["all", "全て"]],
    document: { querySelectorAll: () => [] }, byId: () => pane,
    escapeHtml: String, standaloneTriggers: () => [],
    isBulkSelected: (kind, id) => state.bulkSelection.some((item) => item.kind === kind && item.id === id),
    frameTile: (cell) => cell.draw_group, drawSourceTile: () => {},
    renderAll: () => {}, renderPalette: () => {}, renderInspector: () => {}, drawPaletteThumbs: () => {},
    drawMap: () => {}, updateToolStatus: () => {}, showToast: () => {}, performance: { now: () => 0 },
    ensureActorTrigger: () => {}, commit: (mutator) => mutator(), uniqueInstanceId: () => "new_instance",
  });
  for (const name of [
    "addPoint", "objectDefinition", "objectLayerEditable", "objectPlacementSignature", "objectPlacementConflict",
    "objectBottom", "objectDrawGroupOrder", "objectDrawGroupLabel", "compareObjectsBackToFront",
    "instanceOccupies", "instanceAt", "currentInstance", "bulkItemExists", "normalizeSelections",
    "clearSingleSelections", "clearBulkSelection", "handlePaletteAction", "renderPalette",
    "mapSelectionCandidatesAt", "pointInCellRect", "rangeSelectionItems", "placeObject", "validObjectOrigin",
    "candidatePosition", "validBulkDelta", "drawMapObjectCell", "drawObjectOutline", "drawTabCellHighlights",
    "beginObjectDrag",
    "updateObjectField", "updateVisibilityField", "updateActorField", "currentActor", "visibilityInspector", "objectFlagOptions", "attachSiteToObject",
  ]) {
    const start = source.indexOf(`function ${name}(`);
    assert.notEqual(start, -1, name);
    const tail = source.slice(start + 1);
    const next = tail.search(/\n(?:async )?function /);
    vm.runInContext(source.slice(start, start + 1 + next), context);
  }
  return { context, state, definitions, pane };
}

const ids = (items) => Array.from(items, (item) => item.id);

test("object inspector omits manual draw-order controls but retains object details and deletion", () => {
  const inspector = source.slice(source.indexOf("function renderInspector("), source.indexOf("function renderIssues("));
  assert.doesNotMatch(inspector, /同一下端内の順序|前面へ|背面へ/);
  assert.doesNotMatch(source, /object-front|object-back/);
  assert.match(inspector, /instance\.definition_id/);
  assert.match(inspector, /instance\.origin/);
  assert.match(inspector, /objectDrawGroupLabel/);
  assert.match(inspector, /data-action="delete-instance"/);
});

test("visibility edits, removal and undo preserve the flag ID and boolean", () => {
  const { context, state } = editor();
  state.selectedInstanceId = "instance_1";
  state.history = [];
  state.future = [];
  context.scheduleResolution = () => {};
  for (const name of ["beginChange", "finishChange", "commit", "undo", "redo", "changeSnapshot", "restoreChangeSnapshot"]) {
    const start = source.indexOf(`function ${name}(`);
    const next = source.slice(start + 1).search(/\n(?:async )?function /);
    vm.runInContext(source.slice(start, start + 1 + next), context);
  }
  const condition = () => JSON.parse(JSON.stringify(state.data.objects[1].visibility_condition ?? null));
  context.updateObjectField("visibility_enabled", "true");
  assert.deepEqual(condition(), { flag_id: "story.open", value: true });
  context.updateObjectField("flag_value", "false");
  context.updateObjectField("flag_id", "story.done");
  assert.deepEqual(condition(), { flag_id: "story.done", value: false });
  context.updateObjectField("visibility_enabled", "false");
  assert.equal(condition(), null);
  context.undo();
  assert.deepEqual(condition(), { flag_id: "story.done", value: false });
  context.redo();
  assert.equal(condition(), null);
});

test("visibility controls offer only a declared flag and ON/OFF and explain empty catalogs", () => {
  const { context, state } = editor();
  const instance = state.data.objects[1];
  instance.visibility_condition = { flag_id: "story.open", value: false };
  const html = context.visibilityInspector(instance);
  assert.match(html, /data-object-field="flag_id"/);
  assert.match(html, /story.open.*扉が開いた/);
  assert.match(html, /value="false" selected>OFFのとき/);
  assert.doesNotMatch(html, /member_in_party|item_at_least|condition-type/);
  state.flagOptions = [];
  delete instance.visibility_condition;
  assert.match(context.visibilityInspector(instance), /value="true"\s+disabled/);
  assert.match(context.visibilityInspector(instance), /イベントエディタで登録/);
});

test("all actor kinds can edit and remove flag conditions, preserve them on kind change, and undo", () => {
  const { context, state } = editor();
  state.selectedActorId = "elder";
  state.history = [];
  state.future = [];
  context.scheduleResolution = () => {};
  for (const name of ["beginChange", "finishChange", "commit", "undo", "redo", "changeSnapshot", "restoreChangeSnapshot"]) {
    const start = source.indexOf(`function ${name}(`);
    const next = source.slice(start + 1).search(/\n(?:async )?function /);
    vm.runInContext(source.slice(start, start + 1 + next), context);
  }
  const actor = () => state.data.actors[0];
  const condition = () => JSON.parse(JSON.stringify(actor().visibility_condition ?? null));
  for (const kind of ["stationary", "roaming", "prop", "treasure"]) {
    context.updateActorField("kind", kind);
    context.updateActorField("visibility_enabled", "true");
    context.updateActorField("flag_id", "story.done");
    context.updateActorField("flag_value", "false");
    assert.deepEqual(condition(), { flag_id: "story.done", value: false });
    assert.match(context.visibilityInspector(actor(), "actor"), /data-actor-field="flag_value"/);
    context.updateActorField("visibility_enabled", "false");
    assert.equal(condition(), null);
    context.undo();
    assert.deepEqual(condition(), { flag_id: "story.done", value: false });
    context.redo();
    assert.equal(condition(), null);
  }
  context.updateActorField("visibility_enabled", "true");
  context.updateActorField("kind", "roaming");
  assert.deepEqual(condition(), { flag_id: "story.open", value: true });
  delete actor().visibility_condition;
  state.flagOptions = [];
  context.updateActorField("visibility_enabled", "true");
  assert.equal(condition(), null);
  assert.match(context.visibilityInspector(actor(), "actor"), /value="true"\s+disabled/);
  assert.match(source, /visibilityInspector\(actor, "actor"\)/);
});

test("facility objects cannot create an exit and the inspector limits attachment to world maps", () => {
  const { context, state } = editor();
  state.selectedInstanceId = "instance_1";
  for (const profile of ["town", "dungeon"]) {
    state.data.profile = profile;
    context.attachSiteToObject();
    assert.equal(state.data.sites.length, 0);
  }
  const inspector = source.slice(source.indexOf("function renderInspector("), source.indexOf("function renderIssues("));
  assert.match(inspector, /isWorld \? `<div class="row"[^\n]+attach-site/);
  assert.doesNotMatch(inspector, /\$\{siteLabel\}として設定|移動口として設定/);
});

test("layer selection restricts palette, hit testing and range selection", () => {
  const { context, state, pane } = editor();
  context.renderPalette();
  assert.match(pane.innerHTML, /data-id="definition_1"/);
  assert.doesNotMatch(pane.innerHTML, /data-id="definition_0"/);
  assert.match(pane.innerHTML, /data-object-thumb="1"/);
  assert.equal(context.instanceAt(2, 2).id, "instance_1");
  assert.deepEqual(ids(context.mapSelectionCandidatesAt([2, 2])), ["instance_1"]);
  assert.deepEqual(ids(context.rangeSelectionItems({ left: 2, right: 2, top: 2, bottom: 2 })), ["instance_1"]);
  state.objectLayer = "object_foreground";
  assert.equal(context.instanceAt(2, 2).id, "instance_2");
});

test("all mode disables placement, palette and single selection but selects object groups", () => {
  const { context, state, pane } = editor();
  state.objectLayer = "all";
  context.normalizeSelections();
  context.renderPalette();
  assert.equal(state.objectId, null);
  assert.equal((pane.innerHTML.match(/type="button" disabled data-id=/g) || []).length, 4);
  assert.doesNotMatch(pane.innerHTML, /data-action="select-object-definition"/);
  context.handlePaletteAction({ dataset: { action: "select-object-definition", id: "definition_0" } });
  assert.equal(state.objectId, null);
  state.objectId = "definition_0";
  context.placeObject(4, 4);
  assert.equal(state.data.objects.length, 4);
  assert.equal(context.instanceAt(2, 2), null);
  assert.equal(context.beginObjectDrag({}, [2, 2]), false);
  assert.deepEqual(ids(context.mapSelectionCandidatesAt([2, 2])), []);
  assert.deepEqual(ids(context.rangeSelectionItems({ left: 2, right: 2, top: 2, bottom: 2 })), ids(state.data.objects));
});

test("switching layer clears single and group selections", () => {
  const { context, state } = editor();
  state.selectedInstanceId = "instance_1";
  state.bulkSelection = [{ kind: "object", id: "instance_1" }];
  context.handlePaletteAction({ dataset: { action: "select-object-layer", layer: "object_foreground" } });
  context.normalizeSelections();
  assert.equal(state.selectedInstanceId, null);
  assert.equal(state.bulkSelection.length, 0);
  assert.equal(state.objectId, "definition_2");
});

test("ghost opacity is isolated to other object layers", () => {
  const { context, state } = editor();
  const alphas = [];
  const canvas = { globalAlpha: .8, save() { this.saved = this.globalAlpha; }, restore() { this.globalAlpha = this.saved; } };
  context.drawSourceTile = () => alphas.push(canvas.globalAlpha);
  for (const layer of layers) context.drawMapObjectCell(canvas, { draw_group: layer, position: [2, 2] }, 16, 0);
  assert.deepEqual(alphas, [.2, .8, .2, .2]);
  assert.equal(canvas.globalAlpha, .8);
  state.objectLayer = "all";
  context.drawMapObjectCell(canvas, { draw_group: "object", position: [2, 2] }, 16, 0);
  assert.equal(alphas.at(-1), .8);
});

test("pink outlines omit other layers and shared constituent-cell edges", () => {
  const { context, state, definitions } = editor();
  definitions[1].size = [2, 2];
  definitions[1].cells = [{ offset: [0, 0] }, { offset: [1, 0] }, { offset: [0, 1] }];
  let fills = 0;
  const segments = [];
  const canvas = { save() {}, restore() {}, beginPath() {}, stroke() {},
    fillRect() { fills += 1; }, moveTo(x, y) { this.start = [x, y]; },
    lineTo(x, y) { segments.push([...this.start, x, y]); } };
  context.drawTabCellHighlights(canvas, 16);
  assert.equal(fills, 3);
  assert.equal(segments.length, 8);
  assert.ok(!segments.some((edge) => JSON.stringify(edge) === JSON.stringify([48, 32, 48, 48])));
  state.objectLayer = "all";
  fills = 0;
  context.drawTabCellHighlights(canvas, 16);
  assert.equal(fills, 6);
});

test("placement and single movement reject exact same-layer cells, not shared origins", () => {
  const { context, state, definitions } = editor();
  state.data.objects = [state.data.objects[0]];
  assert.ok(context.objectPlacementConflict(definitions[0], [2, 2]));
  assert.equal(context.objectPlacementConflict(definitions[1], [2, 2]), null);
  state.objectId = definitions[1].id;
  context.placeObject(2, 2);
  assert.equal(state.data.objects.length, 2);
  const moving = { id: "moving", definition_id: definitions[0].id, origin: [3, 2], order: 3 };
  assert.equal(context.validObjectOrigin(moving, 2, 2), false);
  definitions[0].cells.push({ offset: [1, 0] });
  definitions[0].size = [2, 1];
  assert.equal(context.validObjectOrigin(moving, 3, 2), true);
});

test("bulk movement uses exact cell signatures and layer, and retains bounds checks", () => {
  const { context, state } = editor();
  state.data.objects = [state.data.objects[0], { id: "moving", definition_id: "definition_0", origin: [3, 2], order: 5 }];
  state.pointerDrag = { descriptors: [{ kind: "object", id: "moving", position: [3, 2] }] };
  assert.equal(context.validBulkDelta([-1, 0]), false);
  state.data.objects[1].definition_id = "definition_1";
  assert.equal(context.validBulkDelta([-1, 0]), true);
  assert.equal(context.validBulkDelta([-4, 0]), false);
  assert.equal(context.validBulkDelta([20, 0]), false);
});

test("different definitions and origins cannot bypass the exact-overlap check", () => {
  const { context, state, definitions } = editor();
  const shifted = { ...definitions[0], id: "shifted", size: [2, 1], cells: [{ offset: [1, 0] }] };
  state.tileset.objects.push(shifted);
  assert.ok(context.objectPlacementConflict(shifted, [1, 2]));
});
