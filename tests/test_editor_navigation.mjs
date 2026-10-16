import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const editors = ["mapchip_metadata", "map_editor", "event_editor"];

for (const editor of editors) {
  test(`${editor}: suppresses native context menus everywhere without stopping editor actions`, () => {
    const source = readFileSync(new URL(`../tools/${editor}/static/app.js`, import.meta.url), "utf8");
    const registration = source.match(/^document\.addEventListener\("contextmenu",.*$/m)?.[0];
    assert.ok(registration);
    let listener;
    vm.runInNewContext(registration, { document: { addEventListener(type, callback, options) {
      assert.equal(type, "contextmenu");
      assert.equal(options.capture, true);
      listener = callback;
    } } });
    for (const target of ["canvas", "button", "input", "a", "dialog", "body"]) {
      const event = { target, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; },
        stopPropagation() { assert.fail("Editor context menu actions must still receive the event"); },
        stopImmediatePropagation() { assert.fail("Editor context menu actions must still receive the event"); } };
      listener(event);
      assert.equal(event.defaultPrevented, true);
    }
  });
}

test("mapchip metadata: custom right-click frame and collision actions still run", () => {
  const source = readFileSync(new URL("../tools/mapchip_metadata/static/app.js", import.meta.url), "utf8");
  const start = source.indexOf('byId("editor-content").addEventListener("contextmenu"');
  const end = source.indexOf('\n});', start) + '\n});'.length;
  let listener;
  const actions = [];
  vm.runInNewContext(source.slice(start, end), {
    byId: () => ({ addEventListener: (_, callback) => { listener = callback; } }),
    focusVisualFrameInSource: (target) => actions.push(["visual", target]),
    focusObjectFrameInSource: (target) => actions.push(["object", target]),
    handleAction: (target) => actions.push(["collision", target.dataset.action]),
  });
  for (const [action, expected] of [["set-frame-tile", "visual"], ["object-set-frame", "object"],
    ["toggle-object-cell-collision", "collision"]]) {
    const target = { dataset: { x: "1", y: "2" } };
    listener({ defaultPrevented: true, preventDefault() {}, target: {
      closest: (selector) => selector === `[data-action="${action}"]` ? target : null,
    } });
    assert.equal(actions.at(-1)[0], expected);
  }
  assert.equal(actions.at(-1)[1], "toggle-object-cell-override");
});

test("mapchip metadata: switching tilesets preserves each editor tab and resets document-local selection", async () => {
  const source = readFileSync(new URL("../tools/mapchip_metadata/static/app.js", import.meta.url), "utf8");
  const declarations = ["applyDocumentPayload", "loadTilesetDocument"].map((name) => {
    const start = source.search(new RegExp(`(?:async )?function ${name}\\(`));
    assert.notEqual(start, -1);
    const next = source.slice(start + 1).search(/\n(?:async )?function /);
    assert.notEqual(next, -1);
    return source.slice(start, start + 1 + next);
  }).join("\n");
  assert.match(source, /tab: "ground"/);
  for (const tab of ["ground", "boundary", "object"]) {
    const state = { tab, groundIndex: 7, boundaryIndex: 7, objectIndex: 7, choiceIndex: 7, frameIndex: 7 };
    const payload = {
      data: { tileset_id: "next", source_image_id: "next_image", grounds: [{ id: "plain" }], objects: [] },
      image_info: { width: 16, height: 16, columns: 1, rows: 1 }, image_url: "/image?token=test", diagnostics: [],
    };
    let renderedTab;
    const context = vm.createContext({
      state, URL, Date, Array, rawImage: {}, byId: () => ({}),
      window: { clearTimeout() {}, location: { href: "http://localhost/tileset/" }, history: { replaceState() {} } },
      api: async (path) => { assert.equal(path, "/api/document?tileset=next"); return payload; },
      editorApiPath: (path) => path,
      restorePreviewSettings() {}, prepareProcessedImage() {}, showToast() {}, saveLastTilesetId() {},
      renderTilesetSelector() {}, configureEditorNavigation() {}, savePreviewSettings() {}, updateSaveState() {},
      renderAll: () => { renderedTab = state.tab; },
    });
    vm.runInContext(declarations, context);
    await context.loadTilesetDocument("next");
    assert.equal(state.tab, tab);
    assert.equal(renderedTab, tab);
    for (const field of ["groundIndex", "boundaryIndex", "objectIndex", "choiceIndex", "frameIndex"]) assert.equal(state[field], 0);
    assert.equal(state.data.tileset_id, "next");
  }
});

function navigation(editor, dirty = true) {
  const source = readFileSync(new URL(`../tools/${editor}/static/app.js`, import.meta.url), "utf8");
  const callbacks = new Map();
  const buttons = Array.from({ length: 3 }, () => ({ disabled: false }));
  const dialog = {
    open: false,
    focusedChoice: null,
    showModal() { this.open = true; },
    close() { this.open = false; callbacks.get("unsaved-navigation-dialog:close")?.(); },
    querySelectorAll: () => buttons,
    querySelector: () => ({ focus() { dialog.focusedChoice = "save"; } }),
  };
  // Keep one dialog instance so show/close state can be inspected after each choice.
  dialog.addEventListener = (event, callback) => callbacks.set(`unsaved-navigation-dialog:${event}`, callback);
  const lookup = (id) => id === "unsaved-navigation-dialog" ? dialog : {
    addEventListener: (event, callback) => callbacks.set(`${id}:${event}`, callback),
  };
  const assignments = [];
  const location = { assign: (url) => assignments.push(url) };
  const state = { dirty, data: { map_id: "current", tileset_id: "current" } };
  const loadedMaps = [];
  const loadedTilesets = [];
  const messages = [];
  let selectorRenders = 0;
  let saves = 0;
  let discardedDrafts = 0;
  const context = vm.createContext({
    state, window: { location }, location, byId: lookup, $: lookup,
    pendingEditorNavigationUrl: null,
    pendingMapNavigationId: null, navigationBusy: false,
    pendingTilesetNavigationId: null,
    save: async () => { saves += 1; state.dirty = false; return true; },
    loadMapDocument: async (mapId) => { loadedMaps.push(mapId); state.data = { map_id: mapId }; state.dirty = false; },
    loadTilesetDocument: async (tilesetId) => { loadedTilesets.push(tilesetId); state.data = { tileset_id: tilesetId }; state.dirty = false; },
    renderMapSelector: () => { selectorRenders += 1; },
    renderTilesetSelector: () => { selectorRenders += 1; },
    showToast: (message) => messages.push(message),
    discardPendingActorEventDraft: () => { discardedDrafts += 1; },
  });
  for (const name of ["navigateToEditor", "closeNavigationDialog", "handleNavigationChoice",
    ...(editor === "map_editor" ? ["switchMapDocument", "requestMapSwitch"] : []),
    ...(editor === "mapchip_metadata" ? ["switchTilesetDocument", "requestTilesetSwitch"] : [])]) {
    const start = source.search(new RegExp(`(?:async )?function ${name}\\(`));
    assert.notEqual(start, -1);
    const next = source.slice(start + 1).search(/\n(?:async )?function /);
    assert.notEqual(next, -1);
    vm.runInContext(source.slice(start, start + 1 + next), context);
  }
  const start = source.indexOf(editor === "event_editor"
    ? '$("editor-switch").addEventListener("click"'
    : 'byId("editor-switch").addEventListener("click"');
  assert.notEqual(start, -1);
  const end = source.indexOf('\n});', source.indexOf('addEventListener("close"', start));
  assert.notEqual(end, -1);
  vm.runInContext(source.slice(start, end + '\n});'.length), context);
  if (editor === "map_editor") {
    const mapStart = source.indexOf('byId("map-select").addEventListener("change"');
    const mapEnd = source.indexOf('\n});', mapStart);
    vm.runInContext(source.slice(mapStart, mapEnd + '\n});'.length), context);
    const areaStart = source.indexOf('byId("area-select").addEventListener("change"');
    const areaEnd = source.indexOf('\n});', areaStart);
    vm.runInContext(source.slice(areaStart, areaEnd + '\n});'.length), context);
  }
  if (editor === "mapchip_metadata") {
    const tilesetStart = source.indexOf('byId("tileset-select").addEventListener("change"');
    const tilesetEnd = source.indexOf('\n});', tilesetStart);
    vm.runInContext(source.slice(tilesetStart, tilesetEnd + '\n});'.length), context);
  }
  const clickLink = (url) => {
    let prevented = false;
    callbacks.get("editor-switch:click")({
      target: { closest: () => ({ href: url }) },
      preventDefault: () => { prevented = true; },
    });
    return prevented;
  };
  const clickChoice = (choice) => callbacks.get("unsaved-navigation-dialog:click")({
    target: { closest: () => ({ dataset: { navigationChoice: choice } }) },
  });
  return { context, state, dialog, buttons, assignments, clickLink, clickChoice, loadedMaps, loadedTilesets, messages,
    saves: () => saves, discardedDrafts: () => discardedDrafts, selectorRenders: () => selectorRenders,
    changeMap: (mapId) => callbacks.get("map-select:change")({ target: { value: mapId } }),
    changeArea: (mapId) => callbacks.get("area-select:change")({ target: { value: mapId } }),
    changeTileset: (tilesetId) => callbacks.get("tileset-select:change")({ target: { value: tilesetId } }) };
}

test("tileset switch: dirty selection prompts and focuses save, cancel keeps the current document", async () => {
  const app = navigation("mapchip_metadata");
  app.changeTileset("next");
  assert.equal(app.dialog.open, true);
  assert.equal(app.dialog.focusedChoice, "save");
  assert.equal(app.context.pendingTilesetNavigationId, "next");
  assert.equal(app.selectorRenders(), 1);
  assert.deepEqual(app.loadedTilesets, []);
  await app.context.handleNavigationChoice("cancel");
  assert.equal(app.state.data.tileset_id, "current");
  assert.equal(app.state.dirty, true);
  assert.equal(app.context.pendingTilesetNavigationId, null);
  assert.equal(app.dialog.open, false);
});

test("tileset switch: save completes before loading and duplicate operations are ignored", async () => {
  const app = navigation("mapchip_metadata");
  await app.context.requestTilesetSwitch("next");
  let complete;
  let saves = 0;
  app.context.save = () => { saves += 1; return new Promise((resolve) => { complete = resolve; }); };
  const pending = app.context.handleNavigationChoice("save");
  await app.context.handleNavigationChoice("save");
  await app.context.requestTilesetSwitch("other");
  assert.equal(saves, 1);
  assert.deepEqual(app.loadedTilesets, []);
  assert.ok(app.buttons.every((button) => button.disabled));
  complete(true);
  await pending;
  assert.deepEqual(app.loadedTilesets, ["next"]);
  assert.equal(app.dialog.open, false);
  assert.ok(app.buttons.every((button) => !button.disabled));
});

test("tileset switch: failed save keeps current document and dialog", async () => {
  const app = navigation("mapchip_metadata");
  await app.context.requestTilesetSwitch("next");
  app.context.save = async () => false;
  await app.context.handleNavigationChoice("save");
  assert.deepEqual(app.loadedTilesets, []);
  assert.equal(app.state.data.tileset_id, "current");
  assert.equal(app.state.dirty, true);
  assert.equal(app.dialog.open, true);
  assert.ok(app.buttons.every((button) => !button.disabled));
});

test("tileset switch: discard skips saving and clean switching does not prompt", async () => {
  const app = navigation("mapchip_metadata");
  await app.context.requestTilesetSwitch("next");
  await app.context.handleNavigationChoice("discard");
  assert.equal(app.saves(), 0);
  assert.deepEqual(app.loadedTilesets, ["next"]);
  assert.equal(app.dialog.open, false);
  await app.context.requestTilesetSwitch("next");
  assert.deepEqual(app.loadedTilesets, ["next"]);
  await app.context.requestTilesetSwitch("other");
  assert.deepEqual(app.loadedTilesets, ["next", "other"]);
  assert.equal(app.dialog.open, false);
});

test("tileset switch: failed load preserves unsaved document and prior selection", async () => {
  const app = navigation("mapchip_metadata");
  await app.context.requestTilesetSwitch("next");
  app.context.loadTilesetDocument = async () => { throw new Error("読込失敗"); };
  await app.context.handleNavigationChoice("discard");
  assert.equal(app.state.data.tileset_id, "current");
  assert.equal(app.state.dirty, true);
  assert.equal(app.dialog.open, true);
  assert.equal(app.selectorRenders(), 2);
  assert.deepEqual(app.messages, ["読込失敗"]);
});

test("tileset switch: closing the dialog during saving cancels delayed navigation", async () => {
  const app = navigation("mapchip_metadata");
  await app.context.requestTilesetSwitch("next");
  let complete;
  app.context.save = () => new Promise((resolve) => { complete = resolve; });
  const pending = app.context.handleNavigationChoice("save");
  app.dialog.close();
  complete(true);
  await pending;
  assert.deepEqual(app.loadedTilesets, []);
  assert.equal(app.context.pendingTilesetNavigationId, null);
  assert.equal(app.context.navigationBusy, false);
});

test("map switch: dirty selection prompts and focuses save, cancel restores current map", async () => {
  const app = navigation("map_editor");
  app.changeMap("next");
  assert.equal(app.dialog.open, true);
  assert.equal(app.dialog.focusedChoice, "save");
  assert.equal(app.context.pendingMapNavigationId, "next");
  assert.equal(app.selectorRenders(), 1);
  assert.deepEqual(app.loadedMaps, []);
  await app.context.handleNavigationChoice("cancel");
  assert.equal(app.state.data.map_id, "current");
  assert.equal(app.state.dirty, true);
  assert.equal(app.context.pendingMapNavigationId, null);
  assert.equal(app.dialog.open, false);
});

test("area switch saves before loading the selected area", async () => {
  const app = navigation("map_editor");
  app.changeArea("current_b2");
  assert.equal(app.dialog.open, true);
  assert.equal(app.context.pendingMapNavigationId, "current_b2");
  await app.context.handleNavigationChoice("save");
  assert.equal(app.saves(), 1);
  assert.deepEqual(app.loadedMaps, ["current_b2"]);
});

test("area actor events open without initializing the ID filter", () => {
  const source = readFileSync(new URL("../tools/map_editor/static/app.js", import.meta.url), "utf8");
  const helper = source.match(/^const logicalMapId = .*$/m)?.[0];
  assert.ok(helper);
  const start = source.indexOf("function openNewActorEvent(");
  const end = source.indexOf("\nfunction ", start + 1);
  let destination;
  const state = { data: { map_id: "cave_b2", area_parent_id: "cave" }, siteNamesJa: {}, dirty: true };
  const context = vm.createContext({
    state, editorRoute: "map", crypto: { randomUUID: () => "draft" },
    currentActor: () => ({ id: "guide" }),
    sessionStorage: { setItem() {} },
    editorUrl: (_editor, parameters) => { destination = parameters; return "/event/"; },
    window: { location: { assign() {} } },
  });
  vm.runInContext(`${helper}\n${source.slice(start, end)}`, context);
  context.openNewActorEvent();
  assert.equal(destination.filter, undefined);
  assert.equal(destination.new_actor_event, "draft");
});

test("map switch: save completes before loading the requested map", async () => {
  const app = navigation("map_editor");
  await app.context.requestMapSwitch("next");
  let complete;
  app.context.save = () => new Promise((resolve) => { complete = resolve; });
  const pending = app.context.handleNavigationChoice("save");
  assert.deepEqual(app.loadedMaps, []);
  assert.ok(app.buttons.every((button) => button.disabled));
  complete(true);
  await pending;
  assert.deepEqual(app.loadedMaps, ["next"]);
  assert.equal(app.dialog.open, false);
  assert.equal(app.state.data.map_id, "next");
  assert.deepEqual(app.assignments, []);
});

test("map switch: failed save keeps current map and dialog", async () => {
  const app = navigation("map_editor");
  await app.context.requestMapSwitch("next");
  app.context.save = async () => false;
  await app.context.handleNavigationChoice("save");
  assert.deepEqual(app.loadedMaps, []);
  assert.equal(app.state.data.map_id, "current");
  assert.equal(app.state.dirty, true);
  assert.equal(app.dialog.open, true);
  assert.ok(app.buttons.every((button) => !button.disabled));
});

test("map switch: discard skips saving, clean switching does not prompt", async () => {
  const app = navigation("map_editor");
  await app.context.requestMapSwitch("next");
  await app.context.handleNavigationChoice("discard");
  assert.equal(app.saves(), 0);
  assert.equal(app.state.dirty, false);
  assert.equal(app.dialog.open, false);
  await app.context.requestMapSwitch("other");
  assert.deepEqual(app.loadedMaps, ["next", "other"]);
  assert.equal(app.dialog.open, false);
  await app.context.requestMapSwitch("other");
  assert.deepEqual(app.loadedMaps, ["next", "other"]);
});

test("map switch: failed load preserves unsaved current document", async () => {
  const app = navigation("map_editor");
  await app.context.requestMapSwitch("next");
  app.context.loadMapDocument = async () => { throw new Error("読み込み失敗"); };
  await app.context.handleNavigationChoice("discard");
  assert.equal(app.state.data.map_id, "current");
  assert.equal(app.state.dirty, true);
  assert.equal(app.dialog.open, true);
  assert.deepEqual(app.messages, ["読み込み失敗"]);
  assert.equal(app.selectorRenders(), 2);
});

test("map switch: closing during save prevents navigation and duplicate saves", async () => {
  const app = navigation("map_editor");
  await app.context.requestMapSwitch("next");
  let complete;
  let saves = 0;
  app.context.save = () => { saves += 1; return new Promise((resolve) => { complete = resolve; }); };
  const pending = app.context.handleNavigationChoice("save");
  await app.context.handleNavigationChoice("save");
  assert.equal(saves, 1);
  app.dialog.close();
  complete(true);
  await pending;
  assert.deepEqual(app.loadedMaps, []);
  assert.equal(app.state.data.map_id, "current");
  assert.equal(app.context.navigationBusy, false);
});

for (const editor of editors) {
  test(`${editor}: same dialog wording and three choices`, () => {
    const html = readFileSync(new URL(`../tools/${editor}/static/index.html`, import.meta.url), "utf8");
    assert.match(html, /未保存の変更があります/);
    assert.match(html, /変更を保存してからエディタを切り替えますか？/);
    for (const choice of ["save", "discard", "cancel"]) assert.ok(html.includes(`data-navigation-choice="${choice}"`));
  });

  test(`${editor}: clean navigation does not prompt`, () => {
    const app = navigation(editor, false);
    assert.equal(app.clickLink("/map/"), false);
    app.context.navigateToEditor("/map/");
    assert.deepEqual(app.assignments, ["/map/"]);
    assert.equal(app.dialog.open, false);
  });

  test(`${editor}: dirty header navigation prompts, cancel keeps changes`, () => {
    const app = navigation(editor);
    assert.equal(app.clickLink("/event/"), true);
    assert.equal(app.dialog.open, true);
    assert.deepEqual(app.assignments, []);
    app.clickChoice("cancel");
    assert.equal(app.dialog.open, false);
    assert.equal(app.context.pendingEditorNavigationUrl, null);
    assert.equal(app.state.dirty, true);
  });

  test(`${editor}: discard navigates without saving`, async () => {
    const app = navigation(editor);
    app.clickLink("/tileset/");
    await app.context.handleNavigationChoice("discard");
    assert.deepEqual(app.assignments, ["/tileset/"]);
    assert.equal(app.state.dirty, false);
    assert.equal(app.saves(), 0);
    assert.equal(app.discardedDrafts(), editor === "event_editor" ? 1 : 0);
  });

  test(`${editor}: save waits for success before navigating`, async () => {
    const app = navigation(editor);
    app.clickLink("/event/");
    let complete;
    app.context.save = () => new Promise((resolve) => { complete = resolve; });
    const pending = app.context.handleNavigationChoice("save");
    assert.ok(app.buttons.every((button) => button.disabled));
    assert.deepEqual(app.assignments, []);
    complete(true);
    await pending;
    assert.ok(app.buttons.every((button) => !button.disabled));
    assert.deepEqual(app.assignments, ["/event/"]);
  });

  test(`${editor}: failed save keeps dialog and changes`, async () => {
    const app = navigation(editor);
    app.clickLink("/map/");
    app.context.save = async () => false;
    await app.context.handleNavigationChoice("save");
    assert.deepEqual(app.assignments, []);
    assert.equal(app.dialog.open, true);
    assert.equal(app.state.dirty, true);
    assert.ok(app.buttons.every((button) => !button.disabled));
  });
}
