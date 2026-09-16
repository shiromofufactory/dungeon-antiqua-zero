import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../tools/mapchip_metadata/static/app.js", import.meta.url), "utf8");
const css = readFileSync(new URL("../tools/mapchip_metadata/static/styles.css", import.meta.url), "utf8");
const htmlSource = readFileSync(new URL("../tools/mapchip_metadata/static/index.html", import.meta.url), "utf8");
const layers = [["object", "背面"], ["object_y_sorted", "通常"], ["object_foreground", "前面"], ["object_overlay", "最前面"]];
const layerClasses = ["map-layer-back", "map-layer-normal", "map-layer-front", "map-layer-top"];
const colors = Object.fromEntries(Array.from(css.matchAll(/(--[\w-]+):\s*(#[\da-f]{6});/gi), ([, variable, color]) => [variable, color]));

function editor() {
  const objects = layers.map(([layer], index) => ({
    id: `object_${index}`, default_draw_group: layer, size: [1, 1],
    cells: [{ offset: [0, 0], collision: "blocked", tile: [index, 0] }],
  }));
  objects.push({ ...objects[1], id: "normal_second" });
  const state = {
    tab: "object", objectLayer: "object_y_sorted", objectIndex: 1,
    groundIndex: 0, boundaryIndex: 0, choiceIndex: 0, frameIndex: 0,
    previewGrounds: Array(9).fill("plain"), selection: { x: 2, y: 3, width: 2, height: 1 },
    data: { objects, grounds: [{ id: "plain", boundaries: [], base_visual: null }] },
    objectOrigins: objects.map((object) => object.id), history: [], future: [], dirty: false,
  };
  const context = vm.createContext({
    state, OBJECT_LAYERS: layers, OBJECT_LAYER_CLASSES: Object.fromEntries(layers.map(([key], index) => [key, layerClasses[index]])),
    OBJECT_COLLISION_STATES: ["blocked", "passable", "passable_override"], OBJECT_COLLISION_LABELS: { blocked: "blocked", passable: "passable" },
    escapeHtml: String, activeVisual: () => null, renderObjectVisualEditor: () => "",
    mutateObjectVisual: () => false, mutateVisual: () => false, performance: { now: () => 0 },
    savePreviewSettings() {}, scheduleValidation() {}, showToast() {}, window: { confirm: () => true },
    renderAll: () => context.normalizeSelectionIndexes(), uniqueId: () => "new_object",
    document: { documentElement: {} }, getComputedStyle: () => ({ getPropertyValue: (variable) => colors[variable] }),
    byId: () => ({ querySelector: () => ({ focus: () => { context.focusedLayer = state.objectLayer; } }) }),
  });
  const colorStart = source.indexOf("const SOURCE_USAGE_COLORS =");
  vm.runInContext(source.slice(colorStart, source.indexOf(";", colorStart) + 1), context);
  for (const name of ["currentGround", "currentBoundary", "currentObject", "currentVisual", "normalizeSelectionIndexes",
    "objectLayerClass", "renderDefinitionList", "renderObjectLayerSelect", "renderObjectEditor", "handleChange",
    "handleAction", "commit", "undo", "redo", "reorderDefinitions", "addVisualUsage", "sourceTileUsage", "drawSourceUsage"]) {
    const start = source.indexOf(`function ${name}(`);
    assert.notEqual(start, -1, name);
    const next = source.slice(start + 1).search(/\n(?:async )?function /);
    assert.notEqual(next, -1, name);
    vm.runInContext(source.slice(start, start + 1 + next), context);
  }
  return { context, state };
}

test("layer controls precede filtered object list and ID/width/height share a compact row", () => {
  const { context } = editor();
  const html = context.renderObjectEditor();
  assert.doesNotMatch(html, /起点は左上/);
  assert.ok(html.indexOf('data-change="object-layer"') < html.indexOf('class="definition-list"'));
  assert.match(html, /data-action="select-object" data-index="1"/);
  assert.match(html, /data-action="select-object" data-index="4"/);
  assert.doesNotMatch(html, /data-action="select-object" data-index="[023]"/);
  const identity = html.match(/<div class="object-identity-grid">([\s\S]*?)<\/div>\s*<label class="object-interact-toggle">/)[1];
  for (const field of ["object-id", "object-width", "object-height"]) assert.ok(identity.includes(`data-change="${field}"`));
  assert.doesNotMatch(identity, /field full|object-group/);
});

test("filtering selects matching original index without changing metadata or creating undo history", () => {
  const { context, state } = editor();
  const before = JSON.stringify(state.data);
  context.handleChange({ dataset: { change: "object-layer" }, value: "object_foreground" });
  assert.equal(context.currentObject().id, "object_2");
  assert.equal(state.objectIndex, 2);
  assert.equal(context.focusedLayer, "object_foreground");
  assert.equal(JSON.stringify(state.data), before);
  assert.equal(state.dirty, false);
  assert.equal(state.history.length, 0);
  context.handleAction({ dataset: { action: "select-object", index: "0" } });
  assert.equal(state.objectIndex, 2);
  context.handleChange({ dataset: { change: "object-layer" }, value: "invalid" });
  assert.equal(state.objectLayer, "object_foreground");
});

test("object filtering does not reset ground visual selection when that layer has no objects", () => {
  const { context, state } = editor();
  state.tab = "ground";
  state.objectLayer = "object_overlay";
  state.data.objects = [];
  state.choiceIndex = 1;
  state.frameIndex = 1;
  context.activeVisual = () => ({ choices: [{ frames: [] }, { frames: [{}, {}] }] });
  context.normalizeSelectionIndexes();
  context.normalizeSelectionIndexes();
  assert.equal(state.choiceIndex, 1);
  assert.equal(state.frameIndex, 1);
});

test("empty layer shows filter and creation controls, new objects inherit displayed layer", () => {
  const { context, state } = editor();
  state.data.objects = state.data.objects.filter((object) => object.default_draw_group !== "object_overlay");
  context.handleChange({ dataset: { change: "object-layer" }, value: "object_overlay" });
  assert.equal(context.currentObject(), null);
  const html = context.renderObjectEditor();
  assert.match(html, /data-change="object-layer"/);
  assert.match(html, /data-action="add-object"/);
  assert.doesNotMatch(html, /data-change="object-id"|data-change="object-group"/);
  context.handleAction({ dataset: { action: "add-object" } });
  assert.equal(context.currentObject().default_draw_group, "object_overlay");
  context.undo();
  assert.equal(context.currentObject(), null);
  context.redo();
  assert.equal(context.currentObject().default_draw_group, "object_overlay");
});

test("rectangle generation in an empty layer inherits filter and does not overwrite hidden objects", () => {
  const { context, state } = editor();
  state.data.objects = state.data.objects.filter((object) => object.default_draw_group !== "object_foreground");
  const before = JSON.stringify(state.data.objects);
  context.handleChange({ dataset: { change: "object-layer" }, value: "object_foreground" });
  context.handleAction({ dataset: { action: "object-from-selection" } });
  assert.equal(context.currentObject().default_draw_group, "object_foreground");
  assert.deepEqual(Array.from(context.currentObject().size), [2, 1]);
  assert.equal(JSON.stringify(state.data.objects.slice(0, -1)), before);
});

test("adding objects uses the full selected rectangle just like replacement on every layer", () => {
  for (const [layer] of layers) {
    for (const [width, height] of [[1, 1], [2, 3], [3, 2]]) {
      const { context, state } = editor();
      context.handleChange({ dataset: { change: "object-layer" }, value: layer });
      state.selection = { x: 4, y: 5, width, height };
      const before = JSON.stringify(state.data.objects);
      state.choiceIndex = 2;
      state.frameIndex = 3;
      context.handleAction({ dataset: { action: "add-object" } });
      const added = JSON.parse(JSON.stringify(context.currentObject()));
      assert.deepEqual(added.size, [width, height]);
      assert.equal(added.default_draw_group, layer);
      assert.equal(added.interact_through, false);
      assert.deepEqual(added.cells, Array.from({ length: width * height }, (_, index) => ({
        offset: [index % width, Math.floor(index / width)], collision: "blocked",
        tile: [4 + index % width, 5 + Math.floor(index / width)],
      })));
      assert.equal(JSON.stringify(state.data.objects.slice(0, -1)), before);
      assert.equal(state.objectOrigins.at(-1), null);
      assert.equal(state.choiceIndex, 0);
      assert.equal(state.frameIndex, 0);
      assert.equal(state.dirty, true);
      assert.equal(state.history.length, 1);
      context.undo();
      assert.equal(JSON.stringify(state.data.objects), before);
      context.redo();
      assert.deepEqual(JSON.parse(JSON.stringify(state.data.objects.at(-1))), added);

      const replacement = editor();
      replacement.context.handleChange({ dataset: { change: "object-layer" }, value: layer });
      replacement.state.selection = { ...state.selection };
      replacement.context.handleAction({ dataset: { action: "object-from-selection" } });
      const replaced = JSON.parse(JSON.stringify(replacement.context.currentObject()));
      assert.deepEqual(replaced.size, added.size);
      assert.deepEqual(replaced.cells, added.cells);
      assert.equal(replaced.default_draw_group, added.default_draw_group);
    }
  }
});

test("rectangle replacement keeps object identity, layer and interaction setting", () => {
  const { context, state } = editor();
  const object = context.currentObject();
  object.interact_through = true;
  object.cells[0].collision = "passable_override";
  object.cells[0].visual = { choices: [{ frames: [{ tile: [0, 0] }] }] };
  const id = object.id;
  context.handleAction({ dataset: { action: "object-from-selection" } });
  assert.equal(context.currentObject().id, id);
  assert.equal(context.currentObject().default_draw_group, "object_y_sorted");
  assert.equal(context.currentObject().interact_through, true);
  assert.equal(state.data.objects.length, 5);
  assert.ok(context.currentObject().cells.every((cell) => cell.collision === "blocked" && !cell.visual));
});

test("one unified layer selector keeps displayed and selected object layers identical", () => {
  const { context, state } = editor();
  for (const [layer] of layers) {
    context.handleChange({ dataset: { change: "object-layer" }, value: layer });
    assert.equal(context.currentObject().default_draw_group, state.objectLayer);
    const html = context.renderObjectEditor();
    assert.equal((html.match(/data-change="object-layer"/g) || []).length, 4);
    assert.equal((html.match(/type="radio" name="object-layer"/g) || []).length, 4);
    assert.equal((html.match(/ checked/g) || []).length, 1);
    assert.match(html, /<legend>レイヤー<\/legend>/);
    assert.doesNotMatch(html, /<select/);
    assert.doesNotMatch(html, /表示レイヤー|選択オブジェクトのレイヤー|data-change="object-group"/);
  }
  assert.equal(state.history.length, 0);
});

test("ground, boundary and four object layers have six unique shared colors", () => {
  const keys = ["ground", "boundary", "layer-back", "layer-normal", "layer-front", "layer-top"];
  assert.equal(new Set(keys.map((key) => colors[`--${key}-color`])).size, 6);
  for (const layer of ["back", "normal", "front", "top"]) {
    assert.ok(css.includes(`--layer-${layer}-text: var(--layer-${layer}-color)`));
    assert.ok(css.includes(`--layer-${layer}-border: var(--layer-${layer}-color)`));
    assert.ok(htmlSource.includes(`class="usage-dot map-layer map-layer-${layer}"`));
  }
  assert.match(css, /\.usage-dot\.map-layer \{ background: var\(--map-layer-text\)/);
  assert.match(css, /\.layer-option \{[^}]*color: var\(--map-layer-text\)/);
});

test("source usage preserves all layer memberships including animation frames on a shared tile", () => {
  const { context, state } = editor();
  state.data.grounds[0].base_visual = { choices: [{ frames: [{ tile: [0, 0] }] }] };
  state.data.grounds[0].boundaries = [{ visual: { choices: [{ frames: [{ tile: [0, 0] }] }] } }];
  for (const object of state.data.objects) object.cells[0].tile = [0, 0];
  state.data.objects[1].cells[0].visual = { choices: [{ frames: [{ tile: [0, 0] }, { tile: [1, 0] }] }] };
  const usage = context.sourceTileUsage();
  assert.deepEqual(Array.from(usage.get("0,0")).sort(), ["ground", "boundary", ...layers.map(([key]) => key)].sort());
  assert.deepEqual(Array.from(usage.get("1,0")), ["object_y_sorted"]);
  state.imageInfo = { rows: 1, columns: 3 };
  const summary = {};
  context.byId = () => summary;
  const markers = [];
  const canvas = { fillRect(x, y, width, height) {
    if (Object.values(colors).includes(this.fillStyle)) markers.push({ color: this.fillStyle, x, y, width, height });
  } };
  context.drawSourceUsage(canvas, 1);
  const shared = markers.filter((marker) => marker.x < 16);
  assert.equal(shared.length, 6);
  assert.equal(new Set(shared.map((marker) => marker.color)).size, 6);
  assert.ok(shared.every((marker) => marker.x + marker.width <= 16 && marker.y + marker.height <= 16));
  assert.equal(markers.find((marker) => marker.x >= 16).color, colors["--layer-normal-color"]);
  assert.equal(summary.textContent, "使用 2 / 未使用 1");
});

test("filtered reordering retains full-array indices and saved-definition origins", () => {
  const { context, state } = editor();
  context.reorderDefinitions("object", 4, 1);
  assert.equal(state.data.objects[1].id, "normal_second");
  assert.equal(state.objectOrigins[1], "normal_second");
  assert.equal(context.currentObject().id, "object_1");
  context.undo();
  assert.deepEqual(Array.from(state.data.objects, (object) => object.id), ["object_0", "object_1", "object_2", "object_3", "normal_second"]);
});
