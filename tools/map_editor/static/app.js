"use strict";

document.addEventListener("contextmenu", (event) => event.preventDefault(), { capture: true });

const SESSION_CLIENT_HEADER = "map-editor-ui";
const CELL_SIZE = 16;
const FLOATING_PHASE_CYCLE_FRAMES = 96;
const FLOATING_CHARACTER_FRAMES = [2, 1, 0, 1];
const FLOATING_CHARACTER_FRAME_INTERVAL = 20;
const MIN_MAP_WIDTH = 16;
const MIN_MAP_HEIGHT = 15;
const LAST_MAP_STORAGE_KEY = "da0.map-editor.last-map.v1";
const OBJECT_LAYERS = [
  ["object", "背面"],
  ["object_y_sorted", "通常"],
  ["object_foreground", "前面"],
  ["object_overlay", "最前面"],
  ["all", "全て"],
];
let token = new URLSearchParams(window.location.search).get("token") || "";
const editorRoute = window.location.pathname.match(/^\/(tileset|map|event)(?:\/|$)/)?.[1] || null;

const state = {
  data: null,
  tileset: null,
  siteNamesJa: {},
  destinationOptions: [],
  siteOptions: [],
  eventOptions: [],
  flagOptions: [],
  eventNotes: {},
  itemOptions: [],
  bgmOptions: [],
  actorAssets: {},
  mapCatalog: [],
  tilesetCatalog: [],
  resolved: null,
  diagnostics: [],
  dirty: false,
  history: [],
  future: [],
  tab: "ground",
  groundId: null,
  groundTool: "rectangle",
  objectId: null,
  objectLayer: "object_y_sorted",
  selectedInstanceId: null,
  selectedSiteId: null,
  selectedArrivalId: null,
  savedArrivalIds: new Set(),
  arrivalIdRenames: {},
  selectedActorId: null,
  selectedTriggerId: null,
  bulkSelection: [],
  selectionRect: null,
  eventTool: "select",
  travelTool: "select",
  resizeHorizontal: "right",
  resizeVertical: "down",
  zoom: 2,
  showGrid: true,
  showCollision: false,
  showGroundOnly: false,
  paused: false,
  animationStartedAt: performance.now(),
  pointerStroke: null,
  pointerDrag: null,
  dragPointer: null,
  dragScrollTime: null,
  groundPaintRect: null,
  hoveredCell: null,
  resolveTimer: null,
  resolveRevision: 0,
  siteNameEditing: false,
  spritePickerActorId: null,
};
let pendingEditorNavigationUrl = null;
let pendingMapNavigationId = null;
let navigationBusy = false;

const rawImage = new Image();
const sourceImage = document.createElement("canvas");
const actorSheets = {
  prop: { image: new Image(), canvas: document.createElement("canvas"), ready: false },
  character: { image: new Image(), canvas: document.createElement("canvas"), ready: false },
  pc_character: { image: new Image(), canvas: document.createElement("canvas"), ready: false },
  treasure: { image: new Image(), canvas: document.createElement("canvas"), ready: false },
};
const floatingPhaseCache = new Map();
const byId = (id) => document.getElementById(id);
const clone = (value) => JSON.parse(JSON.stringify(value));
const escapeHtml = (value) => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");
const logicalMapId = (data = state.data) => data?.area_parent_id || data?.map_id;

function editorApiPath(path) {
  return editorRoute ? `/${editorRoute}${path}` : path;
}

function editorUrl(editor, parameters = {}) {
  if (!editorRoute) return null;
  const url = new URL(`/${editor}/`, window.location.origin);
  url.searchParams.set("token", token);
  for (const [key, value] of Object.entries(parameters)) {
    if (value) url.searchParams.set(key, value);
  }
  return url.href;
}

function configureEditorNavigation() {
  const navigation = byId("editor-switch");
  if (!navigation || !editorRoute) return;
  navigation.hidden = false;
  navigation.querySelectorAll("[data-editor-link]").forEach((link) => {
    link.href = editorUrl(link.dataset.editorLink, {
      map: state.data?.map_id,
      tileset: state.data?.tileset_id,
      namespace: logicalMapId(),
    });
  });
}

function navigateToEditor(url) {
  if (!url) return;
  if (!state.dirty) {
    window.location.assign(url);
    return;
  }
  pendingEditorNavigationUrl = url;
  pendingMapNavigationId = null;
  byId("unsaved-navigation-message").textContent = "変更を保存してからエディタを切り替えますか？";
  byId("unsaved-navigation-dialog").showModal();
  byId("unsaved-navigation-dialog").querySelector('[data-navigation-choice="save"]').focus();
}

async function switchMapDocument(mapId) {
  try {
    await loadMapDocument(mapId);
    return true;
  } catch (error) {
    showToast(error.message, true);
    renderMapSelector();
    return false;
  }
}

async function requestMapSwitch(mapId) {
  if (navigationBusy || mapId === state.data?.map_id) {
    renderMapSelector();
    return;
  }
  if (!state.dirty) {
    await switchMapDocument(mapId);
    return;
  }
  pendingEditorNavigationUrl = null;
  pendingMapNavigationId = mapId;
  renderMapSelector();
  byId("unsaved-navigation-message").textContent = "変更を保存してからマップを切り替えますか？";
  byId("unsaved-navigation-dialog").showModal();
  byId("unsaved-navigation-dialog").querySelector('[data-navigation-choice="save"]').focus();
}

function openNewActorEvent() {
  const actor = currentActor();
  if (!actor || !editorRoute) return;
  const draftId = crypto.randomUUID();
  try {
    sessionStorage.setItem(`da0.pending-actor-event:${draftId}`, JSON.stringify({
      data: state.data,
      site_names_ja: state.siteNamesJa,
      actor_id: actor.id,
    }));
  } catch (_error) {
    showToast("イベント追加用のマップ内容を一時保存できませんでした。", true);
    return;
  }
  const url = editorUrl("event", {
    namespace: logicalMapId(),
    new_actor_event: draftId,
  });
  state.dirty = false;
  window.location.assign(url);
}

function closeNavigationDialog() {
  pendingEditorNavigationUrl = null;
  pendingMapNavigationId = null;
  byId("unsaved-navigation-dialog").close();
}

async function handleNavigationChoice(choice) {
  if (navigationBusy) return;
  const url = pendingEditorNavigationUrl;
  const mapId = pendingMapNavigationId;
  if ((!url && !mapId) || choice === "cancel") {
    closeNavigationDialog();
    return;
  }
  if (choice !== "save" && choice !== "discard") return;
  const buttons = byId("unsaved-navigation-dialog").querySelectorAll("button");
  navigationBusy = true;
  buttons.forEach((button) => { button.disabled = true; });
  try {
    if (choice === "save" && !await save()) return;
    if (url !== pendingEditorNavigationUrl || mapId !== pendingMapNavigationId) return;
    if (mapId) {
      if (await switchMapDocument(mapId)) closeNavigationDialog();
    } else {
      state.dirty = false;
      window.location.assign(url);
    }
  } finally {
    navigationBusy = false;
    buttons.forEach((button) => { button.disabled = false; });
  }
}

async function renewSessionToken() {
  try {
    const response = await fetch(editorApiPath("/api/session-token"), { cache: "no-store", headers: { "X-Map-Editor-Client": SESSION_CLIENT_HEADER } });
    if (!response.ok) return false;
    const value = await response.json();
    if (typeof value.token !== "string" || !value.token) return false;
    token = value.token;
    const url = new URL(window.location.href);
    url.searchParams.set("token", token);
    window.history.replaceState(null, "", url);
    configureEditorNavigation();
    return true;
  } catch (_error) {
    return false;
  }
}

async function api(path, options = {}, retryAuthentication = true) {
  const response = await fetch(editorApiPath(path), {
    ...options,
    headers: { "Content-Type": "application/json", "X-Map-Editor-Token": token, ...(options.headers || {}) },
  });
  if (response.status === 403 && retryAuthentication && await renewSessionToken()) return api(path, options, false);
  const value = await response.json();
  if (!response.ok) throw new Error(response.status === 403 ? "認証セッションを更新できませんでした。ツールを再起動してください。" : value.error || `HTTP ${response.status}`);
  return value;
}

function renderMapSelector() {
  const select = byId("map-select");
  if (!select) return;
  const records = [...state.mapCatalog];
  if (state.data) {
    const current = {
      map_id: state.data.map_id,
      profile: state.data.profile,
      tileset_id: state.data.tileset_id,
      size: state.data.size,
      area_parent_id: state.data.area_parent_id,
      area_name: state.data.area_name,
    };
    const index = records.findIndex((item) => item.map_id === state.data.map_id);
    if (index === -1) records.push({ ...current, is_new: true });
    else if (state.dirty) records[index] = { ...records[index], ...current, dirty: true };
  }
  records.sort((left, right) => left.map_id.localeCompare(right.map_id));
  const roots = records.filter((item) => !item.area_parent_id);
  select.innerHTML = roots.map((item) => {
    const suffix = item.is_new ? "（未保存）" : `${item.profile} / ${item.tileset_id}${item.dirty ? "（未保存）" : ""}`;
    return `<option value="${escapeHtml(item.map_id)}" ${item.map_id === logicalMapId() ? "selected" : ""}>${escapeHtml(item.map_id)} — ${escapeHtml(suffix)}</option>`;
  }).join("");
  select.disabled = roots.length === 0;
  const areaSelect = byId("area-select");
  const rootId = logicalMapId();
  const areaName = (item) => item.area_name || (item.map_id === rootId ? "メイン" : item.map_id);
  const areas = records.filter((item) => item.map_id === rootId || item.area_parent_id === rootId)
    .sort((left, right) => areaName(left).localeCompare(areaName(right), "ja", { numeric: true })
      || left.map_id.localeCompare(right.map_id));
  areaSelect.innerHTML = areas.map((item) => `<option value="${escapeHtml(item.map_id)}" ${item.map_id === state.data?.map_id ? "selected" : ""}>${escapeHtml(areaName(item))}${item.dirty || item.is_new ? "（未保存）" : ""}</option>`).join("");
  areaSelect.disabled = areas.length < 2;
  const persisted = state.data && state.mapCatalog.some((item) => item.map_id === state.data.map_id);
  const alternatives = state.tilesetCatalog.filter((item) => item.profile === state.data?.profile && item.tileset_id !== state.data?.tileset_id);
  byId("change-map-tileset-button").disabled = !persisted || !!state.data?.area_parent_id || alternatives.length === 0;
  byId("delete-map-button").disabled = !persisted || state.data?.map_id === "worldmap";
  byId("new-area-button").disabled = !state.mapCatalog.some((item) => item.map_id === rootId);
}

function loadLastMapId() {
  try {
    return localStorage.getItem(LAST_MAP_STORAGE_KEY) || null;
  } catch (_error) {
    return null;
  }
}

function saveLastMapId(mapId = state.data?.map_id) {
  if (!mapId || !state.mapCatalog.some((item) => item.map_id === mapId)) return;
  try {
    localStorage.setItem(LAST_MAP_STORAGE_KEY, mapId);
  } catch (_error) {}
}

function applyDocumentPayload(payload) {
  window.clearTimeout(state.resolveTimer);
  stopMapAutoScroll();
  if (state.tileset?.tileset_id !== payload.tileset.tileset_id) {
    state.groundId = null;
    state.objectId = null;
  }
  state.pointerDrag = null;
  state.pointerStroke = null;
  state.resolveRevision += 1;
  state.data = payload.data;
  state.tileset = payload.tileset;
  state.siteNamesJa = payload.site_names_ja;
  state.destinationOptions = payload.destination_options;
  state.siteOptions = payload.site_options;
  state.eventOptions = payload.event_options;
  state.flagOptions = payload.flag_options || [];
  state.eventNotes = payload.event_notes || {};
  state.itemOptions = payload.item_options || [];
  state.bgmOptions = payload.bgm_options || [];
  state.actorAssets = payload.actor_assets || {};
  state.resolved = payload.resolved;
  state.diagnostics = payload.diagnostics;
  state.dirty = Boolean(payload.is_new || payload.dirty);
  state.history = [];
  state.future = [];
  state.selectedInstanceId = null;
  state.selectedSiteId = null;
  state.selectedArrivalId = null;
  state.savedArrivalIds = new Set(payload.is_new ? [] : (payload.data.arrival_points || []).map((arrival) => arrival.id));
  state.arrivalIdRenames = {};
  state.selectedActorId = null;
  state.selectedTriggerId = null;
  state.bulkSelection = [];
  state.selectionRect = null;
  state.groundPaintRect = null;
  state.hoveredCell = null;
  state.zoom = 2;
  state.showGrid = true;
  state.showCollision = false;
  state.showGroundOnly = false;
  restoreUiSettings();
  rawImage.onload = prepareSourceImage;
  rawImage.onerror = () => showToast("マップチップ画像を表示できません。", true);
  rawImage.src = `${editorApiPath(payload.image_url)}&revision=${Date.now()}`;
  loadActorSheets();
  const url = new URL(window.location.href);
  url.searchParams.set("map", state.data.map_id);
  url.searchParams.set("tileset", state.data.tileset_id);
  window.history.replaceState(null, "", url);
  saveLastMapId();
  renderMapSelector();
  configureEditorNavigation();
  renderAll();
  if (payload.repaired_unknown_ground_count > 0) {
    showToast(
      `未定義の地面${payload.repaired_unknown_ground_count}セルをベース地面へ置き換えました。保存してください。`,
    );
  }
}

async function loadMapDocument(mapId) {
  const payload = await api(`/api/document?map=${encodeURIComponent(mapId)}`);
  applyDocumentPayload(payload);
}

function renderNewMapTilesets() {
  const profile = byId("new-map-profile").value;
  const compatible = state.tilesetCatalog.filter((item) => item.profile === profile);
  const select = byId("new-map-tileset");
  const previous = select.value;
  select.innerHTML = compatible.map((item) => `<option value="${escapeHtml(item.tileset_id)}">${escapeHtml(item.tileset_id)}</option>`).join("");
  if (compatible.some((item) => item.tileset_id === previous)) select.value = previous;
  const selected = compatible.find((item) => item.tileset_id === select.value);
  select.disabled = compatible.length === 0;
  byId("new-map-form").querySelector('button[type="submit"]').disabled = compatible.length === 0;
  byId("new-map-source-summary").textContent = selected ? `ソース画像: ${selected.source_image_id} / ベース地面: ${selected.base_ground_id}` : "このprofileに対応するタイルセットがありません。";
}

function renderChangeMapTilesets() {
  const compatible = state.tilesetCatalog.filter((item) => item.profile === state.data.profile && item.tileset_id !== state.data.tileset_id);
  const select = byId("change-map-tileset-select");
  select.innerHTML = compatible.map((item) => `<option value="${escapeHtml(item.tileset_id)}">${escapeHtml(item.tileset_id)} — ${escapeHtml(item.source_image_id)}</option>`).join("");
  const selected = compatible.find((item) => item.tileset_id === select.value);
  byId("change-map-tileset-summary").textContent = selected ? `ベース地面: ${selected.base_ground_id}` : "同じprofileの別タイルセットがありません。";
  byId("change-map-tileset-form").querySelector('button[type="submit"]').disabled = compatible.length === 0;
}

function showToast(message, error = false) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.classList.toggle("error", error);
  toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("visible"), 2600);
}

function settingsKey() {
  return `da0.map-editor.ui.v1:${state.data?.map_id || "unknown"}`;
}

function saveUiSettings() {
  if (!state.data) return;
  try {
    localStorage.setItem(settingsKey(), JSON.stringify({ zoom: state.zoom, showGrid: state.showGrid, showCollision: state.showCollision, showGroundOnly: state.showGroundOnly }));
  } catch (_error) {}
}

function restoreUiSettings() {
  try {
    const settings = JSON.parse(localStorage.getItem(settingsKey()) || "null");
    if (!settings) return;
    if (Number.isInteger(settings.zoom)) state.zoom = Math.max(1, Math.min(4, settings.zoom));
    if (typeof settings.showGrid === "boolean") state.showGrid = settings.showGrid;
    if (typeof settings.showCollision === "boolean") state.showCollision = settings.showCollision;
    if (typeof settings.showGroundOnly === "boolean") state.showGroundOnly = settings.showGroundOnly;
  } catch (_error) {}
}

function canSave() {
  return Boolean(state.data) && (state.dirty || state.diagnostics.some((issue) => issue.severity === "error"));
}

function updateSaveState(kind = null, text = null) {
  const errors = state.diagnostics.some((issue) => issue.severity === "error");
  const element = byId("save-state");
  element.className = "status-pill";
  if (kind) element.classList.add(kind);
  else if (errors) element.classList.add("error");
  else if (state.dirty) element.classList.add("dirty");
  else element.classList.add("saved");
  element.textContent = text || (errors ? "要修正" : state.dirty ? "未保存" : "保存済み");
  byId("undo-button").disabled = state.history.length === 0;
  byId("redo-button").disabled = state.future.length === 0;
  byId("save-button").disabled = !canSave();
}

function beginChange() {
  state.history.push(changeSnapshot());
  if (state.history.length > 100) state.history.shift();
  state.future = [];
}

function finishChange() {
  state.dirty = true;
  renderAll();
  scheduleResolution();
}

function commit(mutator) {
  beginChange();
  mutator();
  finishChange();
}

function undo() {
  if (!state.history.length) return;
  state.future.push(changeSnapshot());
  restoreChangeSnapshot(state.history.pop());
  state.dirty = true;
  normalizeSelections();
  renderAll();
  scheduleResolution(0);
}

function redo() {
  if (!state.future.length) return;
  state.history.push(changeSnapshot());
  restoreChangeSnapshot(state.future.pop());
  state.dirty = true;
  normalizeSelections();
  renderAll();
  scheduleResolution(0);
}

function changeSnapshot() {
  return JSON.stringify({ data: state.data, siteNamesJa: state.siteNamesJa, arrivalIdRenames: state.arrivalIdRenames });
}

function restoreChangeSnapshot(snapshot) {
  const value = JSON.parse(snapshot);
  state.data = value.data;
  state.siteNamesJa = value.siteNamesJa;
  state.arrivalIdRenames = value.arrivalIdRenames || {};
  state.siteNameEditing = false;
}

function normalizeSelections() {
  const grounds = state.tileset?.grounds || [];
  const objects = state.tileset?.objects || [];
  if (state.data) {
    if (!Array.isArray(state.data.sites)) state.data.sites = [];
    if (!Array.isArray(state.data.arrival_points)) state.data.arrival_points = [];
    if (!Array.isArray(state.data.actors)) state.data.actors = [];
    if (!Array.isArray(state.data.event_triggers)) state.data.event_triggers = [];
  }
  if (!grounds.some((ground) => ground.id === state.groundId)) state.groundId = grounds[0]?.id || null;
  const paletteObjects = objects.filter((object) => state.objectLayer !== "all" && object.default_draw_group === state.objectLayer);
  if (!paletteObjects.some((object) => object.id === state.objectId)) state.objectId = paletteObjects[0]?.id || null;
  if (!state.data?.objects?.some((instance) => instance.id === state.selectedInstanceId)) state.selectedInstanceId = null;
  if (state.tab === "object" && (state.objectLayer === "all" || !objectLayerEditable(objectDefinition(currentInstance())))) state.selectedInstanceId = null;
  if (!state.data?.sites?.some((site) => site.id === state.selectedSiteId)) state.selectedSiteId = null;
  if (!state.data?.arrival_points?.some((arrival) => arrival.id === state.selectedArrivalId)) state.selectedArrivalId = null;
  if (!state.data?.actors?.some((actor) => actor.id === state.selectedActorId)) state.selectedActorId = null;
  if (!state.data?.event_triggers?.some((trigger) => trigger.id === state.selectedTriggerId)) state.selectedTriggerId = null;
  state.bulkSelection = (state.bulkSelection || []).filter((item) => bulkItemExists(item)
    && (state.tab !== "object" || (item.kind === "object"
      && objectLayerEditable(objectDefinition(state.data.objects.find((instance) => instance.id === item.id))))));
  if (!state.bulkSelection.length) state.selectionRect = null;
}

function clearSingleSelections() {
  state.selectedInstanceId = null;
  state.selectedSiteId = null;
  state.selectedArrivalId = null;
  state.selectedActorId = null;
  state.selectedTriggerId = null;
}

function clearBulkSelection() {
  state.bulkSelection = [];
  state.selectionRect = null;
}

function bulkItemExists(item) {
  if (!state.data || !item) return false;
  const collections = {
    object: state.data.objects,
    site: state.data.sites,
    arrival: state.data.arrival_points,
    actor: state.data.actors,
    trigger: standaloneTriggers(),
  };
  return Boolean(collections[item.kind]?.some((record) => record.id === item.id));
}

function isBulkSelected(kind, id) {
  return state.bulkSelection.some((item) => item.kind === kind && item.id === id);
}

function clearSelectionsOutsideTab(tab) {
  if (tab !== "object") state.selectedInstanceId = null;
  if (tab !== "site") {
    state.selectedSiteId = null;
    state.selectedArrivalId = null;
  }
  if (tab !== "event") {
    state.selectedActorId = null;
    state.selectedTriggerId = null;
  }
}

function groundStack(groundId) {
  const byGround = new Map(state.tileset.grounds.map((ground) => [ground.id, ground]));
  const stack = [];
  const seen = new Set();
  let current = groundId;
  while (current && byGround.has(current) && !seen.has(current)) {
    seen.add(current);
    const ground = byGround.get(current);
    stack.unshift(ground);
    current = ground.parent_id;
  }
  return stack;
}

function firstTile(visual) {
  return visual?.choices?.find((choice) => Number(choice.weight) > 0)?.frames?.[0]?.tile || null;
}

function drawSourceTile(context, tile, x, y, size) {
  if (!tile || !sourceImage.width) return;
  context.imageSmoothingEnabled = false;
  context.drawImage(sourceImage, tile[0] * CELL_SIZE, tile[1] * CELL_SIZE, CELL_SIZE, CELL_SIZE, x, y, size, size);
}

function prepareSourceImage() {
  sourceImage.width = rawImage.naturalWidth;
  sourceImage.height = rawImage.naturalHeight;
  const context = sourceImage.getContext("2d", { willReadFrequently: true });
  context.drawImage(rawImage, 0, 0);
  const pixels = context.getImageData(0, 0, sourceImage.width, sourceImage.height);
  for (let index = 0; index < pixels.data.length; index += 4) {
    if (pixels.data[index] === 255 && pixels.data[index + 1] === 0 && pixels.data[index + 2] === 128) pixels.data[index + 3] = 0;
  }
  context.putImageData(pixels, 0, 0);
  renderPalette();
  drawMap(performance.now());
}

function actorCells(actor, position = actor.position) {
  const cells = [[...position]];
  if (actor.kind === "stationary" || actor.kind === "roaming") cells.push([position[0], position[1] - 1]);
  return cells;
}

function actorIntersectsMap(actor, position = actor.position) {
  const [width, height] = state.data.size;
  return actorCells(actor, position).some(([x, y]) => x >= 0 && x < width && y >= 0 && y < height);
}

function actorOccupiesCell(actor, cell) {
  return actorCells(actor).some(([x, y]) => x === cell[0] && y === cell[1]);
}

function actorAssetId(actor) {
  if (actor.kind === "treasure") return "treasure";
  if (actor.kind === "prop") return "prop";
  return actor.sprite_source === "pc" ? "pc_character" : "character";
}

function actorSpriteLabel(actor) {
  if (actor.kind === "prop") return `固定物 #${actor.sprite_index}`;
  return `${actor.sprite_source === "pc" ? "PC" : "NPC"} #${actor.sprite_index}`;
}

function prepareActorSheet(assetId) {
  const sheet = actorSheets[assetId];
  const image = sheet.image;
  sheet.canvas.width = image.naturalWidth;
  sheet.canvas.height = image.naturalHeight;
  const context = sheet.canvas.getContext("2d", { willReadFrequently: true });
  context.drawImage(image, 0, 0);
  const pixels = context.getImageData(0, 0, sheet.canvas.width, sheet.canvas.height);
  for (let index = 0; index < pixels.data.length; index += 4) {
    if (pixels.data[index] === 255 && pixels.data[index + 1] === 0 && pixels.data[index + 2] === 128) pixels.data[index + 3] = 0;
  }
  context.putImageData(pixels, 0, 0);
  sheet.ready = true;
  drawSelectedActorSprite();
  if (byId("actor-sprite-dialog").open) renderActorSpriteDialog();
}

function loadActorSheets() {
  for (const [assetId, asset] of Object.entries(state.actorAssets)) {
    const sheet = actorSheets[assetId];
    if (!sheet || typeof asset?.image_url !== "string") continue;
    sheet.ready = false;
    sheet.image.onload = () => prepareActorSheet(assetId);
    sheet.image.onerror = () => {
      sheet.ready = false;
      if (byId("actor-sprite-dialog").open) renderActorSpriteDialog();
      showToast("actorスプライト画像を表示できません。", true);
    };
    sheet.image.src = editorApiPath(asset.image_url);
  }
}

function actorSpriteCapacity(assetId) {
  const sheet = actorSheets[assetId];
  const size = state.actorAssets[assetId]?.sprite_size;
  if (!sheet?.ready || !Array.isArray(size) || size.length !== 2) return 0;
  return Math.floor(sheet.canvas.width / size[0]) * Math.floor(sheet.canvas.height / size[1]);
}

function actorSpriteSource(assetId, spriteIndex, facing = "down", frame = 1) {
  const sheet = actorSheets[assetId];
  const size = state.actorAssets[assetId]?.sprite_size;
  if (!sheet?.ready || !Array.isArray(size) || !Number.isInteger(spriteIndex)) return null;
  const columns = Math.floor(sheet.canvas.width / size[0]);
  if (columns < 1 || spriteIndex < 0 || spriteIndex >= actorSpriteCapacity(assetId)) return null;
  let sourceX = (spriteIndex % columns) * size[0];
  let sourceY = Math.floor(spriteIndex / columns) * size[1];
  let sourceWidth = CELL_SIZE;
  let sourceHeight = CELL_SIZE;
  if (assetId === "character" || assetId === "pc_character") {
    const facingRow = { down: 0, up: 1, left: 2, right: 3 }[facing] ?? 0;
    sourceX += frame * CELL_SIZE;
    sourceY += facingRow * CELL_SIZE * 2;
    sourceHeight = CELL_SIZE * 2;
  }
  return { sheet, sourceX, sourceY, sourceWidth, sourceHeight };
}

function stableFloatingPhase(identity) {
  if (floatingPhaseCache.has(identity)) return floatingPhaseCache.get(identity);
  let checksum = 0xffffffff;
  for (const byte of new TextEncoder().encode(identity)) {
    checksum ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      checksum = (checksum >>> 1) ^ (0xedb88320 & -(checksum & 1));
    }
  }
  const phase = ((checksum ^ 0xffffffff) >>> 0) % FLOATING_PHASE_CYCLE_FRAMES;
  floatingPhaseCache.set(identity, phase);
  return phase;
}

function actorFloatingPhase(actor) {
  return stableFloatingPhase(`actor:${state.data.map_id}:${actor.id}`);
}

function floatingCharacterFrame(now, phaseOffset = 0) {
  if (state.paused) return 1;
  const frame = Math.floor((now - state.animationStartedAt) / (1000 / 60)) + phaseOffset;
  const phase = Math.floor(frame / FLOATING_CHARACTER_FRAME_INTERVAL) % FLOATING_CHARACTER_FRAMES.length;
  return FLOATING_CHARACTER_FRAMES[phase];
}

function drawActorSprite(canvas, assetId, spriteIndex, facing = "down", floating = false, now = performance.now(), floatingPhase = 0) {
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  const frame = floating ? floatingCharacterFrame(now, floatingPhase) : 1;
  const source = actorSpriteSource(assetId, spriteIndex, facing, frame);
  if (!source) return;
  const scale = Math.max(1, Math.floor(Math.min(canvas.width / source.sourceWidth, canvas.height / source.sourceHeight)));
  const drawWidth = source.sourceWidth * scale;
  const drawHeight = source.sourceHeight * scale;
  const drawX = Math.floor((canvas.width - drawWidth) / 2);
  const drawY = Math.floor((canvas.height - drawHeight) / 2);
  context.imageSmoothingEnabled = false;
  context.drawImage(source.sheet.canvas, source.sourceX, source.sourceY, source.sourceWidth, source.sourceHeight, drawX, drawY, drawWidth, drawHeight);
}

function drawActorOnMap(context, actor, scale, now) {
  const floatingPhase = actor.floating ? actorFloatingPhase(actor) : 0;
  const frame = actor.floating ? floatingCharacterFrame(now, floatingPhase) : 1;
  const source = actorSpriteSource(actorAssetId(actor), actor.kind === "treasure" ? 0 : actor.sprite_index, actor.facing, frame);
  if (!source) return false;
  context.imageSmoothingEnabled = false;
  context.drawImage(
    source.sheet.canvas,
    source.sourceX,
    source.sourceY,
    source.sourceWidth,
    source.sourceHeight,
    actor.position[0] * scale,
    actor.position[1] * scale - (source.sourceHeight / CELL_SIZE - 1) * scale,
    scale,
    source.sourceHeight / CELL_SIZE * scale,
  );
  return true;
}

function drawSelectedActorSprite(now = performance.now()) {
  const actor = currentActor();
  const canvas = document.querySelector("[data-selected-actor-sprite]");
  if (!actor || !canvas) return;
  drawActorSprite(
    canvas,
    actorAssetId(actor),
    actor.kind === "treasure" ? 0 : actor.sprite_index,
    actor.facing,
    Boolean(actor.floating),
    now,
    actorFloatingPhase(actor),
  );
}

function renderActorSpriteDialog() {
  const actor = state.data?.actors?.find((item) => item.id === state.spritePickerActorId);
  const options = byId("actor-sprite-options");
  if (!actor) {
    options.innerHTML = `<div class="empty-state">actorが選択されていません。</div>`;
    return;
  }
  const assetIds = actor.kind === "prop"
    ? ["prop"]
    : ["character", "pc_character"];
  const capacities = Object.fromEntries(
    assetIds.map((assetId) => [assetId, actorSpriteCapacity(assetId)]),
  );
  const ready = assetIds.every((assetId) => capacities[assetId] > 0);
  const selectedAssetId = actorAssetId(actor);
  byId("actor-sprite-dialog-title").textContent = actor.kind === "prop" ? "固定物のスプライトを選択" : "キャラクターのスプライトを選択";
  byId("actor-sprite-dialog-summary").textContent = ready
    ? (actor.kind === "prop"
      ? `${capacities.prop}件`
      : `NPC ${capacities.character}件・PC ${capacities.pc_character}件・下向きの画像で表示`)
    : "画像を読み込んでいます…";
  options.innerHTML = ready
    ? assetIds.flatMap((assetId) => Array.from(
      { length: capacities[assetId] },
      (_, index) => {
        const selected = assetId === selectedAssetId && index === actor.sprite_index;
        const label = assetId === "pc_character" ? `PC #${index}` : assetId === "character" ? `NPC #${index}` : `#${index}`;
        return `<button class="actor-sprite-option ${selected ? "selected" : ""}" type="button" role="option" aria-selected="${selected}" data-action="select-actor-sprite" data-asset-id="${assetId}" data-sprite-index="${index}"><canvas width="48" height="64" data-actor-sprite-option="${index}" data-asset-id="${assetId}"></canvas><span>${label}</span></button>`;
      },
    )).join("")
    : `<div class="empty-state">スプライト画像を表示できません。</div>`;
  options.querySelectorAll("[data-actor-sprite-option]").forEach((canvas) => {
    drawActorSprite(canvas, canvas.dataset.assetId, Number(canvas.dataset.actorSpriteOption));
  });
}

function openActorSpriteDialog() {
  const actor = currentActor();
  if (!actor || actor.kind === "treasure") return;
  state.spritePickerActorId = actor.id;
  renderActorSpriteDialog();
  byId("actor-sprite-dialog").showModal();
}

function closeActorSpriteDialog() {
  const dialog = byId("actor-sprite-dialog");
  if (dialog.open) dialog.close();
}

function selectActorSprite(assetId, spriteIndex) {
  const actor = state.data?.actors?.find((item) => item.id === state.spritePickerActorId);
  const permittedAssetIds = actor?.kind === "prop"
    ? ["prop"]
    : ["character", "pc_character"];
  if (!actor || !permittedAssetIds.includes(assetId) || !Number.isInteger(spriteIndex) || spriteIndex < 0 || spriteIndex >= actorSpriteCapacity(assetId)) return;
  const spriteSource = assetId === "pc_character" ? "pc" : "npc";
  if (actor.sprite_index !== spriteIndex || (actor.sprite_source || "npc") !== spriteSource) commit(() => {
    actor.sprite_index = spriteIndex;
    if (actor.kind === "prop") delete actor.sprite_source;
    else actor.sprite_source = spriteSource;
  });
  closeActorSpriteDialog();
}

function renderPalette() {
  if (!state.tileset) return;
  const container = byId("palette-content");
  if (state.tab === "ground") {
    container.innerHTML = `
      <div class="section">
        <div class="section-title"><h2>地面</h2><span class="subtle">塗り方を選択</span></div>
        <div class="row" role="group" aria-label="地面の塗り方" style="margin-bottom:9px">
          <button class="button small ${state.groundTool === "brush" ? "secondary" : "ghost"}" type="button" data-action="select-ground-tool" data-tool="brush" aria-pressed="${state.groundTool === "brush"}">ブラシ</button>
          <button class="button small ${state.groundTool === "rectangle" ? "secondary" : "ghost"}" type="button" data-action="select-ground-tool" data-tool="rectangle" aria-pressed="${state.groundTool === "rectangle"}">矩形塗り</button>
        </div>
        <p class="subtle" style="margin-bottom:9px">${state.groundTool === "rectangle" ? "左ドラッグした矩形をまとめて塗ります。" : "左ドラッグで通過したセルを塗ります。"}外周1マスはゲーム内では表示されず、進入もできません。</p>
        <div class="palette-list">${state.tileset.grounds.map((ground, index) => `
          <button class="palette-item ${ground.id === state.groundId ? "active" : ""}" type="button" data-action="select-ground" data-id="${escapeHtml(ground.id)}">
            <canvas data-ground-thumb="${index}" width="48" height="48"></canvas><span>${escapeHtml(ground.id)}</span>
          </button>`).join("")}</div>
      </div>`;
  } else if (state.tab === "object") {
    const allLayers = state.objectLayer === "all";
    const paletteObjects = state.tileset.objects.filter((object) => allLayers || objectLayerEditable(object));
    container.innerHTML = `
      <div class="section">
        <div class="section-title"><h2>オブジェクト</h2></div>
        <div class="object-layer-tabs" role="group" aria-label="編集レイヤー">
          ${OBJECT_LAYERS.map(([layer, label]) => `<button class="button small ${layer === state.objectLayer ? "secondary" : "ghost"}" type="button" data-action="select-object-layer" data-layer="${layer}" aria-pressed="${layer === state.objectLayer}">${label}</button>`).join("")}
        </div>
        <p class="subtle object-layer-help">${allLayers ? "全レイヤーのグループ選択・移動・削除専用です。新規配置・単体選択はできません。" : "選択中レイヤーのみ配置・選択・移動できます。他レイヤーは半透明で表示します。"}</p>
        <div class="palette-list">${paletteObjects.map((object) => `
          <button class="palette-item ${object.id === state.objectId ? "active" : ""}" type="button" ${allLayers ? "disabled" : `data-action="select-object-definition"`} data-id="${escapeHtml(object.id)}">
            <canvas data-object-thumb="${state.tileset.objects.indexOf(object)}" width="${object.size[0] * 16}" height="${object.size[1] * 16}"></canvas><span>${escapeHtml(object.id)}</span>${object.default_draw_group !== "object_y_sorted" ? `<span class="palette-meta">${escapeHtml(objectDrawGroupLabel(object))}</span>` : ""}
          </button>`).join("") || `<div class="empty-state">このレイヤーのオブジェクト定義がありません。</div>`}</div>
        </div>`;
  } else if (state.tab === "site") {
    const isWorld = state.data.profile === "world";
    const siteLabel = isWorld ? "拠点" : "移動口";
    container.innerHTML = `
      <div class="section">
        <div class="section-title"><h2>${siteLabel}</h2><span class="subtle">${state.data.sites.length}件</span></div>
        <div class="travel-list">${state.data.sites.map((site) => `
          <button class="travel-item ${site.id === state.selectedSiteId ? "active" : ""}" type="button" data-action="select-site" data-id="${escapeHtml(site.id)}">
            <strong>${escapeHtml(site.id)}</strong>${isWorld ? escapeHtml(state.siteNamesJa[site.id] || "日本語名未入力") : escapeHtml(siteDestinationSummary(site))}
          </button>`).join("") || `<div class="empty-state">${siteLabel}がありません。</div>`}</div>
        <div class="row" style="margin-top:9px"><button class="button secondary small" type="button" data-action="prepare-cell-site">座標${siteLabel}を追加</button></div>
      </div>
      <div class="section">
        <div class="section-title"><h2>到着地点</h2><span class="subtle">${state.data.arrival_points.length}件</span></div>
        <div class="travel-list">${state.data.arrival_points.map((arrival) => `
          <button class="travel-item ${arrival.id === state.selectedArrivalId ? "active" : ""}" type="button" data-action="select-arrival" data-id="${escapeHtml(arrival.id)}">
            <strong>${escapeHtml(arrival.id)}</strong>${arrival.position.join(", ")} / ${escapeHtml(arrival.facing)}${arrival.teleport_enabled ? " / テレポート対象" : ""}
          </button>`).join("") || `<div class="empty-state">到着地点がありません。</div>`}</div>
        <div class="row" style="margin-top:9px"><button class="button secondary small" type="button" data-action="prepare-arrival">到着地点を追加</button></div>
      </div>`;
  } else {
    container.innerHTML = `
      <div class="section">
        <div class="section-title"><h2>actor</h2><span class="subtle">${state.data.actors.length}件</span></div>
        <div class="travel-list">${state.data.actors.map((actor) => `
          <button class="travel-item ${actor.id === state.selectedActorId ? "active" : ""}" type="button" data-action="select-actor" data-id="${escapeHtml(actor.id)}"><strong>${escapeHtml(actor.id)}</strong>${actor.position.join(", ")} / ${escapeHtml(actor.kind)}${actor.kind === "treasure" ? "" : ` / ${actorSpriteLabel(actor)}`}</button>`).join("") || `<div class="empty-state">actorがありません。</div>`}</div>
        <div class="row" style="margin-top:9px"><button class="button secondary small" type="button" data-action="prepare-actor">actorを配置</button></div>
      </div>
      <div class="section">
        <div class="section-title"><h2>トリガー</h2><span class="subtle">${standaloneTriggers().length}件</span></div>
        <div class="travel-list">${standaloneTriggers().map((trigger) => `
          <button class="travel-item ${trigger.id === state.selectedTriggerId ? "active" : ""}" type="button" data-action="select-trigger" data-id="${escapeHtml(trigger.id)}"><strong>${escapeHtml(trigger.event_id)}</strong><span class="event-note">${escapeHtml(eventNote(trigger.event_id) || "メモなし")}</span></button>`).join("") || `<div class="empty-state">トリガーがありません。</div>`}</div>
        <div class="row" style="margin-top:9px"><button class="button secondary small" type="button" data-action="prepare-cell-trigger">セルtrigger</button><button class="button ghost small" type="button" data-action="prepare-object-trigger" ${state.data.objects.length ? "" : "disabled"}>object trigger</button></div>
      </div>`;
  }
  drawPaletteThumbs();
  updateToolStatus();
}

function drawPaletteThumbs() {
  document.querySelectorAll("[data-ground-thumb]").forEach((canvas) => {
    const ground = state.tileset.grounds[Number(canvas.dataset.groundThumb)];
    const context = canvas.getContext("2d");
    context.clearRect(0, 0, canvas.width, canvas.height);
    for (const layer of groundStack(ground.id)) drawSourceTile(context, firstTile(layer.base_visual), 0, 0, 48);
  });
  document.querySelectorAll("[data-object-thumb]").forEach((canvas) => {
    const object = state.tileset.objects[Number(canvas.dataset.objectThumb)];
    const context = canvas.getContext("2d");
    context.clearRect(0, 0, canvas.width, canvas.height);
    for (const cell of object.cells) drawSourceTile(context, cell.tile || firstTile(cell.visual), cell.offset[0] * 16, cell.offset[1] * 16, 16);
  });
}

function currentInstance() {
  return state.data?.objects?.find((instance) => instance.id === state.selectedInstanceId) || null;
}

function currentSite() {
  return state.data?.sites?.find((site) => site.id === state.selectedSiteId) || null;
}

function currentArrival() {
  return state.data?.arrival_points?.find((arrival) => arrival.id === state.selectedArrivalId) || null;
}

function currentActor() {
  return state.data?.actors?.find((actor) => actor.id === state.selectedActorId) || null;
}

function currentTrigger() {
  return state.data?.event_triggers?.find((trigger) => trigger.id === state.selectedTriggerId) || null;
}

function actorTrigger(actorId) {
  return state.data?.event_triggers?.find((trigger) => trigger.anchor?.kind === "actor" && trigger.anchor.actor_id === actorId) || null;
}

function standaloneTriggers() {
  return state.data?.event_triggers?.filter((trigger) => trigger.anchor?.kind !== "actor") || [];
}

function eventNote(eventId) {
  return state.eventNotes?.[eventId]?.trim() || "";
}

function eventIdOptions(selected) {
  const ids = [...state.eventOptions];
  if (selected && !ids.includes(selected)) ids.push(selected);
  return `<option value="" ${selected ? "" : "selected"}>イベントを選択</option>` + ids.map((id) => {
    const characters = Array.from(eventNote(id).replace(/\s+/g, " "));
    const summary = characters.slice(0, 20).join("") + (characters.length > 20 ? "…" : "");
    return `<option value="${escapeHtml(id)}" ${id === selected ? "selected" : ""}>${escapeHtml(id)}${summary ? ` — ${escapeHtml(summary)}` : ""}${state.eventOptions.includes(id) ? "" : "（未定義）"}</option>`;
  }).join("");
}

function treasureItemOptions(selected) {
  return state.itemOptions.map((item) => `<option value="${escapeHtml(item.key)}" ${item.key === selected ? "selected" : ""}>${escapeHtml(item.name_ja)} (${escapeHtml(item.key)})</option>`).join("");
}

function siteDestinationSummary(site) {
  const mapId = site?.destination?.map_id;
  const arrivalId = site?.destination?.arrival_id;
  if (!mapId && !arrivalId) return "移動先未設定";
  return `移動先: ${mapId || "—"} / ${arrivalId || "—"}`;
}

function triggerAnchorPosition(trigger) {
  if (trigger?.anchor?.kind === "cell") return trigger.anchor.position;
  if (trigger?.anchor?.kind === "object") return state.data.objects.find((item) => item.id === trigger.anchor.object_id)?.origin || null;
  if (trigger?.anchor?.kind === "actor") return state.data.actors.find((item) => item.id === trigger.anchor.actor_id)?.position || null;
  return null;
}

function triggerPositions(trigger) {
  const origin = triggerAnchorPosition(trigger);
  return origin ? trigger.offsets.map((offset) => addPoint(origin, offset)) : [];
}

function siteForObject(objectId) {
  return state.data?.sites?.find((site) => site.anchor?.kind === "object" && site.anchor.object_id === objectId) || null;
}

function siteNameTextKey(siteId) {
  return `location.${siteId}`;
}

function objectFlagOptions(selected) {
  const flags = [...state.flagOptions];
  if (selected && !flags.some((flag) => flag.flag_id === selected)) flags.push({ flag_id: selected, note: "未定義" });
  return `<option value="">選択してください</option>` + flags.map((flag) =>
    `<option value="${escapeHtml(flag.flag_id)}" ${selected === flag.flag_id ? "selected" : ""}>${escapeHtml(flag.flag_id)}${flag.note ? ` — ${escapeHtml(flag.note)}` : ""}</option>`
  ).join("");
}

function visibilityInspector(instance, kind = "object") {
  const condition = instance.visibility_condition;
  return `<div class="field" style="margin-top:9px"><label>表示条件</label>
    <select data-${kind}-field="visibility_enabled"><option value="false" ${condition ? "" : "selected"}>常に表示</option><option value="true" ${condition ? "selected" : ""} ${state.flagOptions.length || condition ? "" : "disabled"}>フラグで指定</option></select></div>
    ${condition ? `<div class="field"><label>フラグ</label><select data-${kind}-field="flag_id">${objectFlagOptions(condition.flag_id)}</select></div>
    <div class="field"><label>表示する状態</label><select data-${kind}-field="flag_value"><option value="true" ${condition.value === true ? "selected" : ""}>ONのとき</option><option value="false" ${condition.value === false ? "selected" : ""}>OFFのとき</option></select></div>` : ""}
    ${state.flagOptions.length ? "" : `<div class="field-note">フラグはイベントエディタで登録してください。</div>`}`;
}

function bulkSelectionSummary() {
  const labels = { object: "オブジェクト", site: "拠点", arrival: "到着地点", actor: "actor", trigger: "トリガー" };
  const counts = new Map();
  for (const item of state.bulkSelection) counts.set(item.kind, (counts.get(item.kind) || 0) + 1);
  return Object.entries(labels)
    .filter(([kind]) => counts.has(kind))
    .map(([kind, label]) => `${label} ${counts.get(kind)}`)
    .join(" / ");
}

function availableDestinations() {
  const options = state.destinationOptions.map((option) => ({
    map_id: option.map_id,
    label: option.label || option.map_id,
    arrival_ids: [...option.arrival_ids],
  }));
  const current = options.find((option) => option.map_id === state.data.map_id);
  const arrivalIds = state.data.arrival_points.map((arrival) => arrival.id);
  const currentLabel = state.data.area_name ? `${logicalMapId()} / ${state.data.area_name}` : state.data.map_id;
  if (current) {
    current.arrival_ids = arrivalIds;
    current.label = currentLabel;
  } else options.push({ map_id: state.data.map_id, label: currentLabel, arrival_ids: arrivalIds });
  return options.sort((left, right) => left.label.localeCompare(right.label, "ja", { numeric: true })
    || left.map_id.localeCompare(right.map_id));
}

function destinationMapOptions(selected) {
  const options = availableDestinations();
  if (selected && !options.some((option) => option.map_id === selected)) options.push({ map_id: selected, label: `${selected}（未作成）` });
  return `<option value="" ${selected ? "" : "selected"}>選択してください</option>` + options.map((option) => `<option value="${escapeHtml(option.map_id)}" ${selected === option.map_id ? "selected" : ""}>${escapeHtml(option.label)}</option>`).join("");
}

function destinationArrivalOptions(mapId, selected) {
  const destination = availableDestinations().find((option) => option.map_id === mapId);
  const arrivalIds = destination ? [...destination.arrival_ids] : [];
  if (selected && !arrivalIds.includes(selected)) arrivalIds.push(selected);
  const emptyLabel = arrivalIds.length ? "選択してください" : "到着地点がありません";
  return `<option value="" ${selected ? "" : "selected"}>${emptyLabel}</option>` + arrivalIds.map((arrivalId) => `<option value="${escapeHtml(arrivalId)}" ${selected === arrivalId ? "selected" : ""}>${escapeHtml(arrivalId)}${destination?.arrival_ids.includes(arrivalId) ? "" : "（未作成）"}</option>`).join("");
}

function availableSiteIds() {
  const localWorldSiteIds = state.data.profile === "world" ? state.data.sites.map((site) => site.id) : [];
  return [...new Set([...state.siteOptions, ...localWorldSiteIds])].sort();
}

function siteIdOptions(selected) {
  const siteIds = availableSiteIds();
  if (selected && !siteIds.includes(selected)) siteIds.push(selected);
  return `<option value="" ${selected ? "" : "selected"}>選択してください</option>` + siteIds.map((siteId) => `<option value="${escapeHtml(siteId)}" ${selected === siteId ? "selected" : ""}>${escapeHtml(siteId)}</option>`).join("");
}

function facingOptions(selected) {
  return [["up", "上"], ["right", "右"], ["down", "下"], ["left", "左"]]
    .map(([value, label]) => `<option value="${value}" ${selected === value ? "selected" : ""}>${label}</option>`)
    .join("");
}

function renderInspector() {
  if (!state.data) return;
  const [width, height] = state.data.size;
  const instance = currentInstance();
  const site = currentSite();
  const arrival = currentArrival();
  const actor = currentActor();
  const trigger = currentTrigger();
  const linkedActorTrigger = actor ? actorTrigger(actor.id) : null;
  const attachedSite = instance ? siteForObject(instance.id) : null;
  const isWorld = state.data.profile === "world";
  const siteLabel = isWorld ? "拠点" : "移動口";
  const bulkInspector = state.bulkSelection.length ? `
    <div class="section bulk-selection-inspector">
      <div class="section-title"><h2>範囲選択</h2><span class="subtle">${state.bulkSelection.length}件</span></div>
      <div class="instance-card"><strong>${escapeHtml(bulkSelectionSummary())}</strong>選択対象を左ドラッグすると、まとめて移動できます。</div>
      <div class="row end" style="margin-top:9px"><button class="button danger small" type="button" data-action="delete-bulk-selection">選択範囲を削除</button></div>
    </div>` : "";
  const objectInspector = `
    <div class="section">
      <div class="section-title"><h2>選択オブジェクト</h2><span class="subtle">配置数 ${state.data.objects.length}</span></div>
      ${instance ? `
        <div class="instance-card"><strong>${escapeHtml(instance.definition_id)}</strong>ID: ${escapeHtml(instance.id)}<br>起点: ${instance.origin.join(", ")} / ${escapeHtml(objectDrawGroupLabel(objectDefinition(instance)))}</div>
        ${visibilityInspector(instance)}
        <div class="row end" style="margin-top:9px">
          <button class="button danger small" type="button" data-action="delete-instance">配置を削除</button>
        </div>
        ${isWorld ? `<div class="row" style="margin-top:9px"><button class="button secondary small" type="button" data-action="${attachedSite ? "open-attached-site" : "attach-site"}">${attachedSite ? `拠点 ${escapeHtml(attachedSite.id)} を編集` : "拠点として設定"}</button></div>` : ""}`
        : `<div class="empty-state">${state.objectLayer === "all" ? "全てモードでは範囲選択したオブジェクトの移動・削除だけができます。" : "マップ上の選択中レイヤーのオブジェクトを右クリックすると選択できます。"}</div>`}
    </div>`;
  const siteInspector = `
    <div class="section">
      <div class="section-title"><h2>選択${siteLabel}</h2><span class="subtle">${state.data.sites.length}件</span></div>
      ${site ? `
        <div class="instance-card"><strong>${escapeHtml(site.id)}</strong>アンカー: ${site.anchor.kind === "object" ? `オブジェクト ${escapeHtml(site.anchor.object_id)}` : `セル ${site.anchor.position.join(", ")}`}<br>入口: ${site.entrance_offsets.length}セル</div>
        <div class="form-grid" style="margin-top:9px">
          <div class="field full">
            <label>${siteLabel}ID</label>
            <input type="text" value="${escapeHtml(site.id)}" data-site-field="id">
            ${isWorld ? `<div class="field-note">文言キー：${escapeHtml(siteNameTextKey(site.id))}</div>` : `<div class="field-note">この移動口の名称はゲーム中に表示されません。</div>`}
          </div>
          ${isWorld ? `<div class="field full"><label>日本語名</label><input type="text" value="${escapeHtml(state.siteNamesJa[site.id] || "")}" data-site-name-ja="true"></div>` : ""}
          <div class="field"><label>移動先マップID</label><select data-site-field="destination.map_id">${destinationMapOptions(site.destination.map_id)}</select></div>
          <div class="field"><label>移動先到着地点ID</label><select data-site-field="destination.arrival_id">${destinationArrivalOptions(site.destination.map_id, site.destination.arrival_id)}</select></div>
        </div>
        <div class="row" style="margin-top:9px">
          <button class="button ghost small" type="button" data-action="edit-site-entrances">入口セルを編集</button>
        </div>
        <div class="row end" style="margin-top:9px"><button class="button danger small" type="button" data-action="delete-site">${siteLabel}を削除</button></div>
      ` : `<div class="empty-state">左の一覧またはキャンバスから${siteLabel}を選択してください。</div>`}
    </div>
    <div class="section">
      <div class="section-title"><h2>選択到着地点</h2><span class="subtle">${state.data.arrival_points.length}件</span></div>
      ${arrival ? `
        <div class="instance-card"><strong>${escapeHtml(arrival.id)}</strong>セル: ${arrival.position.join(", ")}</div>
        <div class="form-grid" style="margin-top:9px">
          <div class="field full"><label>到着地点ID</label><input type="text" value="${escapeHtml(arrival.id)}" data-arrival-field="id"></div>
          <div class="field full"><label>到着時の向き</label><select data-arrival-field="facing">${facingOptions(arrival.facing)}</select></div>
          <div class="field full"><label><input type="checkbox" data-arrival-field="teleport_enabled" ${arrival.teleport_enabled ? "checked" : ""}> テレポート対象にする</label></div>
          ${arrival.teleport_enabled ? `<div class="field full"><label>対応拠点</label><select data-arrival-field="site_id">${siteIdOptions(arrival.site_id)}</select></div>` : ""}
        </div>
        <div class="row end" style="margin-top:9px"><button class="button danger small" type="button" data-action="delete-arrival">到着地点を削除</button></div>
      ` : `<div class="empty-state">左の一覧またはキャンバスから到着地点を選択してください。</div>`}
    </div>`;
  const eventInspector = `
    <div class="section">
      <div class="section-title"><h2>選択actor</h2><span class="subtle">${state.data.actors.length}件</span></div>
      ${actor ? `<div class="instance-card"><strong>${escapeHtml(actor.id)}</strong>セル: ${actor.position.join(", ")}</div>
        <div class="form-grid" style="margin-top:9px">
          <div class="field full"><label>actor ID</label><input type="text" value="${escapeHtml(actor.id)}" data-actor-field="id"></div>
          <div class="field full"><label>種別</label><select data-actor-field="kind"><option value="prop" ${actor.kind === "prop" ? "selected" : ""}>固定物（向きなし）</option><option value="stationary" ${actor.kind === "stationary" ? "selected" : ""}>固定キャラ</option><option value="roaming" ${actor.kind === "roaming" ? "selected" : ""}>移動キャラ</option><option value="treasure" ${actor.kind === "treasure" ? "selected" : ""}>宝箱</option></select></div>
          ${actor.kind === "treasure"
            ? `<div class="field full"><label>中身の種別</label><select data-treasure-field="type"><option value="gold" ${actor.contents?.type === "gold" ? "selected" : ""}>お金</option><option value="item" ${actor.contents?.type === "item" ? "selected" : ""}>アイテム</option></select></div>
               ${actor.contents?.type === "gold"
                 ? `<div class="field full"><label>金額</label><input type="number" min="1" max="999999" value="${actor.contents.amount}" data-treasure-field="amount"></div>`
                 : `<div class="field full"><label>アイテム</label><select data-treasure-field="item_key">${treasureItemOptions(actor.contents?.item_key)}</select></div>`}`
            : `<div class="field full"><label>スプライト</label><button class="button actor-sprite-select" type="button" data-action="open-actor-sprite-dialog"><canvas width="48" height="72" data-selected-actor-sprite></canvas><span class="actor-sprite-select-copy"><strong>${actorSpriteLabel(actor)}</strong><span>NPC・PC画像から選択</span></span></button></div>
               ${actor.kind === "prop" ? "" : `<div class="field full"><label>向き</label><select data-actor-field="facing">${facingOptions(actor.facing)}</select></div><div class="field full"><label><input type="checkbox" data-actor-field="floating" ${actor.floating ? "checked" : ""}> 浮遊</label></div>`}
               <div class="field full"><label>イベント</label><select data-actor-event-id="true">${eventIdOptions(linkedActorTrigger?.event_id || "")}</select><div class="field-note">touch・interactで自動的に起動します。</div></div>`}
        </div>${visibilityInspector(actor, "actor")}<div class="row between" style="margin-top:9px"><div class="row">${actor.kind !== "treasure" && editorRoute ? `<button class="button secondary small" data-action="add-actor-event">イベントを追加</button>` : ""}${actor.kind !== "treasure" && editorRoute && linkedActorTrigger?.event_id ? `<button class="button secondary small" data-action="open-actor-event">イベント本文を編集</button>` : ""}</div><button class="button danger small" data-action="delete-actor">actorを削除</button></div>` : `<div class="empty-state">actorを選択してください。</div>`}
    </div>
    <div class="section">
      <div class="section-title"><h2>選択トリガー</h2><span class="subtle">${standaloneTriggers().length}件</span></div>
      ${trigger ? `<div class="instance-card"><strong>${escapeHtml(trigger.event_id)}</strong><span class="event-note">${escapeHtml(eventNote(trigger.event_id) || "メモなし")}</span></div>
        <div class="form-grid" style="margin-top:9px">
          <div class="field full"><label>イベント</label><select data-trigger-field="event_id">${eventIdOptions(trigger.event_id)}</select></div>
          <div class="field full"><label>発火方法</label><div class="row">${["step","touch"].map(value => `<label><input type="checkbox" data-trigger-activation="${value}" ${trigger.activations.includes(value) ? "checked" : ""}> ${value}</label>`).join("")}</div></div>
        </div><div class="row between" style="margin-top:9px"><div class="row">${editorRoute ? `<button class="button secondary small" data-action="open-trigger-event">イベント本文を編集</button>` : ""}</div><button class="button danger small" data-action="delete-trigger">triggerを削除</button></div>` : `<div class="empty-state">トリガーを選択してください。</div>`}
    </div>`;
  const bgmOptions = [...new Set([...state.bgmOptions, state.data.bgm_id])]
    .filter(Boolean)
    .sort()
    .map((bgmId) => `<option value="${escapeHtml(bgmId)}" ${bgmId === state.data.bgm_id ? "selected" : ""}>${escapeHtml(bgmId)}</option>`)
    .join("");
  const encounterSettings = state.data.profile === "dungeon" ? `
        <div class="field full"><label>エンカウント</label><button class="button secondary" type="button" data-action="open-random-encounter-dialog">エンカウント設定</button></div>` : "";
  byId("inspector-content").innerHTML = `
    <div class="section">
      <div class="section-title"><h2>マップ設定</h2><span class="subtle">${escapeHtml(state.data.profile)} / ${escapeHtml(state.data.tileset_id)}</span></div>
      <div class="form-grid">
        <div class="field full"><label>エリア名</label><input data-map-field="area_name" type="text" value="${escapeHtml(state.data.area_name || "")}" placeholder="例：地下1階"></div>
        <div class="field full"><label>BGM</label><select data-map-field="bgm_id" ${state.data.area_parent_id ? "disabled" : ""}>${bgmOptions}</select></div>
        ${encounterSettings}
        <div class="field"><label>幅</label><input id="map-width" type="number" min="${MIN_MAP_WIDTH}" max="512" value="${width}"></div>
        <div class="field"><label>高さ</label><input id="map-height" type="number" min="${MIN_MAP_HEIGHT}" max="512" value="${height}"></div>
        <div class="field"><label>横方向</label><select id="resize-horizontal"><option value="left" ${state.resizeHorizontal === "left" ? "selected" : ""}>左側を増減</option><option value="right" ${state.resizeHorizontal === "right" ? "selected" : ""}>右側を増減</option></select></div>
        <div class="field"><label>縦方向</label><select id="resize-vertical"><option value="up" ${state.resizeVertical === "up" ? "selected" : ""}>上側を増減</option><option value="down" ${state.resizeVertical === "down" ? "selected" : ""}>下側を増減</option></select></div>
      </div>
      <div class="row between" style="margin-top:9px">
        <button class="button ghost small" type="button" data-action="reroll">見た目を振り直す</button>
        <button class="button secondary small" type="button" data-action="resize-map">寸法を反映</button>
      </div>
    </div>
    ${bulkInspector}
    ${state.tab === "site" ? siteInspector : state.tab === "event" ? eventInspector : objectInspector}`;
  drawSelectedActorSprite();
}

function renderIssues() {
  const issues = byId("issues");
  const errors = state.diagnostics.filter((issue) => issue.severity === "error").length;
  const warnings = state.diagnostics.filter((issue) => issue.severity === "warning").length;
  byId("issue-count").textContent = errors ? `${errors} error / ${warnings} warning` : `${warnings} warning`;
  issues.innerHTML = state.diagnostics.length ? state.diagnostics.map((issue) => `<div class="issue ${issue.severity}"><strong>${escapeHtml(issue.path)} · ${escapeHtml(issue.code)}</strong><p>${escapeHtml(issue.message)}</p></div>`).join("") : `<div class="empty-state">問題はありません。</div>`;
  updateSaveState();
}

function renderAll() {
  if (!state.data) return;
  renderMapSelector();
  normalizeSelections();
  clearSelectionsOutsideTab(state.tab);
  document.querySelectorAll(".tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === state.tab));
  byId("grid-toggle").checked = state.showGrid;
  byId("collision-toggle").checked = state.showCollision;
  byId("ground-only-toggle").checked = state.showGroundOnly;
  byId("ground-only-control").hidden = state.tab !== "ground";
  byId("animation-toggle").textContent = state.paused ? "再生" : "一時停止";
  byId("zoom-label").textContent = `${state.zoom}×`;
  byId("map-title").textContent = state.data.area_name ? `${logicalMapId()} / ${state.data.area_name}` : state.data.map_id;
  byId("map-summary").textContent = `${state.data.size[0]}×${state.data.size[1]} cells · ${state.data.objects.length} objects · ${state.data.sites.length} sites · ${state.data.event_triggers.length} triggers`;
  renderPalette();
  renderInspector();
  renderIssues();
  drawMap(performance.now());
}

function frameTile(display, now) {
  const frames = display?.frames || [];
  if (!frames.length) return null;
  if (state.paused) return frames[0];
  const interval = Math.max(1, Number(display.frame_interval) || 1);
  const index = Math.floor((now - state.animationStartedAt) / (1000 / 60 * interval)) % frames.length;
  return frames[index];
}

function siteAnchorPosition(site) {
  if (site?.anchor?.kind === "cell") return site.anchor.position;
  if (site?.anchor?.kind === "object") {
    return state.data.objects.find((instance) => instance.id === site.anchor.object_id)?.origin || null;
  }
  return null;
}

function addPoint(origin, offset) {
  return origin && offset ? [origin[0] + offset[0], origin[1] + offset[1]] : null;
}

function siteEntrancePositions(site) {
  const origin = siteAnchorPosition(site);
  return origin ? site.entrance_offsets.map((offset) => addPoint(origin, offset)) : [];
}

function siteFocusPosition(site) {
  const positions = siteEntrancePositions(site);
  if (!positions.length) return siteAnchorPosition(site);
  const xs = positions.map((position) => position[0]);
  const ys = positions.map((position) => position[1]);
  return [
    (Math.min(...xs) + Math.max(...xs)) / 2,
    (Math.min(...ys) + Math.max(...ys)) / 2,
  ];
}

function centerMapOnPosition(position) {
  if (!position) return;
  const scroll = byId("map-scroll");
  const scale = CELL_SIZE * state.zoom;
  scroll.scrollLeft = (position[0] + .5) * scale - scroll.clientWidth / 2;
  scroll.scrollTop = (position[1] + .5) * scale - scroll.clientHeight / 2;
}

function drawDirectionMarker(context, position, facing, scale, color) {
  if (!position) return;
  const centerX = (position[0] + .5) * scale;
  const centerY = (position[1] + .5) * scale;
  const distance = scale * .25;
  const directions = { up: [0, -1], right: [1, 0], down: [0, 1], left: [-1, 0] };
  const [dx, dy] = directions[facing] || [0, 1];
  context.strokeStyle = color;
  context.fillStyle = color;
  context.lineWidth = Math.max(2, state.zoom);
  context.beginPath();
  context.moveTo(centerX - dx * distance, centerY - dy * distance);
  context.lineTo(centerX + dx * distance, centerY + dy * distance);
  context.stroke();
  context.beginPath();
  context.arc(centerX + dx * distance, centerY + dy * distance, Math.max(3, state.zoom * 2), 0, Math.PI * 2);
  context.fill();
}

function drawCellSelectionFrame(context, position, scale) {
  context.strokeStyle = "#ff67bd";
  context.lineWidth = Math.max(2, state.zoom * 2);
  context.strokeRect(position[0] * scale + 1, position[1] * scale + 1, scale - 2, scale - 2);
}

function drawTravelMarkers(context, scale) {
  const emphasized = state.tab === "site";
  for (const site of state.data.sites) {
    const selected = site.id === state.selectedSiteId || isBulkSelected("site", site.id);
    const origin = siteAnchorPosition(site);
    context.lineWidth = Math.max(selected ? 3 : emphasized ? 2.5 : 2, state.zoom);
    for (const entrance of siteEntrancePositions(site)) {
      context.fillStyle = selected ? "rgba(47,196,255,.52)" : emphasized ? "rgba(47,196,255,.40)" : "rgba(47,196,255,.24)";
      context.strokeStyle = selected ? "#71ddff" : emphasized ? "#49c7f4" : "rgba(49,155,192,.78)";
      context.fillRect(entrance[0] * scale, entrance[1] * scale, scale, scale);
      context.strokeRect(entrance[0] * scale + 1, entrance[1] * scale + 1, scale - 2, scale - 2);
      if (selected) drawCellSelectionFrame(context, entrance, scale);
    }
    if (site.anchor?.kind === "cell" && origin) {
      context.strokeStyle = selected ? "#ff67bd" : emphasized ? "#d75ca0" : "rgba(157,71,121,.72)";
      context.beginPath();
      context.moveTo(origin[0] * scale + scale * .2, origin[1] * scale + scale * .2);
      context.lineTo((origin[0] + .8) * scale, (origin[1] + .8) * scale);
      context.moveTo((origin[0] + .8) * scale, origin[1] * scale + scale * .2);
      context.lineTo(origin[0] * scale + scale * .2, (origin[1] + .8) * scale);
      context.stroke();
    }
  }
  for (const arrival of state.data.arrival_points) {
    const selected = arrival.id === state.selectedArrivalId || isBulkSelected("arrival", arrival.id);
    const color = selected ? "#91f090" : emphasized ? "#66db79" : "rgba(75,150,82,.78)";
    context.fillStyle = selected ? "rgba(95,232,120,.52)" : emphasized ? "rgba(95,232,120,.40)" : "rgba(95,232,120,.22)";
    context.strokeStyle = color;
    context.lineWidth = Math.max(selected ? 3 : emphasized ? 2.5 : 2, state.zoom);
    context.fillRect(arrival.position[0] * scale + 3, arrival.position[1] * scale + 3, scale - 6, scale - 6);
    context.strokeRect(arrival.position[0] * scale + 5, arrival.position[1] * scale + 5, scale - 10, scale - 10);
    drawDirectionMarker(context, arrival.position, arrival.facing, scale, color);
    if (selected) drawCellSelectionFrame(context, arrival.position, scale);
  }
}

function drawEventMarkers(context, scale) {
  const emphasized = state.tab === "event";
  for (const trigger of standaloneTriggers()) {
    const selected = trigger.id === state.selectedTriggerId || isBulkSelected("trigger", trigger.id);
    context.fillStyle = selected ? "rgba(255,79,163,.52)" : emphasized ? "rgba(224,184,90,.40)" : "rgba(224,184,90,.22)";
    context.strokeStyle = selected ? "#ff67bd" : emphasized ? "#e9c45c" : "rgba(208,169,78,.78)";
    context.lineWidth = Math.max(selected ? 3 : emphasized ? 2.5 : 2, state.zoom);
    for (const position of triggerPositions(trigger)) {
      context.fillRect(position[0] * scale, position[1] * scale, scale, scale);
      context.strokeRect(position[0] * scale + 2, position[1] * scale + 2, scale - 4, scale - 4);
    }
  }
}

function drawActor(context, actor, scale, now) {
  const selected = actor.id === state.selectedActorId || isBulkSelected("actor", actor.id);
  const rendered = drawActorOnMap(context, actor, scale, now);
  if (!rendered) {
    const centerX = (actor.position[0] + .5) * scale;
    const centerY = (actor.position[1] + .5) * scale;
    context.fillStyle = selected ? "#ff67bd" : "#76d7c4";
    context.beginPath();
    context.arc(centerX, centerY, Math.max(5, scale * .22), 0, Math.PI * 2);
    context.fill();
    if (actor.kind === "stationary" || actor.kind === "roaming") drawDirectionMarker(context, actor.position, actor.facing, scale, selected ? "#ffb4dc" : "#b3fff0");
  }
  if (selected) {
    for (const position of actorCells(actor)) drawCellSelectionFrame(context, position, scale);
  }
}

function drawMapObjectCell(context, cell, scale, now) {
  context.save();
  if (state.tab === "object" && state.objectLayer !== "all" && cell.draw_group !== state.objectLayer) context.globalAlpha *= .25;
  drawSourceTile(context, frameTile(cell, now), cell.position[0] * scale, cell.position[1] * scale, scale);
  context.restore();
}

function drawActorsAndYSortedObjects(context, scale, now) {
  const items = state.data.actors.map((actor, index) => ({
    kind: "actor",
    sortY: actor.position[1],
    tieOrder: 1,
    order: index,
    x: actor.position[0],
    id: actor.id,
    actor,
  }));
  const instances = new Map();
  for (const cell of state.resolved?.object_cells || []) {
    if (cell.draw_group !== "object_y_sorted" && cell.draw_group !== "object_foreground") continue;
    if (!instances.has(cell.instance_id)) instances.set(cell.instance_id, []);
    instances.get(cell.instance_id).push(cell);
  }
  for (const [instanceId, cells] of instances) {
    const first = cells[0];
    items.push({
      kind: "object",
      sortY: first.sort_y ?? Math.max(...cells.map((cell) => cell.position[1])),
      tieOrder: first.draw_group === "object_foreground" ? 2 : 0,
      order: first.order,
      x: Math.min(...cells.map((cell) => cell.position[0])),
      id: instanceId,
      cells,
    });
  }
  items.sort((left, right) => left.sortY - right.sortY
    || left.tieOrder - right.tieOrder
    || left.order - right.order
    || left.x - right.x
    || left.id.localeCompare(right.id));
  for (const item of items) {
    if (item.kind === "actor") drawActor(context, item.actor, scale, now);
    else for (const cell of item.cells) drawMapObjectCell(context, cell, scale, now);
  }
}

function drawObjectOutline(context, instance, scale, highlighted = false) {
  const definition = objectDefinition(instance);
  if (!definition) return;
  const positions = new Set(definition.cells.map((cell) => addPoint(instance.origin, cell.offset).join(",")));
  const selected = instance.id === state.selectedInstanceId || isBulkSelected("object", instance.id);
  context.save();
  context.fillStyle = "rgba(255,79,163,.18)";
  context.strokeStyle = selected ? "#ff67bd" : "rgba(255,103,189,.82)";
  context.lineWidth = Math.max(2, selected ? state.zoom * 2 : state.zoom);
  context.beginPath();
  for (const position of positions) {
    const [x, y] = position.split(",").map(Number);
    if (highlighted) context.fillRect(x * scale, y * scale, scale, scale);
    if (!positions.has(`${x},${y - 1}`)) { context.moveTo(x * scale, y * scale); context.lineTo((x + 1) * scale, y * scale); }
    if (!positions.has(`${x + 1},${y}`)) { context.moveTo((x + 1) * scale, y * scale); context.lineTo((x + 1) * scale, (y + 1) * scale); }
    if (!positions.has(`${x},${y + 1}`)) { context.moveTo(x * scale, (y + 1) * scale); context.lineTo((x + 1) * scale, (y + 1) * scale); }
    if (!positions.has(`${x - 1},${y}`)) { context.moveTo(x * scale, y * scale); context.lineTo(x * scale, (y + 1) * scale); }
  }
  context.stroke();
  context.restore();
}

function drawTabCellHighlights(context, scale) {
  if (state.tab !== "object" && state.tab !== "event") return;
  if (state.tab === "object") {
    for (const instance of state.data.objects) {
      if (objectLayerEditable(objectDefinition(instance))) drawObjectOutline(context, instance, scale, true);
    }
    return;
  }
  const positions = new Set();
  const addPosition = (position) => {
    if (!position) return;
    const [x, y] = position;
    if (x < 0 || y < 0 || x >= state.data.size[0] || y >= state.data.size[1]) return;
    positions.add(`${x},${y}`);
  };
  for (const actor of state.data.actors) {
    for (const position of actorCells(actor)) addPosition(position);
  }
  for (const trigger of state.data.event_triggers) {
    for (const position of triggerPositions(trigger)) addPosition(position);
  }
  context.save();
  context.fillStyle = "rgba(255,79,163,.18)";
  context.strokeStyle = "rgba(255,103,189,.82)";
  context.lineWidth = Math.max(2, state.zoom);
  for (const key of positions) {
    const [x, y] = key.split(",").map(Number);
    context.fillRect(x * scale + 1, y * scale + 1, scale - 2, scale - 2);
    context.strokeRect(x * scale + 1, y * scale + 1, scale - 2, scale - 2);
  }
  context.restore();
}

function drawRangeSelection(context, scale) {
  if (!state.selectionRect) return;
  const { left, top, right, bottom } = state.selectionRect;
  context.save();
  context.fillStyle = "rgba(255,79,163,.10)";
  context.strokeStyle = "#ff67bd";
  context.lineWidth = Math.max(2, state.zoom);
  context.setLineDash([Math.max(4, state.zoom * 3), Math.max(3, state.zoom * 2)]);
  context.fillRect(left * scale, top * scale, (right - left + 1) * scale, (bottom - top + 1) * scale);
  context.strokeRect(left * scale + 1, top * scale + 1, (right - left + 1) * scale - 2, (bottom - top + 1) * scale - 2);
  context.restore();
}

function drawGroundPaintPreview(context, scale) {
  if (!state.groundPaintRect) return;
  const { left, top, right, bottom } = state.groundPaintRect;
  context.save();
  context.fillStyle = "rgba(224,184,90,.14)";
  context.strokeStyle = "#f0cf7e";
  context.lineWidth = Math.max(2, state.zoom);
  context.setLineDash([Math.max(4, state.zoom * 3), Math.max(3, state.zoom * 2)]);
  context.fillRect(left * scale, top * scale, (right - left + 1) * scale, (bottom - top + 1) * scale);
  context.strokeRect(left * scale + 1, top * scale + 1, (right - left + 1) * scale - 2, (bottom - top + 1) * scale - 2);
  context.restore();
}

function drawObjectPlacementPreview(context, scale) {
  if (state.tab !== "object" || state.objectLayer === "all" || !state.hoveredCell || state.pointerDrag || state.bulkSelection.length) return;
  const definition = state.tileset.objects.find((object) => object.id === state.objectId);
  if (!objectLayerEditable(definition)) return;
  const selected = currentInstance();
  if (selected && instanceOccupies(selected, ...state.hoveredCell)) return;
  const [x, y] = state.hoveredCell;
  const valid = objectIntersectsMap(definition, [x, y])
    && !objectPlacementConflict(definition, [x, y]);
  context.save();
  context.fillStyle = valid ? "rgba(114,183,119,.12)" : "rgba(227,119,107,.14)";
  context.setLineDash([Math.max(4, state.zoom * 3), Math.max(3, state.zoom * 2)]);
  context.fillRect(x * scale, y * scale, definition.size[0] * scale, definition.size[1] * scale);
  context.strokeStyle = "rgba(12,18,11,.88)";
  context.lineWidth = Math.max(4, state.zoom * 2);
  context.strokeRect(x * scale + 1, y * scale + 1, definition.size[0] * scale - 2, definition.size[1] * scale - 2);
  context.strokeStyle = valid ? "#d8ffd9" : "#ff8f84";
  context.lineWidth = Math.max(2, state.zoom);
  context.strokeRect(x * scale + 1, y * scale + 1, definition.size[0] * scale - 2, definition.size[1] * scale - 2);
  context.restore();
}

function drawMap(now) {
  if (!state.data) return;
  const canvas = byId("map-canvas");
  const scale = CELL_SIZE * state.zoom;
  const [width, height] = state.data.size;
  const targetWidth = width * scale;
  const targetHeight = height * scale;
  if (canvas.width !== targetWidth || canvas.height !== targetHeight) {
    canvas.width = targetWidth;
    canvas.height = targetHeight;
  }
  const context = canvas.getContext("2d");
  const groundOnly = state.tab === "ground" && state.showGroundOnly;
  context.clearRect(0, 0, canvas.width, canvas.height);
  if (state.resolved) {
    state.resolved.ground_cells.forEach((cell, index) => {
      const x = (index % width) * scale;
      const y = Math.floor(index / width) * scale;
      for (const layer of cell.layers) drawSourceTile(context, frameTile(layer, now), x, y, scale);
    });
    if (!groundOnly) for (const cell of state.resolved.object_cells) {
      if (cell.draw_group !== "object") continue;
      drawMapObjectCell(context, cell, scale, now);
    }
  }
  if (!groundOnly) drawActorsAndYSortedObjects(context, scale, now);
  if (state.resolved && !groundOnly) {
    for (const cell of state.resolved.object_cells) {
      if (cell.draw_group !== "object_overlay") continue;
      drawMapObjectCell(context, cell, scale, now);
    }
  }
  context.save();
  context.fillStyle = "rgba(0,0,0,.55)";
  context.fillRect(0, 0, targetWidth, scale);
  context.fillRect(0, targetHeight - scale, targetWidth, scale);
  context.fillRect(0, scale, scale, targetHeight - scale * 2);
  context.fillRect(targetWidth - scale, scale, scale, targetHeight - scale * 2);
  context.restore();
  if (!groundOnly) drawTabCellHighlights(context, scale);
  if (!groundOnly && state.tab !== "object") for (const selected of state.data.objects.filter((instance) => instance.id === state.selectedInstanceId || isBulkSelected("object", instance.id))) {
    drawObjectOutline(context, selected, scale);
  }
  if (state.resolved && state.showCollision && !groundOnly) {
    context.fillStyle = "rgba(255,32,32,.28)";
    context.strokeStyle = "#ff2020";
    context.lineWidth = Math.max(1, state.zoom);
    state.resolved.collision.forEach((blocked, index) => {
      const cellX = index % width;
      const cellY = Math.floor(index / width);
      const border = cellX === 0 || cellY === 0 || cellX === width - 1 || cellY === height - 1;
      if (!blocked && !border) return;
      const x = cellX * scale;
      const y = cellY * scale;
      context.fillRect(x, y, scale, scale);
      context.strokeRect(x + .5, y + .5, scale - 1, scale - 1);
    });
  }
  if (!groundOnly) {
    drawTravelMarkers(context, scale);
    drawEventMarkers(context, scale);
    drawRangeSelection(context, scale);
  }
  if (state.showGrid) {
    context.strokeStyle = "rgba(238,233,215,.18)";
    context.lineWidth = 1;
    context.beginPath();
    for (let x = 0; x <= width; x += 1) { context.moveTo(x * scale + .5, 0); context.lineTo(x * scale + .5, targetHeight); }
    for (let y = 0; y <= height; y += 1) { context.moveTo(0, y * scale + .5); context.lineTo(targetWidth, y * scale + .5); }
    context.stroke();
  }
  drawGroundPaintPreview(context, scale);
  drawObjectPlacementPreview(context, scale);
  drawSelectedActorSprite(now);
}

function animationLoop(now) {
  const scrolled = updateMapAutoScroll(now);
  if (!state.paused || scrolled) drawMap(now);
  requestAnimationFrame(animationLoop);
}

function updateToolStatus() {
  if (!state.data) return;
  const rangeHint = "右ドラッグ: 配置要素を範囲選択";
  if (state.bulkSelection.length) byId("tool-status").textContent = `${state.bulkSelection.length}件を範囲選択中 / 選択対象を左ドラッグ: 一括移動 / Delete: 一括削除`;
  else if (state.tab === "ground") byId("tool-status").textContent = `${state.groundTool === "rectangle" ? "矩形塗り" : "地面ブラシ"}: ${state.groundId || "—"} / ${rangeHint}`;
  else if (state.tab === "object") byId("tool-status").textContent = state.objectLayer === "all"
    ? "全て: 左／右ドラッグでオブジェクトを範囲選択 / 選択グループをドラッグ: 移動 / Delete: 削除"
    : `左: ${state.objectId || "—"}を配置 / 右クリック: 選択中レイヤーのみ選択 / 右ドラッグ: 同レイヤーを範囲選択`;
  else if (state.tab === "site") {
    const selectedSite = currentSite();
    const labels = {
      select: selectedSite?.anchor?.kind === "cell" ? "ピンクのアンカーを左ドラッグして移動" : "拠点または到着地点を選択",
      create_site: "座標アンカーにするセルを選択",
      entrance: "入口セルをクリックして追加・解除",
      create_arrival: "到着地点にするセルを選択",
    };
    byId("tool-status").textContent = `${labels[state.travelTool] || labels.select} / ${rangeHint}`;
  } else {
    const labels = {
      select: currentTrigger() ? "Shift＋左クリック: trigger対象セルを追加・解除" : "actorまたはtriggerを選択",
      create_actor: "actorを置くセルを選択",
      create_trigger: "triggerの基準セルを選択",
      create_object_trigger: "triggerを設定するobjectを選択",
    };
    byId("tool-status").textContent = `${labels[state.eventTool] || labels.select} / ${rangeHint}`;
  }
}

function mapScrollBounds() {
  const scroll = byId("map-scroll");
  const rect = scroll.getBoundingClientRect();
  const left = rect.left + scroll.clientLeft;
  const top = rect.top + scroll.clientTop;
  return { left, top, right: left + scroll.clientWidth, bottom: top + scroll.clientHeight };
}

function mapCellFromPointer(event, clampToViewport = false) {
  const canvas = byId("map-canvas");
  const rect = canvas.getBoundingClientRect();
  const scale = CELL_SIZE * state.zoom;
  const allowActorOverflow = clampToViewport && (state.pointerDrag?.descriptors?.some((item) => item.kind === "actor")
    || state.pointerDrag?.draggableItem?.kind === "actor");
  let { clientX, clientY } = event;
  if (clampToViewport) {
    const bounds = mapScrollBounds();
    clientX = Math.min(Math.max(clientX, bounds.left), bounds.right - 1);
    clientY = Math.min(Math.max(clientY, bounds.top), bounds.bottom - 1);
    if (allowActorOverflow && rect.bottom <= bounds.bottom + 1 && event.clientY >= rect.bottom) clientY = rect.bottom;
  }
  let x = Math.floor((clientX - rect.left) * canvas.width / rect.width / scale);
  let y = Math.floor((clientY - rect.top) * canvas.height / rect.height / scale);
  if (clampToViewport) {
    x = Math.min(Math.max(x, 0), state.data.size[0] - 1);
    y = Math.min(Math.max(y, 0), state.data.size[1] - 1 + (allowActorOverflow ? 1 : 0));
  }
  if (x < 0 || y < 0 || x >= state.data.size[0] || y >= state.data.size[1] + (allowActorOverflow ? 1 : 0)) return null;
  return [x, y];
}

function rememberMapPointer(event) {
  state.dragPointer = { clientX: event.clientX, clientY: event.clientY, pointerId: event.pointerId };
}

function stopMapAutoScroll() {
  state.dragPointer = null;
  state.dragScrollTime = null;
}

function mapDragScrollAmount(position, start, end, elapsed) {
  const direction = position < start ? -1 : position >= end ? 1 : 0;
  if (!direction) return 0;
  const distance = direction < 0 ? start - position : position - end;
  const speed = Math.min(720, 180 + distance * 6);
  return direction * Math.min(CELL_SIZE * state.zoom, speed * elapsed / 1000);
}

function updateMapAutoScroll(now) {
  const drag = state.pointerDrag || state.pointerStroke;
  if (!drag || !state.dragPointer || drag.pointerId !== state.dragPointer.pointerId) {
    stopMapAutoScroll();
    return;
  }
  const elapsed = Math.min(50, Math.max(0, now - (state.dragScrollTime ?? now)));
  state.dragScrollTime = now;
  const bounds = mapScrollBounds();
  const dx = mapDragScrollAmount(state.dragPointer.clientX, bounds.left, bounds.right, elapsed);
  const dy = mapDragScrollAmount(state.dragPointer.clientY, bounds.top, bounds.bottom, elapsed);
  if (!dx && !dy) return;
  const scroll = byId("map-scroll");
  const previousLeft = scroll.scrollLeft;
  const previousTop = scroll.scrollTop;
  scroll.scrollLeft += dx;
  scroll.scrollTop += dy;
  if (scroll.scrollLeft !== previousLeft || scroll.scrollTop !== previousTop) {
    updateMapPointer(state.dragPointer);
    return true;
  }
}

function updateMapPointer(event) {
  const dragging = Boolean(state.pointerDrag || state.pointerStroke);
  const drag = state.pointerDrag || state.pointerStroke;
  if (drag && drag.pointerId !== event.pointerId) return;
  if (dragging) rememberMapPointer(event);
  const cell = mapCellFromPointer(event, dragging);
  byId("cursor-status").textContent = cell ? `セル ${cell[0]}, ${cell[1]}` : "セル —";
  state.hoveredCell = cell ? [...cell] : null;
  if (cell && state.pointerDrag) {
    if (state.pointerDrag.kind === "object") dragObjectTo(cell);
    else if (state.pointerDrag.kind === "site_anchor") dragSiteAnchorTo(cell);
    else if (state.pointerDrag.kind === "range_selection") updateRangeSelection(event, cell);
    else if (state.pointerDrag.kind === "bulk") dragBulkTo(cell);
    else if (state.pointerDrag.kind === "single_selection") dragBulkTo(cell);
    else if (state.pointerDrag.kind === "ground_rectangle") updateGroundRectangle(cell);
    return;
  }
  if (!state.pointerStroke) drawMap(performance.now());
  if (!cell || !state.pointerStroke || state.pointerStroke.last === cell.join(",")) return;
  state.pointerStroke.last = cell.join(",");
  if (paintGround(...cell)) {
    state.pointerStroke.changed = true;
    state.dirty = true;
    scheduleResolution();
    updateSaveState();
  }
}

function cancelMapPointer(event) {
  const drag = state.pointerDrag || state.pointerStroke;
  if (drag && event?.pointerId !== undefined && drag.pointerId !== event.pointerId) return;
  stopMapAutoScroll();
  if (!state.pointerStroke && !state.pointerDrag) return;
  if (state.pointerStroke && !state.pointerStroke.changed) state.history.pop();
  if (state.pointerDrag?.kind === "ground_rectangle") state.history.pop();
  else if (state.pointerDrag && state.pointerDrag.kind !== "range_selection" && !state.pointerDrag.changed) state.history.pop();
  if (state.pointerDrag?.kind === "range_selection") state.selectionRect = null;
  state.pointerStroke = null;
  state.pointerDrag = null;
  state.groundPaintRect = null;
  renderAll();
}

function normalizedCellRect(start, end) {
  return {
    left: Math.min(start[0], end[0]),
    top: Math.min(start[1], end[1]),
    right: Math.max(start[0], end[0]),
    bottom: Math.max(start[1], end[1]),
  };
}

function pointInCellRect(position, rect) {
  return Boolean(position && position[0] >= rect.left && position[0] <= rect.right
    && position[1] >= rect.top && position[1] <= rect.bottom);
}

function rangeSelectionItems(rect) {
  const items = [];
  for (const instance of state.data.objects) {
    const definition = objectDefinition(instance);
    if (state.tab === "object" && !objectLayerEditable(definition)) continue;
    if (definition?.cells.some((cell) => pointInCellRect(addPoint(instance.origin, cell.offset), rect))) {
      items.push({ kind: "object", id: instance.id });
    }
  }
  if (state.tab === "object") return items;
  for (const site of state.data.sites) {
    const origin = siteAnchorPosition(site);
    if (siteEntrancePositions(site).some((position) => pointInCellRect(position, rect))
      || (site.anchor?.kind === "cell" && pointInCellRect(origin, rect))) {
      items.push({ kind: "site", id: site.id });
    }
  }
  for (const arrival of state.data.arrival_points) {
    if (pointInCellRect(arrival.position, rect)) items.push({ kind: "arrival", id: arrival.id });
  }
  for (const actor of state.data.actors) {
    if (actorCells(actor).some((position) => pointInCellRect(position, rect))) items.push({ kind: "actor", id: actor.id });
  }
  for (const trigger of standaloneTriggers()) {
    if (triggerPositions(trigger).some((position) => pointInCellRect(position, rect))) {
      items.push({ kind: "trigger", id: trigger.id });
    }
  }
  return items;
}

function beginRangeSelection(event, cell) {
  const selectedItem = currentSingleSelectionItem();
  state.selectionRect = null;
  state.pointerDrag = {
    kind: "range_selection",
    changed: false,
    pointerId: event.pointerId,
    start: [...cell],
    last: [...cell],
    draggableItem: selectedItem && bulkItemOccupiesCell(selectedItem, cell) ? selectedItem : null,
  };
  mapCanvas.setPointerCapture(event.pointerId);
}

function updateRangeSelection(event, cell) {
  if (state.pointerDrag?.kind !== "range_selection") return;
  if (cell[0] === state.pointerDrag.last[0] && cell[1] === state.pointerDrag.last[1]) return;
  if (!state.pointerDrag.changed && state.pointerDrag.draggableItem
    && isMapSelectionCandidateSelected(state.pointerDrag.draggableItem)) {
    const start = [...state.pointerDrag.start];
    const item = state.pointerDrag.draggableItem;
    if (beginSingleSelectionDrag(event, start, item)) {
      dragBulkTo(cell);
      return;
    }
  }
  if (!state.pointerDrag.changed) {
    clearSingleSelections();
    clearBulkSelection();
    state.travelTool = "select";
    state.eventTool = "select";
  }
  state.pointerDrag.last = [...cell];
  state.pointerDrag.changed = true;
  state.selectionRect = normalizedCellRect(state.pointerDrag.start, cell);
  drawMap(performance.now());
}

function bulkItemOccupiesCell(item, cell) {
  if (item.kind === "object") {
    const instance = state.data.objects.find((record) => record.id === item.id);
    return Boolean(instance && instanceOccupies(instance, ...cell));
  }
  if (item.kind === "site") {
    const site = state.data.sites.find((record) => record.id === item.id);
    const origin = siteAnchorPosition(site);
    return Boolean(site && (siteEntrancePositions(site).some((position) => position[0] === cell[0] && position[1] === cell[1])
      || (site.anchor?.kind === "cell" && origin?.[0] === cell[0] && origin?.[1] === cell[1])));
  }
  if (item.kind === "arrival") {
    const arrival = state.data.arrival_points.find((record) => record.id === item.id);
    return Boolean(arrival && arrival.position[0] === cell[0] && arrival.position[1] === cell[1]);
  }
  if (item.kind === "actor") {
    const actor = state.data.actors.find((record) => record.id === item.id);
    return Boolean(actor && actorOccupiesCell(actor, cell));
  }
  const trigger = standaloneTriggers().find((record) => record.id === item.id);
  return Boolean(trigger && triggerPositions(trigger).some((position) => position[0] === cell[0] && position[1] === cell[1]));
}

function bulkMoveDescriptors() {
  const descriptors = [];
  for (const item of state.bulkSelection) {
    if (item.kind === "object") {
      const record = state.data.objects.find((candidate) => candidate.id === item.id);
      if (record) descriptors.push({ kind: item.kind, id: item.id, position: [...record.origin] });
    } else if (item.kind === "site") {
      const record = state.data.sites.find((candidate) => candidate.id === item.id);
      if (record?.anchor?.kind === "cell") descriptors.push({ kind: item.kind, id: item.id, position: [...record.anchor.position] });
    } else if (item.kind === "arrival") {
      const record = state.data.arrival_points.find((candidate) => candidate.id === item.id);
      if (record) descriptors.push({ kind: item.kind, id: item.id, position: [...record.position] });
    } else if (item.kind === "actor") {
      const record = state.data.actors.find((candidate) => candidate.id === item.id);
      if (record) descriptors.push({ kind: item.kind, id: item.id, position: [...record.position] });
    } else if (item.kind === "trigger") {
      const record = standaloneTriggers().find((candidate) => candidate.id === item.id);
      if (record?.anchor?.kind === "cell") descriptors.push({ kind: item.kind, id: item.id, position: [...record.anchor.position] });
    }
  }
  return descriptors;
}

function currentSingleSelectionItem() {
  if (state.tab === "object" && state.selectedInstanceId) return { kind: "object", id: state.selectedInstanceId, tab: "object" };
  if (state.tab === "site" && state.selectedSiteId) return { kind: "site", id: state.selectedSiteId, tab: "site" };
  if (state.tab === "site" && state.selectedArrivalId) return { kind: "arrival", id: state.selectedArrivalId, tab: "site" };
  if (state.tab === "event" && state.selectedActorId) return { kind: "actor", id: state.selectedActorId, tab: "event" };
  if (state.tab === "event" && state.selectedTriggerId) return { kind: "trigger", id: state.selectedTriggerId, tab: "event" };
  return null;
}

function singleSelectionMoveDescriptors(item) {
  if (item.kind === "object") {
    const record = state.data.objects.find((candidate) => candidate.id === item.id);
    return record ? [{ kind: "object", id: record.id, position: [...record.origin] }] : [];
  }
  if (item.kind === "site") {
    const record = state.data.sites.find((candidate) => candidate.id === item.id);
    if (record?.anchor?.kind === "cell") return [{ kind: "site", id: record.id, position: [...record.anchor.position] }];
    if (record?.anchor?.kind === "object") {
      const object = state.data.objects.find((candidate) => candidate.id === record.anchor.object_id);
      return object ? [{ kind: "object", id: object.id, position: [...object.origin] }] : [];
    }
    return [];
  }
  if (item.kind === "arrival") {
    const record = state.data.arrival_points.find((candidate) => candidate.id === item.id);
    return record ? [{ kind: "arrival", id: record.id, position: [...record.position] }] : [];
  }
  if (item.kind === "actor") {
    const record = state.data.actors.find((candidate) => candidate.id === item.id);
    return record ? [{ kind: "actor", id: record.id, position: [...record.position] }] : [];
  }
  const trigger = standaloneTriggers().find((candidate) => candidate.id === item.id);
  if (trigger?.anchor?.kind === "cell") return [{ kind: "trigger", id: trigger.id, position: [...trigger.anchor.position] }];
  if (trigger?.anchor?.kind === "object") {
    const object = state.data.objects.find((candidate) => candidate.id === trigger.anchor.object_id);
    return object ? [{ kind: "object", id: object.id, position: [...object.origin] }] : [];
  }
  if (trigger?.anchor?.kind === "actor") {
    const actor = state.data.actors.find((candidate) => candidate.id === trigger.anchor.actor_id);
    return actor ? [{ kind: "actor", id: actor.id, position: [...actor.position] }] : [];
  }
  return [];
}

function beginSingleSelectionDrag(event, cell, item) {
  const descriptors = singleSelectionMoveDescriptors(item);
  if (!descriptors.length) return false;
  beginChange();
  state.pointerDrag = {
    kind: "single_selection",
    changed: false,
    pointerId: event.pointerId,
    start: [...cell],
    delta: [0, 0],
    descriptors,
    originalRect: null,
  };
  mapCanvas.setPointerCapture(event.pointerId);
  return true;
}

function beginBulkDrag(event, cell) {
  if (!state.bulkSelection.some((item) => bulkItemOccupiesCell(item, cell))) return false;
  const descriptors = bulkMoveDescriptors();
  if (!descriptors.length) {
    showToast("選択対象は別のアンカーに追従するため、単独では移動できません。", true);
    return true;
  }
  beginChange();
  state.pointerDrag = {
    kind: "bulk",
    changed: false,
    pointerId: event.pointerId,
    start: [...cell],
    delta: [0, 0],
    descriptors,
    originalRect: state.selectionRect ? { ...state.selectionRect } : null,
  };
  mapCanvas.setPointerCapture(event.pointerId);
  return true;
}

function candidatePosition(descriptor, delta) {
  return [descriptor.position[0] + delta[0], descriptor.position[1] + delta[1]];
}

function validBulkDelta(delta) {
  const [width, height] = state.data.size;
  const inBounds = (position) => position[0] >= 0 && position[1] >= 0 && position[0] < width && position[1] < height;
  const movedObjects = new Map();
  for (const descriptor of state.pointerDrag.descriptors) {
    const position = candidatePosition(descriptor, delta);
    if (descriptor.kind === "object") {
      const instance = state.data.objects.find((record) => record.id === descriptor.id);
      const definition = objectDefinition(instance);
      if (!objectIntersectsMap(definition, position)) return false;
      movedObjects.set(descriptor.id, position);
    } else if (descriptor.kind === "actor") {
      const actor = state.data.actors.find((record) => record.id === descriptor.id);
      if (!actor || !actorIntersectsMap(actor, position)) return false;
    } else if (!inBounds(position)) return false;
    if (descriptor.kind === "site") {
      const site = state.data.sites.find((record) => record.id === descriptor.id);
      if (site && site.entrance_offsets.some((offset) => !inBounds(addPoint(position, offset)))) return false;
    } else if (descriptor.kind === "trigger") {
      const trigger = state.data.event_triggers.find((record) => record.id === descriptor.id);
      if (trigger && trigger.offsets.some((offset) => !inBounds(addPoint(position, offset)))) return false;
    }
  }
  const placements = new Set();
  for (const instance of state.data.objects) {
    const origin = movedObjects.get(instance.id) || instance.origin;
    const key = objectPlacementSignature(objectDefinition(instance), origin);
    if (key === null) continue;
    if (placements.has(key)) return false;
    placements.add(key);
  }
  for (const site of state.data.sites) {
    if (site.anchor?.kind !== "object" || !movedObjects.has(site.anchor.object_id)) continue;
    const origin = movedObjects.get(site.anchor.object_id);
    if (site.entrance_offsets.some((offset) => !inBounds(addPoint(origin, offset)))) return false;
  }
  for (const trigger of state.data.event_triggers) {
    let origin = null;
    if (trigger.anchor?.kind === "object") origin = movedObjects.get(trigger.anchor.object_id) || null;
    if (origin && trigger.offsets.some((offset) => !inBounds(addPoint(origin, offset)))) return false;
  }
  return true;
}

function dragBulkTo(cell) {
  if (!state.pointerDrag || !["bulk", "single_selection"].includes(state.pointerDrag.kind)) return;
  const delta = [cell[0] - state.pointerDrag.start[0], cell[1] - state.pointerDrag.start[1]];
  if (delta[0] === state.pointerDrag.delta[0] && delta[1] === state.pointerDrag.delta[1]) return;
  if (!validBulkDelta(delta)) return;
  for (const descriptor of state.pointerDrag.descriptors) {
    const position = candidatePosition(descriptor, delta);
    if (descriptor.kind === "object") state.data.objects.find((record) => record.id === descriptor.id).origin = position;
    else if (descriptor.kind === "site") state.data.sites.find((record) => record.id === descriptor.id).anchor.position = position;
    else if (descriptor.kind === "arrival") state.data.arrival_points.find((record) => record.id === descriptor.id).position = position;
    else if (descriptor.kind === "actor") state.data.actors.find((record) => record.id === descriptor.id).position = position;
    else state.data.event_triggers.find((record) => record.id === descriptor.id).anchor.position = position;
  }
  if (state.pointerDrag.originalRect) {
    const rect = state.pointerDrag.originalRect;
    state.selectionRect = {
      left: rect.left + delta[0], top: rect.top + delta[1],
      right: rect.right + delta[0], bottom: rect.bottom + delta[1],
    };
  }
  state.pointerDrag.delta = delta;
  state.pointerDrag.changed = delta[0] !== 0 || delta[1] !== 0;
  state.dirty = true;
  renderInspector();
  drawMap(performance.now());
  updateSaveState();
  scheduleResolution(0);
}

function deleteBulkSelection() {
  if (!state.bulkSelection.length) return;
  commit(() => {
    const objectIds = new Set(state.bulkSelection.filter((item) => item.kind === "object").map((item) => item.id));
    const siteIds = new Set(state.bulkSelection.filter((item) => item.kind === "site").map((item) => item.id));
    const arrivalIds = new Set(state.bulkSelection.filter((item) => item.kind === "arrival").map((item) => item.id));
    const actorIds = new Set(state.bulkSelection.filter((item) => item.kind === "actor").map((item) => item.id));
    const triggerIds = new Set(state.bulkSelection.filter((item) => item.kind === "trigger").map((item) => item.id));
    const removedSiteIds = new Set(siteIds);
    state.data.objects = state.data.objects.filter((instance) => !objectIds.has(instance.id));
    state.data.sites = state.data.sites.filter((site) => {
      const remove = siteIds.has(site.id) || (site.anchor?.kind === "object" && objectIds.has(site.anchor.object_id));
      if (remove) {
        removedSiteIds.add(site.id);
        delete state.siteNamesJa[site.id];
      }
      return !remove;
    });
    state.siteOptions = state.siteOptions.filter((siteId) => !removedSiteIds.has(siteId));
    state.data.arrival_points = state.data.arrival_points.filter((arrival) => !arrivalIds.has(arrival.id));
    state.data.actors = state.data.actors.filter((actor) => !actorIds.has(actor.id));
    state.data.event_triggers = state.data.event_triggers.filter((trigger) => !triggerIds.has(trigger.id)
      && !(trigger.anchor?.kind === "object" && objectIds.has(trigger.anchor.object_id))
      && !(trigger.anchor?.kind === "actor" && actorIds.has(trigger.anchor.actor_id)));
    clearSingleSelections();
    state.bulkSelection = [];
    state.selectionRect = null;
  });
}

function rightClickWithEscape(event) {
  if (event.key !== "Escape") return false;
  event.preventDefault();
  if (event.repeat || state.pointerDrag || state.pointerStroke || document.querySelector("dialog[open]")) return true;
  const cell = state.hoveredCell;
  if (cell && !state.bulkSelection.some((item) => bulkItemOccupiesCell(item, cell))) selectAnyAt(cell);
  return true;
}

function paintGround(x, y) {
  if (state.data.grounds[y][x] === state.groundId) return false;
  state.data.grounds[y][x] = state.groundId;
  return true;
}

function paintGroundRectangle(rect) {
  let changed = false;
  for (let y = rect.top; y <= rect.bottom; y += 1) {
    for (let x = rect.left; x <= rect.right; x += 1) changed = paintGround(x, y) || changed;
  }
  return changed;
}

function beginGroundRectangle(event, cell) {
  beginChange();
  state.pointerDrag = { kind: "ground_rectangle", changed: false, pointerId: event.pointerId, start: [...cell], last: [...cell] };
  state.groundPaintRect = normalizedCellRect(cell, cell);
  mapCanvas.setPointerCapture(event.pointerId);
  drawMap(performance.now());
}

function updateGroundRectangle(cell) {
  if (state.pointerDrag?.kind !== "ground_rectangle") return;
  if (cell[0] === state.pointerDrag.last[0] && cell[1] === state.pointerDrag.last[1]) return;
  state.pointerDrag.last = [...cell];
  state.pointerDrag.changed = true;
  state.groundPaintRect = normalizedCellRect(state.pointerDrag.start, cell);
  drawMap(performance.now());
}

function finishGroundRectangle(event) {
  const rect = state.groundPaintRect;
  const changed = Boolean(rect && paintGroundRectangle(rect));
  if (!changed) state.history.pop();
  else {
    state.dirty = true;
    scheduleResolution(0);
  }
  state.pointerDrag = null;
  state.groundPaintRect = null;
  if (mapCanvas.hasPointerCapture(event.pointerId)) mapCanvas.releasePointerCapture(event.pointerId);
  renderAll();
}

function uniqueInstanceId(definitionId) {
  const used = new Set(state.data.objects.map((instance) => instance.id));
  let suffix = 1;
  while (used.has(`${definitionId}_${suffix}`)) suffix += 1;
  return `${definitionId}_${suffix}`;
}

function uniqueRecordId(base, records) {
  const used = new Set(records.map((record) => record.id));
  if (!used.has(base)) return base;
  let suffix = 2;
  while (used.has(`${base}_${suffix}`)) suffix += 1;
  return `${base}_${suffix}`;
}

function uniqueSiteId(base) {
  const records = state.data.profile === "world"
    ? [...state.data.sites, ...state.siteOptions.map((id) => ({ id }))]
    : state.data.sites;
  return uniqueRecordId(base, records);
}

function defaultSiteNameJa() {
  const used = new Set(Object.values(state.siteNamesJa).filter((value) => typeof value === "string"));
  let suffix = 1;
  while (used.has(`拠点${suffix}`)) suffix += 1;
  return `拠点${suffix}`;
}

function defaultSite(siteId, anchor, entranceOffsets) {
  return {
    id: siteId,
    anchor,
    entrance_offsets: entranceOffsets,
    destination: {
      map_id: "",
      arrival_id: "",
    },
  };
}

function attachSiteToObject() {
  if (state.data.profile !== "world") return;
  const instance = currentInstance();
  const definition = objectDefinition(instance);
  if (!instance || !definition || siteForObject(instance.id)) return;
  const siteId = uniqueSiteId(instance.id);
  const offsets = definition.cells.length
    ? [...new Map(definition.cells.map((cell) => [cell.offset.join(","), [...cell.offset]])).values()]
    : [[0, 0]];
  commit(() => {
    state.data.sites.push(defaultSite(siteId, { kind: "object", object_id: instance.id }, offsets));
    if (state.data.profile === "world") state.siteNamesJa[siteId] = defaultSiteNameJa();
    state.selectedSiteId = siteId;
    state.selectedArrivalId = null;
    state.tab = "site";
    state.travelTool = "select";
  });
}

function createCellSite(position) {
  const siteId = uniqueSiteId("site_1");
  commit(() => {
    state.data.sites.push(defaultSite(siteId, { kind: "cell", position: [...position] }, [[0, 0]]));
    if (state.data.profile === "world") state.siteNamesJa[siteId] = defaultSiteNameJa();
    state.selectedSiteId = siteId;
    state.selectedArrivalId = null;
    state.travelTool = "select";
  });
}

function createArrivalPoint(position) {
  const arrivalId = uniqueRecordId("arrival_1", state.data.arrival_points);
  commit(() => {
    state.data.arrival_points.push({ id: arrivalId, position: [...position], facing: "down", teleport_enabled: false, site_id: null });
    state.selectedArrivalId = arrivalId;
    state.selectedSiteId = null;
    state.travelTool = "select";
  });
}

function siteOffsetForCell(site, cell) {
  const origin = siteAnchorPosition(site);
  return origin ? [cell[0] - origin[0], cell[1] - origin[1]] : null;
}

function selectTravelAt(cell) {
  const selectedSite = state.data.sites.find((site) => {
    const origin = siteAnchorPosition(site);
    return siteEntrancePositions(site).some((entrance) => entrance[0] === cell[0] && entrance[1] === cell[1])
      || (site.anchor?.kind === "cell" && origin?.[0] === cell[0] && origin?.[1] === cell[1]);
  });
  const selectedArrival = state.data.arrival_points.find((arrival) => arrival.position[0] === cell[0] && arrival.position[1] === cell[1]);
  state.selectedSiteId = selectedSite?.id || null;
  state.selectedArrivalId = selectedSite ? null : selectedArrival?.id || null;
  renderAll();
}

function handleTravelCell(cell) {
  const site = currentSite();
  const arrival = currentArrival();
  if (state.travelTool === "create_site") {
    createCellSite(cell);
    return;
  }
  if (state.travelTool === "create_arrival") {
    createArrivalPoint(cell);
    return;
  }
  if (state.travelTool === "entrance" && site) {
    const offset = siteOffsetForCell(site, cell);
    if (!offset) return;
    commit(() => {
      const index = site.entrance_offsets.findIndex((item) => item[0] === offset[0] && item[1] === offset[1]);
      if (index >= 0 && site.entrance_offsets.length > 1) site.entrance_offsets.splice(index, 1);
      else if (index < 0) site.entrance_offsets.push(offset);
    });
    return;
  }
  selectTravelAt(cell);
}

function defaultTrigger(anchor) {
  return {
    id: uniqueRecordId("event_1", state.data.event_triggers),
    event_id: state.eventOptions[0] || "",
    activations: anchor.kind === "actor" ? ["touch", "interact"] : ["step"],
    anchor,
    offsets: [[0, 0]],
  };
}

function createActor(position) {
  const id = uniqueRecordId("actor_1", state.data.actors);
  commit(() => {
    const actor = { id, position: [...position], kind: "stationary", sprite_index: 0, sprite_source: "npc", facing: "down", floating: false };
    state.data.actors.push(actor);
    ensureActorTrigger(actor);
    state.selectedActorId = id;
    state.selectedTriggerId = null;
    state.eventTool = "select";
  });
}

function addAnchoredTrigger(anchor) {
  commit(() => {
    const trigger = defaultTrigger(anchor);
    state.data.event_triggers.push(trigger);
    state.selectedTriggerId = trigger.id;
    state.eventTool = "select";
  });
}

function ensureActorTrigger(actor) {
  if (actor.kind === "treasure") return null;
  let trigger = actorTrigger(actor.id);
  if (trigger) return trigger;
  trigger = defaultTrigger({ kind: "actor", actor_id: actor.id });
  state.data.event_triggers.push(trigger);
  return trigger;
}

function triggerOffsetForCell(trigger, cell) {
  const origin = triggerAnchorPosition(trigger);
  return origin ? [cell[0] - origin[0], cell[1] - origin[1]] : null;
}

function selectEventAt(cell) {
  const actor = state.data.actors.find((item) => item.position[0] === cell[0] && item.position[1] === cell[1]);
  const trigger = standaloneTriggers().find((item) => triggerPositions(item).some((position) => position[0] === cell[0] && position[1] === cell[1]));
  if (actor && actor.kind !== "treasure" && !actorTrigger(actor.id)) {
    commit(() => {
      ensureActorTrigger(actor);
      state.selectedActorId = actor.id;
      state.selectedTriggerId = null;
    });
    return;
  }
  state.selectedActorId = actor?.id || null;
  state.selectedTriggerId = trigger?.id || null;
  renderAll();
}

function mapSelectionCandidatesAt(cell) {
  const [x, y] = cell;
  const candidates = [];
  const objects = [...state.data.objects]
    .filter((instance) => instanceOccupies(instance, x, y))
    .sort((left, right) => compareObjectsBackToFront(right, left));
  if (state.tab === "object") {
    return state.objectLayer === "all" ? [] : objects
      .filter((instance) => objectLayerEditable(objectDefinition(instance)))
      .map((instance) => ({ kind: "object", id: instance.id, tab: "object" }));
  }
  for (const actor of state.data.actors) {
    if (actorOccupiesCell(actor, cell)) candidates.push({ kind: "actor", id: actor.id, tab: "event" });
  }
  for (const trigger of standaloneTriggers()) {
    if (triggerPositions(trigger).some((position) => position[0] === x && position[1] === y)) candidates.push({ kind: "trigger", id: trigger.id, tab: "event" });
  }
  for (const arrival of state.data.arrival_points) {
    if (arrival.position[0] === x && arrival.position[1] === y) candidates.push({ kind: "arrival", id: arrival.id, tab: "site" });
  }
  for (const site of state.data.sites) {
    const origin = siteAnchorPosition(site);
    const occupiesCell = siteEntrancePositions(site).some((position) => position[0] === x && position[1] === y)
      || (site.anchor?.kind === "cell" && origin?.[0] === x && origin?.[1] === y);
    if (occupiesCell) candidates.push({ kind: "site", id: site.id, tab: "site" });
  }
  for (const instance of objects) candidates.push({ kind: "object", id: instance.id, tab: "object" });
  return candidates;
}

function prioritizeMapSelectionCandidates(candidates) {
  const preferred = candidates.filter((candidate) => candidate.tab === state.tab);
  if (!preferred.length || preferred.length === candidates.length) return candidates;
  return [...preferred, ...candidates.filter((candidate) => candidate.tab !== state.tab)];
}

function isMapSelectionCandidateSelected(candidate) {
  if (candidate.tab !== state.tab) return false;
  if (candidate.kind === "actor") return candidate.id === state.selectedActorId;
  if (candidate.kind === "trigger") return candidate.id === state.selectedTriggerId;
  if (candidate.kind === "arrival") return candidate.id === state.selectedArrivalId;
  if (candidate.kind === "site") return candidate.id === state.selectedSiteId;
  return candidate.id === state.selectedInstanceId;
}

function selectAnyAt(cell) {
  const candidates = prioritizeMapSelectionCandidates(mapSelectionCandidatesAt(cell));
  const selectedIndex = candidates.findIndex(isMapSelectionCandidateSelected);
  const candidate = candidates.length ? candidates[(selectedIndex + 1) % candidates.length] : null;
  clearSingleSelections();
  clearBulkSelection();
  state.travelTool = "select";
  state.eventTool = "select";
  if (!candidate) {
    renderAll();
    return null;
  }
  state.tab = candidate.tab;
  if (candidate.kind === "actor") state.selectedActorId = candidate.id;
  else if (candidate.kind === "trigger") state.selectedTriggerId = candidate.id;
  else if (candidate.kind === "arrival") state.selectedArrivalId = candidate.id;
  else if (candidate.kind === "site") state.selectedSiteId = candidate.id;
  else {
    const instance = state.data.objects.find((item) => item.id === candidate.id);
    state.selectedInstanceId = candidate.id;
    if (instance) {
      state.objectLayer = objectDefinition(instance)?.default_draw_group || "object_y_sorted";
      state.objectId = instance.definition_id;
    }
  }
  const actor = candidate.kind === "actor" ? currentActor() : null;
  if (actor && actor.kind !== "treasure" && !actorTrigger(actor.id)) commit(() => ensureActorTrigger(actor));
  else renderAll();
  return candidate;
}

function toggleTriggerOffset(cell) {
  const offset = triggerOffsetForCell(currentTrigger(), cell);
  if (!offset) return;
  commit(() => {
    const trigger = currentTrigger();
    const index = trigger.offsets.findIndex((item) => item[0] === offset[0] && item[1] === offset[1]);
    if (index >= 0 && trigger.offsets.length > 1) trigger.offsets.splice(index, 1);
    else if (index < 0) trigger.offsets.push(offset);
  });
}

function handleEventCell(cell) {
  if (state.eventTool === "create_actor") return createActor(cell);
  if (state.eventTool === "create_trigger") return addAnchoredTrigger({ kind: "cell", position: [...cell] });
  if (state.eventTool === "create_object_trigger") {
    const instance = instanceAt(...cell);
    if (!instance) {
      showToast("トリガーを設定するオブジェクトを選択してください。", true);
      return;
    }
    return addAnchoredTrigger({ kind: "object", object_id: instance.id });
  }
  selectEventAt(cell);
}

function placeObject(x, y) {
  const definition = state.tileset.objects.find((object) => object.id === state.objectId);
  if (state.objectLayer === "all" || !objectLayerEditable(definition)) return;
  if (!objectIntersectsMap(definition, [x, y])) {
    showToast("オブジェクトの構成セルがすべてマップ範囲外です。", true);
    return;
  }
  const conflict = objectPlacementConflict(definition, [x, y]);
  if (conflict) {
    state.selectedInstanceId = conflict.id;
    state.objectId = conflict.definition_id;
    renderAll();
    showToast("同じレイヤーで構成セルが完全に重なるため、既存の配置を選択しました。", true);
    return;
  }
  commit(() => {
    clearBulkSelection();
    const order = state.data.objects.length ? Math.max(...state.data.objects.map((instance) => instance.order)) + 1 : 0;
    const instance = { id: uniqueInstanceId(definition.id), definition_id: definition.id, origin: [x, y], order };
    state.data.objects.push(instance);
    state.selectedInstanceId = instance.id;
  });
}

function objectDefinition(instance) {
  return state.tileset.objects.find((object) => object.id === instance?.definition_id) || null;
}

function objectIntersectsMap(definition, origin) {
  const [width, height] = state.data.size;
  return Boolean(definition?.cells.some((cell) => {
    const [x, y] = addPoint(origin, cell.offset);
    return x >= 0 && x < width && y >= 0 && y < height;
  }));
}

function objectLayerEditable(definition) {
  return Boolean(definition && (state.objectLayer === "all" || definition.default_draw_group === state.objectLayer));
}

function objectPlacementSignature(definition, origin) {
  if (!definition?.cells?.length) return null;
  const positions = new Set(definition.cells.map((cell) => addPoint(origin, cell.offset).join(",")));
  return `${definition.default_draw_group}:${JSON.stringify([...positions].sort())}`;
}

function objectPlacementConflict(definition, origin, excludedId = null) {
  const signature = objectPlacementSignature(definition, origin);
  return state.data.objects.find((instance) => instance.id !== excludedId
    && signature !== null && objectPlacementSignature(objectDefinition(instance), instance.origin) === signature) || null;
}

function objectBottom(instance) {
  const definition = objectDefinition(instance);
  return definition ? instance.origin[1] + definition.size[1] - 1 : instance.origin[1];
}

function objectDrawGroupOrder(instance) {
  const drawGroup = objectDefinition(instance)?.default_draw_group;
  return { object: 0, object_y_sorted: 1, object_foreground: 2, object_overlay: 3 }[drawGroup] ?? 1;
}

function objectDrawGroupLabel(definition) {
  return {
    object: "背面",
    object_y_sorted: "通常",
    object_foreground: "前面",
    object_overlay: "最前面",
  }[definition?.default_draw_group] || "通常";
}

function compareObjectsBackToFront(left, right) {
  const leftLayer = objectDrawGroupOrder(left);
  const rightLayer = objectDrawGroupOrder(right);
  const depthBand = (layer) => layer === 2 ? 1 : layer;
  return depthBand(leftLayer) - depthBand(rightLayer)
    || objectBottom(left) - objectBottom(right)
    || leftLayer - rightLayer
    || left.order - right.order
    || left.origin[0] - right.origin[0]
    || left.id.localeCompare(right.id);
}

function instanceOccupies(instance, x, y) {
  const definition = objectDefinition(instance);
  return Boolean(definition?.cells.some((cell) => instance.origin[0] + cell.offset[0] === x && instance.origin[1] + cell.offset[1] === y));
}

function instanceAt(x, y) {
  if (state.tab === "object" && state.objectLayer === "all") return null;
  return [...state.data.objects]
    .filter((instance) => state.tab !== "object" || objectLayerEditable(objectDefinition(instance)))
    .sort((left, right) => compareObjectsBackToFront(right, left))
    .find((instance) => instanceOccupies(instance, x, y)) || null;
}

function validObjectOrigin(instance, x, y) {
  const definition = objectDefinition(instance);
  if (!objectIntersectsMap(definition, [x, y])) return false;
  return !objectPlacementConflict(definition, [x, y], instance.id);
}

function beginObjectDrag(event, cell) {
  const instance = currentInstance();
  if (state.objectLayer === "all" || !instance || !objectLayerEditable(objectDefinition(instance)) || !instanceOccupies(instance, ...cell)) return false;
  beginChange();
  state.pointerDrag = {
    kind: "object",
    changed: false,
    pointerId: event.pointerId,
    grabOffset: [cell[0] - instance.origin[0], cell[1] - instance.origin[1]],
    lastOrigin: [...instance.origin],
  };
  mapCanvas.setPointerCapture(event.pointerId);
  return true;
}

function dragObjectTo(cell) {
  const instance = currentInstance();
  if (!instance || state.pointerDrag?.kind !== "object") return;
  const origin = [cell[0] - state.pointerDrag.grabOffset[0], cell[1] - state.pointerDrag.grabOffset[1]];
  if (origin[0] === state.pointerDrag.lastOrigin[0] && origin[1] === state.pointerDrag.lastOrigin[1]) return;
  if (!validObjectOrigin(instance, ...origin)) return;
  instance.origin = origin;
  state.pointerDrag.lastOrigin = [...origin];
  state.pointerDrag.changed = true;
  state.dirty = true;
  renderInspector();
  updateSaveState();
  scheduleResolution(0);
}

function beginSiteAnchorDrag(event, cell) {
  if (state.travelTool !== "select") return false;
  const site = state.data.sites.find((item) => item.anchor?.kind === "cell"
    && item.anchor.position[0] === cell[0]
    && item.anchor.position[1] === cell[1]);
  if (!site) return false;
  state.selectedSiteId = site.id;
  state.selectedArrivalId = null;
  beginChange();
  state.pointerDrag = {
    kind: "site_anchor",
    changed: false,
    pointerId: event.pointerId,
    lastPosition: [...site.anchor.position],
  };
  mapCanvas.setPointerCapture(event.pointerId);
  renderAll();
  return true;
}

function dragSiteAnchorTo(cell) {
  const site = currentSite();
  if (site?.anchor?.kind !== "cell" || state.pointerDrag?.kind !== "site_anchor") return;
  if (cell[0] === state.pointerDrag.lastPosition[0] && cell[1] === state.pointerDrag.lastPosition[1]) return;
  site.anchor.position = [...cell];
  state.pointerDrag.lastPosition = [...cell];
  state.pointerDrag.changed = true;
  state.dirty = true;
  renderInspector();
  drawMap(performance.now());
  updateSaveState();
  scheduleResolution(0);
}

function handlePaletteAction(element) {
  const action = element.dataset.action;
  if (action === "select-object-definition" && (state.objectLayer === "all"
    || !objectLayerEditable(state.tileset.objects.find((object) => object.id === element.dataset.id)))) return;
  clearBulkSelection();
  if (action === "select-object-layer") {
    if (!OBJECT_LAYERS.some(([layer]) => layer === element.dataset.layer)) return;
    state.objectLayer = element.dataset.layer;
    clearSingleSelections();
    state.hoveredCell = null;
    renderAll();
  } else if (action === "select-ground") {
    state.groundId = element.dataset.id;
    renderPalette();
  } else if (action === "select-ground-tool") {
    state.groundTool = element.dataset.tool;
    state.groundPaintRect = null;
    renderPalette();
    drawMap(performance.now());
  } else if (action === "select-object-definition") {
    state.objectId = element.dataset.id;
    state.selectedInstanceId = null;
    renderPalette();
    renderInspector();
    drawMap(performance.now());
  } else if (action === "select-site") {
    state.selectedSiteId = element.dataset.id;
    state.selectedArrivalId = null;
    state.travelTool = "select";
    renderAll();
    centerMapOnPosition(siteFocusPosition(currentSite()));
  } else if (action === "select-arrival") {
    state.selectedArrivalId = element.dataset.id;
    state.selectedSiteId = null;
    state.travelTool = "select";
    renderAll();
    centerMapOnPosition(currentArrival()?.position);
  } else if (action === "prepare-cell-site") {
    state.selectedSiteId = null;
    state.selectedArrivalId = null;
    state.travelTool = "create_site";
    renderAll();
  } else if (action === "prepare-arrival") {
    state.selectedSiteId = null;
    state.selectedArrivalId = null;
    state.travelTool = "create_arrival";
    renderAll();
  } else if (action === "select-actor") {
    state.selectedActorId = element.dataset.id;
    state.selectedTriggerId = null;
    state.eventTool = "select";
    if (currentActor() && currentActor().kind !== "treasure" && !actorTrigger(currentActor().id)) {
      commit(() => { ensureActorTrigger(currentActor()); });
      centerMapOnPosition(currentActor()?.position);
      return;
    }
    renderAll();
    centerMapOnPosition(currentActor()?.position);
  } else if (action === "select-trigger") {
    state.selectedTriggerId = element.dataset.id;
    state.eventTool = "select";
    renderAll();
    centerMapOnPosition(triggerAnchorPosition(currentTrigger()));
  } else if (action === "prepare-actor") {
    state.selectedActorId = null;
    state.eventTool = "create_actor";
    renderAll();
  } else if (action === "prepare-cell-trigger") {
    state.selectedTriggerId = null;
    state.eventTool = "create_trigger";
    renderAll();
  } else if (action === "prepare-object-trigger") {
    state.selectedTriggerId = null;
    state.eventTool = "create_object_trigger";
    renderAll();
  }
}

function removeOutsideMapPlacements() {
  const [width, height] = state.data.size;
  const inBounds = (position) => position[0] >= 0 && position[0] < width
    && position[1] >= 0 && position[1] < height;
  const removedObjectIds = new Set();
  state.data.objects = state.data.objects.filter((instance) => {
    const definition = objectDefinition(instance);
    // Keep unknown definitions for validation rather than guessing their extent.
    if (!definition?.cells?.length || objectIntersectsMap(definition, instance.origin)) return true;
    removedObjectIds.add(instance.id);
    return false;
  });
  const removedActorIds = new Set();
  state.data.actors = state.data.actors.filter((actor) => {
    if (actorIntersectsMap(actor)) return true;
    removedActorIds.add(actor.id);
    return false;
  });
  state.data.event_triggers = state.data.event_triggers.filter((trigger) => {
    if (trigger.anchor?.kind === "object" && removedObjectIds.has(trigger.anchor.object_id)) return false;
    if (trigger.anchor?.kind === "actor" && removedActorIds.has(trigger.anchor.actor_id)) return false;
    if (trigger.anchor?.kind === "actor") return true;
    const positions = triggerPositions(trigger);
    return !positions.length || positions.some(inBounds);
  });
  const removedSiteIds = new Set();
  state.data.sites = state.data.sites.filter((site) => {
    if (site.anchor?.kind !== "object" || !removedObjectIds.has(site.anchor.object_id)) return true;
    removedSiteIds.add(site.id);
    delete state.siteNamesJa[site.id];
    return false;
  });
  state.siteOptions = state.siteOptions.filter((siteId) => !removedSiteIds.has(siteId));
}

function resizeMap() {
  const width = Number(byId("map-width").value);
  const height = Number(byId("map-height").value);
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < MIN_MAP_WIDTH || height < MIN_MAP_HEIGHT || width > 512 || height > 512) {
    showToast(`幅は${MIN_MAP_WIDTH}〜512、高さは${MIN_MAP_HEIGHT}〜512の整数で指定してください。`, true);
    return;
  }
  if (width === state.data.size[0] && height === state.data.size[1]) return;
  const [previousWidth, previousHeight] = state.data.size;
  const offsetX = state.resizeHorizontal === "left" ? width - previousWidth : 0;
  const offsetY = state.resizeVertical === "up" ? height - previousHeight : 0;
  const rootGround = state.tileset.grounds[0].id;
  commit(() => {
    const previous = state.data.grounds;
    state.data.grounds = Array.from({ length: height }, (_unused, y) => Array.from({ length: width }, (_empty, x) => {
      const sourceX = x - offsetX;
      const sourceY = y - offsetY;
      return previous[sourceY]?.[sourceX] ?? rootGround;
    }));
    for (const instance of state.data.objects) {
      instance.origin[0] += offsetX;
      instance.origin[1] += offsetY;
    }
    for (const site of state.data.sites) {
      if (site.anchor?.kind !== "cell") continue;
      site.anchor.position[0] += offsetX;
      site.anchor.position[1] += offsetY;
    }
    for (const arrival of state.data.arrival_points) {
      arrival.position[0] += offsetX;
      arrival.position[1] += offsetY;
    }
    for (const actor of state.data.actors) {
      actor.position[0] += offsetX;
      actor.position[1] += offsetY;
    }
    for (const trigger of state.data.event_triggers) {
      if (trigger.anchor?.kind !== "cell") continue;
      trigger.anchor.position[0] += offsetX;
      trigger.anchor.position[1] += offsetY;
    }
    state.data.size = [width, height];
    removeOutsideMapPlacements();
  });
}

function openRandomEncounterDialog() {
  if (state.data?.profile !== "dungeon") return;
  const settings = state.data.random_encounter;
  byId("encounter-enabled").value = String(settings.enabled !== false);
  byId("encounter-monster-level").value = String(settings.monster_level);
  byId("encounter-danger").value = settings.danger;
  byId("encounter-polarity").value = settings.polarity;
  byId("encounter-allow-demons").checked = settings.allow_demons;
  byId("encounter-allow-humans").checked = settings.allow_humans;
  byId("encounter-allow-giants").checked = settings.allow_giants;
  byId("encounter-allow-large-animals").checked = settings.allow_large_animals;
  updateRandomEncounterControls();
  byId("random-encounter-dialog").showModal();
}

function updateRandomEncounterControls() {
  const disabled = byId("encounter-enabled").value === "false";
  for (const id of [
    "encounter-monster-level", "encounter-danger", "encounter-polarity",
    "encounter-allow-demons", "encounter-allow-humans", "encounter-allow-giants",
    "encounter-allow-large-animals",
  ]) byId(id).disabled = disabled;
}

function handleInspectorAction(element) {
  const action = element.dataset.action;
  if (state.tab === "object" && state.objectLayer === "all"
    && ["delete-instance", "attach-site", "open-attached-site"].includes(action)) return;
  if (action === "open-random-encounter-dialog") openRandomEncounterDialog();
  else if (action === "resize-map") resizeMap();
  else if (action === "reroll") commit(() => { state.data.visual_seed += 1; });
  else if (action === "delete-bulk-selection") deleteBulkSelection();
  else if (action === "delete-instance") commit(() => {
    const objectId = state.selectedInstanceId;
    const index = state.data.objects.findIndex((instance) => instance.id === objectId);
    if (index >= 0) state.data.objects.splice(index, 1);
    const removedSiteIds = new Set();
    state.data.sites = state.data.sites.filter((site) => {
      const remove = site.anchor?.kind === "object" && site.anchor.object_id === objectId;
      if (remove) {
        removedSiteIds.add(site.id);
        delete state.siteNamesJa[site.id];
      }
      return !remove;
    });
    state.siteOptions = state.siteOptions.filter((siteId) => !removedSiteIds.has(siteId));
    state.data.event_triggers = state.data.event_triggers.filter((trigger) => !(trigger.anchor?.kind === "object" && trigger.anchor.object_id === objectId));
    state.selectedInstanceId = null;
  });
  else if (action === "attach-site") attachSiteToObject();
  else if (action === "open-attached-site") {
    state.selectedSiteId = siteForObject(currentInstance()?.id)?.id || null;
    state.selectedArrivalId = null;
    state.tab = "site";
    state.travelTool = "select";
    renderAll();
  }
  else if (action === "edit-site-entrances") {
    state.travelTool = "entrance";
    renderAll();
  }
  else if (action === "delete-site") commit(() => {
    const siteId = state.selectedSiteId;
    const index = state.data.sites.findIndex((site) => site.id === state.selectedSiteId);
    if (index >= 0) state.data.sites.splice(index, 1);
    delete state.siteNamesJa[siteId];
    state.siteOptions = state.siteOptions.filter((item) => item !== siteId);
    state.selectedSiteId = null;
    state.travelTool = "select";
  });
  else if (action === "delete-arrival") commit(() => {
    const index = state.data.arrival_points.findIndex((arrival) => arrival.id === state.selectedArrivalId);
    if (index >= 0) state.data.arrival_points.splice(index, 1);
    state.selectedArrivalId = null;
    state.travelTool = "select";
  });
  else if (action === "open-actor-sprite-dialog") openActorSpriteDialog();
  else if (action === "add-actor-event" && currentActor()) openNewActorEvent();
  else if (action === "open-actor-event" && currentActor()) {
    const trigger = actorTrigger(currentActor().id);
    if (!trigger?.event_id) return;
    const [namespace, eventId] = trigger.event_id.split(".", 2);
    const url = editorUrl("event", { namespace, event: eventId });
    navigateToEditor(url);
  }
  else if (action === "delete-actor") commit(() => {
    const actorId = state.selectedActorId;
    state.data.actors = state.data.actors.filter((actor) => actor.id !== actorId);
    state.data.event_triggers = state.data.event_triggers.filter((trigger) => !(trigger.anchor?.kind === "actor" && trigger.anchor.actor_id === actorId));
    state.selectedActorId = null;
    state.selectedTriggerId = null;
    state.eventTool = "select";
  });
  else if (action === "open-trigger-event" && currentTrigger()) {
    const [namespace, eventId] = currentTrigger().event_id.split(".", 2);
    const url = editorUrl("event", { namespace, event: eventId });
    navigateToEditor(url);
  }
  else if (action === "delete-trigger") commit(() => {
    state.data.event_triggers = state.data.event_triggers.filter((trigger) => trigger.id !== state.selectedTriggerId);
    state.selectedTriggerId = null;
    state.eventTool = "select";
  });
}

function updateObjectField(path, value) {
  const instance = currentInstance();
  if (!instance || state.objectLayer === "all" || !objectLayerEditable(objectDefinition(instance))) return;
  updateVisibilityField(instance, path, value);
}

function updateVisibilityField(instance, path, value) {
  if (path === "visibility_enabled") {
    if (value === "true" && !state.flagOptions.length) return;
    commit(() => {
      if (value === "true") instance.visibility_condition = { flag_id: state.flagOptions[0].flag_id, value: true };
      else delete instance.visibility_condition;
    });
  } else if (instance.visibility_condition && ["flag_id", "flag_value"].includes(path)) {
    commit(() => {
      if (path === "flag_id") instance.visibility_condition.flag_id = value;
      else if (path === "flag_value") instance.visibility_condition.value = value === "true";
    });
  }
}

function updateSiteField(path, value) {
  const site = currentSite();
  if (!site) return;
  commit(() => {
    if (path === "id") {
      const previousId = site.id;
      site.id = value;
      state.selectedSiteId = value;
      if (state.data.profile === "world") state.siteNamesJa[value] = state.siteNamesJa[previousId] || "";
      delete state.siteNamesJa[previousId];
      state.siteOptions = state.siteOptions.filter((item) => item !== previousId);
      for (const arrival of state.data.arrival_points) {
        if (arrival.site_id === previousId) arrival.site_id = value;
      }
    } else if (path === "destination.map_id") {
      site.destination.map_id = value;
      const arrivals = availableDestinations().find((option) => option.map_id === value)?.arrival_ids || [];
      if (!arrivals.includes(site.destination.arrival_id)) site.destination.arrival_id = arrivals[0] || "";
    }
    else if (path === "destination.arrival_id") site.destination.arrival_id = value;
  });
}

function updateSiteNameJaInput(value) {
  const site = currentSite();
  if (!site) return;
  if (!state.siteNameEditing) {
    beginChange();
    state.siteNameEditing = true;
  }
  state.siteNamesJa[site.id] = value;
  state.dirty = true;
  renderPalette();
  updateSaveState();
  scheduleResolution();
}

function updateArrivalField(path, value) {
  const arrival = currentArrival();
  if (!arrival) return;
  commit(() => {
    if (path === "id") {
      const previousId = arrival.id;
      const originalId = Object.keys(state.arrivalIdRenames).find((id) => state.arrivalIdRenames[id] === previousId)
        || (state.savedArrivalIds.has(previousId) ? previousId : null);
      if (originalId) {
        if (originalId === value) delete state.arrivalIdRenames[originalId];
        else state.arrivalIdRenames[originalId] = value;
      }
      arrival.id = value;
      state.selectedArrivalId = value;
      for (const site of state.data.sites) {
        const destination = site.destination;
        if (destination.map_id === state.data.map_id && destination.arrival_id === previousId) destination.arrival_id = value;
      }
    } else if (path === "facing") arrival.facing = value;
    else if (path === "teleport_enabled") {
      arrival.teleport_enabled = value;
      arrival.site_id = value ? (arrival.site_id || availableSiteIds()[0] || null) : null;
    } else if (path === "site_id") arrival.site_id = value || null;
  });
}

function updateActorField(path, value) {
  const actor = currentActor();
  if (!actor) return;
  if (["visibility_enabled", "flag_id", "flag_value"].includes(path)) {
    updateVisibilityField(actor, path, value);
    return;
  }
  commit(() => {
    if (path === "id") {
      const previousId = actor.id;
      actor.id = value;
      state.selectedActorId = value;
      for (const trigger of state.data.event_triggers) {
        if (trigger.anchor?.kind === "actor" && trigger.anchor.actor_id === previousId) trigger.anchor.actor_id = value;
      }
    } else if (path === "kind") {
      actor.kind = value;
      state.data.event_triggers = state.data.event_triggers.filter((trigger) => !(trigger.anchor?.kind === "actor" && trigger.anchor.actor_id === actor.id));
      if (value === "treasure") {
        delete actor.facing;
        delete actor.sprite_index;
        delete actor.sprite_source;
        delete actor.floating;
        actor.contents = { type: "gold", amount: 1 };
      } else {
        delete actor.contents;
        actor.sprite_index = 0;
        if (value === "prop") {
          delete actor.facing;
          delete actor.sprite_source;
          delete actor.floating;
        } else {
          actor.sprite_source = "npc";
          actor.facing = "down";
          actor.floating = false;
        }
        ensureActorTrigger(actor);
      }
    } else if (path === "sprite_index") actor.sprite_index = Number(value);
    else actor[path] = value;
  });
}

function updateTreasureField(path, value) {
  const actor = currentActor();
  if (!actor || actor.kind !== "treasure") return;
  commit(() => {
    if (path === "type") {
      actor.contents = value === "item"
        ? { type: "item", item_key: state.itemOptions[0]?.key || "" }
        : { type: "gold", amount: 1 };
    } else if (path === "amount") actor.contents.amount = Number(value);
    else if (path === "item_key") actor.contents.item_key = value;
  });
}

function updateActorEventId(value) {
  const actor = currentActor();
  if (!actor) return;
  commit(() => {
    const trigger = ensureActorTrigger(actor);
    if (trigger) trigger.event_id = value;
  });
}

function updateTriggerField(path, value) {
  const trigger = currentTrigger();
  if (!trigger || path !== "event_id") return;
  commit(() => {
    trigger.event_id = value;
  });
}

function applyValidationResult(result) {
  state.diagnostics = result.diagnostics;
  if (result.resolved) state.resolved = result.resolved;
}

function scheduleResolution(delay = 70) {
  window.clearTimeout(state.resolveTimer);
  const revision = ++state.resolveRevision;
  state.resolveTimer = window.setTimeout(async () => {
    try {
      const result = await api("/api/resolve", { method: "POST", body: JSON.stringify({ data: state.data, site_names_ja: state.siteNamesJa, arrival_id_renames: state.arrivalIdRenames }) });
      if (revision !== state.resolveRevision) return;
      applyValidationResult(result);
      renderIssues();
      drawMap(performance.now());
    } catch (error) {
      if (revision === state.resolveRevision) showToast(error.message, true);
    }
  }, delay);
}

async function save() {
  if (!canSave()) return false;
  updateSaveState("dirty", "保存・生成中…");
  try {
    const result = await api("/api/save", { method: "POST", body: JSON.stringify({ data: state.data, site_names_ja: state.siteNamesJa, arrival_id_renames: state.arrivalIdRenames }) });
    applyValidationResult(result);
    if (result.saved) {
      state.data = result.data || state.data;
      state.savedArrivalIds = new Set(state.data.arrival_points.map((arrival) => arrival.id));
      state.arrivalIdRenames = {};
      state.dirty = false;
      state.history = [];
      state.future = [];
      const existing = state.mapCatalog.find((item) => item.map_id === state.data.map_id);
      const record = {
        map_id: state.data.map_id,
        profile: state.data.profile,
        tileset_id: state.data.tileset_id,
        size: state.data.size,
        area_parent_id: state.data.area_parent_id,
        area_name: state.data.area_name,
      };
      if (existing) Object.assign(existing, record, { is_new: false });
      else state.mapCatalog.push(record);
      if (!state.data.area_parent_id) for (const item of state.mapCatalog) {
        if (item.area_parent_id === state.data.map_id) item.tileset_id = state.data.tileset_id;
      }
      saveLastMapId();
      showToast("制作用マップを保存し、ゲーム用データを生成しました。");
    } else {
      showToast("エラーを修正してから保存してください。", true);
    }
    renderMapSelector();
    renderAll();
    return Boolean(result.saved);
  } catch (error) {
    updateSaveState("error", "保存失敗");
    showToast(error.message, true);
    return false;
  }
}

async function initialize() {
  if (!token) {
    showToast("起動URLの認証トークンがありません。", true);
    updateSaveState("error", "接続不可");
    return;
  }
  try {
    const requestedMap = new URLSearchParams(window.location.search).get("map");
    const catalog = await api("/api/catalog");
    const storedMap = loadLastMapId();
    const storedMapExists = (catalog.maps || []).some((item) => item.map_id === storedMap);
    const initialMap = requestedMap || (storedMapExists ? storedMap : null);
    const payload = await api(initialMap ? `/api/document?map=${encodeURIComponent(initialMap)}` : "/api/document");
    state.mapCatalog = catalog.maps || [];
    state.tilesetCatalog = catalog.tilesets || [];
    applyDocumentPayload(payload);
  } catch (error) {
    showToast(error.message, true);
    updateSaveState("error", "読込失敗");
  }
}

byId("map-select").addEventListener("change", (event) => {
  requestMapSwitch(event.target.value);
});
byId("area-select").addEventListener("change", (event) => {
  requestMapSwitch(event.target.value);
});
byId("editor-switch").addEventListener("click", (event) => {
  const link = event.target.closest("a");
  if (!link || !state.dirty) return;
  event.preventDefault();
  navigateToEditor(link.href);
});
byId("unsaved-navigation-dialog").addEventListener("click", (event) => {
  const choice = event.target.closest("[data-navigation-choice]")?.dataset.navigationChoice;
  if (choice) handleNavigationChoice(choice);
});
byId("unsaved-navigation-dialog").addEventListener("close", () => {
  pendingEditorNavigationUrl = null;
  pendingMapNavigationId = null;
});
byId("new-map-button").addEventListener("click", () => {
  if (state.dirty && !window.confirm("未保存の変更を破棄して新規マップを作成しますか？")) return;
  byId("new-map-id").value = "";
  renderNewMapTilesets();
  byId("new-map-dialog").showModal();
});
byId("new-map-profile").addEventListener("change", renderNewMapTilesets);
byId("new-map-tileset").addEventListener("change", renderNewMapTilesets);
byId("new-map-dialog").addEventListener("click", (event) => {
  if (event.target === event.currentTarget || event.target.dataset.action === "close-new-map-dialog") byId("new-map-dialog").close();
});
byId("new-map-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const payload = await api("/api/create", {
      method: "POST",
      body: JSON.stringify({
        map_id: byId("new-map-id").value.trim(),
        profile: byId("new-map-profile").value,
        tileset_id: byId("new-map-tileset").value,
        width: Number(byId("new-map-width").value),
        height: Number(byId("new-map-height").value),
      }),
    });
    byId("new-map-dialog").close();
    applyDocumentPayload(payload);
  } catch (error) {
    showToast(error.message, true);
  }
});
byId("new-area-button").addEventListener("click", () => {
  if (state.dirty && !window.confirm("未保存の変更を破棄して新規エリアを作成しますか？")) return;
  byId("new-area-name").value = "";
  byId("new-area-width").value = String(state.data.size[0]);
  byId("new-area-height").value = String(state.data.size[1]);
  byId("new-area-dialog").showModal();
});
byId("new-area-dialog").addEventListener("click", (event) => {
  if (event.target === event.currentTarget || event.target.dataset.action === "close-new-area-dialog") byId("new-area-dialog").close();
});
byId("new-area-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const payload = await api("/api/create-area", {
      method: "POST",
      body: JSON.stringify({
        parent_id: logicalMapId(),
        area_name: byId("new-area-name").value.trim(),
        width: Number(byId("new-area-width").value),
        height: Number(byId("new-area-height").value),
      }),
    });
    byId("new-area-dialog").close();
    applyDocumentPayload(payload);
  } catch (error) {
    showToast(error.message, true);
  }
});
byId("change-map-tileset-button").addEventListener("click", () => {
  if (state.dirty) {
    showToast("先に現在の変更を保存してください。", true);
    return;
  }
  renderChangeMapTilesets();
  byId("change-map-tileset-dialog").showModal();
});
byId("change-map-tileset-select").addEventListener("change", renderChangeMapTilesets);
byId("change-map-tileset-dialog").addEventListener("click", (event) => {
  if (event.target === event.currentTarget || event.target.dataset.action === "close-change-map-tileset-dialog") byId("change-map-tileset-dialog").close();
});
byId("change-map-tileset-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!window.confirm(`マップ ${state.data.map_id} の全エリアの配置をクリアしてマップチップを変更しますか？`)) return;
  try {
    const payload = await api("/api/change-tileset", {
      method: "POST",
      body: JSON.stringify({ map_id: state.data.map_id, tileset_id: byId("change-map-tileset-select").value }),
    });
    byId("change-map-tileset-dialog").close();
    applyDocumentPayload(payload);
    showToast("マップを初期化しました。保存すると変更が確定します。");
  } catch (error) {
    showToast(error.message, true);
  }
});
byId("encounter-enabled").addEventListener("change", updateRandomEncounterControls);
byId("random-encounter-dialog").addEventListener("click", (event) => {
  if (event.target === event.currentTarget || event.target.dataset.action === "close-random-encounter-dialog") byId("random-encounter-dialog").close();
});
byId("random-encounter-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const monsterLevelValue = byId("encounter-monster-level").value;
  const nextSettings = {
    enabled: byId("encounter-enabled").value === "true",
    monster_level: monsterLevelValue === "dynamic" ? "dynamic" : Number(monsterLevelValue),
    danger: byId("encounter-danger").value,
    polarity: byId("encounter-polarity").value,
    allow_demons: byId("encounter-allow-demons").checked,
    allow_humans: byId("encounter-allow-humans").checked,
    allow_giants: byId("encounter-allow-giants").checked,
    allow_large_animals: byId("encounter-allow-large-animals").checked,
  };
  byId("random-encounter-dialog").close();
  commit(() => { state.data.random_encounter = nextSettings; });
});
byId("delete-map-button").addEventListener("click", async () => {
  if (state.dirty) {
    showToast("未保存の変更があるため削除できません。", true);
    return;
  }
  if (!window.confirm(`マップ ${state.data.map_id} を削除しますか？この操作は元に戻せません。`)) return;
  try {
    const result = await api("/api/delete", { method: "POST", body: JSON.stringify({ map_id: state.data.map_id }) });
    state.mapCatalog = result.maps || [];
    if (result.next_map_id) await loadMapDocument(result.next_map_id);
    showToast(`マップ ${result.map_id} を削除しました。`);
  } catch (error) {
    showToast(error.message, true);
  }
});

document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => {
  state.tab = button.dataset.tab;
  state.travelTool = "select";
  state.eventTool = "select";
  renderAll();
}));
byId("palette-content").addEventListener("click", (event) => {
  const target = event.target.closest("[data-action]");
  if (target) handlePaletteAction(target);
});
byId("inspector-content").addEventListener("click", (event) => {
  const target = event.target.closest("[data-action]");
  if (target) handleInspectorAction(target);
});
byId("inspector-content").addEventListener("input", (event) => {
  if (event.target.dataset.siteNameJa) updateSiteNameJaInput(event.target.value);
});
byId("inspector-content").addEventListener("change", (event) => {
  if (event.target.id === "resize-horizontal") state.resizeHorizontal = event.target.value;
  else if (event.target.id === "resize-vertical") state.resizeVertical = event.target.value;
  else if (event.target.dataset.mapField === "bgm_id") commit(() => { state.data.bgm_id = event.target.value; });
  else if (event.target.dataset.mapField === "area_name") commit(() => {
    const name = event.target.value.trim();
    if (name || state.data.area_parent_id) state.data.area_name = name;
    else delete state.data.area_name;
  });
  else if (event.target.dataset.siteNameJa) {
    state.siteNameEditing = false;
    renderPalette();
  }
  else if (event.target.dataset.objectField) updateObjectField(event.target.dataset.objectField, event.target.value);
  else if (event.target.dataset.siteField) updateSiteField(event.target.dataset.siteField, event.target.value);
  else if (event.target.dataset.arrivalField) updateArrivalField(event.target.dataset.arrivalField, event.target.type === "checkbox" ? event.target.checked : event.target.value);
  else if (event.target.dataset.actorField) updateActorField(event.target.dataset.actorField, event.target.type === "checkbox" ? event.target.checked : event.target.value);
  else if (event.target.dataset.treasureField) updateTreasureField(event.target.dataset.treasureField, event.target.value);
  else if (event.target.dataset.actorEventId) updateActorEventId(event.target.value);
  else if (event.target.dataset.triggerField) updateTriggerField(event.target.dataset.triggerField, event.target.value);
  else if (event.target.dataset.triggerActivation) commit(() => {
    const trigger = currentTrigger();
    const activation = event.target.dataset.triggerActivation;
    if (event.target.checked && !trigger.activations.includes(activation)) trigger.activations.push(activation);
    else if (!event.target.checked) trigger.activations = trigger.activations.filter((item) => item !== activation);
  });
});
byId("actor-sprite-dialog").addEventListener("click", (event) => {
  if (event.target === event.currentTarget) closeActorSpriteDialog();
  const target = event.target.closest("[data-action]");
  if (!target) return;
  if (target.dataset.action === "close-actor-sprite-dialog") closeActorSpriteDialog();
  else if (target.dataset.action === "select-actor-sprite") selectActorSprite(target.dataset.assetId, Number(target.dataset.spriteIndex));
});
byId("actor-sprite-dialog").addEventListener("close", () => { state.spritePickerActorId = null; });
byId("undo-button").addEventListener("click", undo);
byId("redo-button").addEventListener("click", redo);
byId("save-button").addEventListener("click", save);
byId("zoom-in").addEventListener("click", () => { state.zoom = Math.min(4, state.zoom + 1); saveUiSettings(); renderAll(); });
byId("zoom-out").addEventListener("click", () => { state.zoom = Math.max(1, state.zoom - 1); saveUiSettings(); renderAll(); });
byId("grid-toggle").addEventListener("change", (event) => { state.showGrid = event.target.checked; saveUiSettings(); drawMap(performance.now()); });
byId("collision-toggle").addEventListener("change", (event) => { state.showCollision = event.target.checked; saveUiSettings(); drawMap(performance.now()); });
byId("ground-only-toggle").addEventListener("change", (event) => { state.showGroundOnly = event.target.checked; saveUiSettings(); drawMap(performance.now()); });
byId("animation-toggle").addEventListener("click", () => {
  state.paused = !state.paused;
  if (!state.paused) state.animationStartedAt = performance.now();
  renderAll();
});

const mapCanvas = byId("map-canvas");
mapCanvas.addEventListener("pointerdown", (event) => {
  if (state.pointerDrag || state.pointerStroke) return;
  const cell = mapCellFromPointer(event);
  if (!cell) return;
  rememberMapPointer(event);
  state.hoveredCell = [...cell];
  if (event.button === 2) {
    event.preventDefault();
    if (beginBulkDrag(event, cell)) return;
    beginRangeSelection(event, cell);
    return;
  }
  if (event.button !== 0) return;
  if (event.shiftKey && state.tab === "event" && currentTrigger()) {
    toggleTriggerOffset(cell);
    return;
  }
  if (beginBulkDrag(event, cell)) return;
  if (state.tab === "object" && state.objectLayer === "all") {
    beginRangeSelection(event, cell);
    return;
  }
  if (state.bulkSelection.length) clearBulkSelection();
  if (state.tab === "ground") {
    if (state.groundTool === "rectangle") {
      beginGroundRectangle(event, cell);
      return;
    }
    beginChange();
    state.pointerStroke = { changed: false, last: null, pointerId: event.pointerId };
    mapCanvas.setPointerCapture(event.pointerId);
    state.pointerStroke.changed = paintGround(...cell);
    state.pointerStroke.last = cell.join(",");
    if (state.pointerStroke.changed) { state.dirty = true; scheduleResolution(); updateSaveState(); }
  } else if (state.tab === "object") {
    if (!beginObjectDrag(event, cell)) placeObject(...cell);
  } else if (state.tab === "event") {
    const item = currentSingleSelectionItem();
    if (item?.kind === "actor" && bulkItemOccupiesCell(item, cell) && beginSingleSelectionDrag(event, cell, item)) return;
    handleEventCell(cell);
  }
  else if (!beginSiteAnchorDrag(event, cell)) handleTravelCell(cell);
});
mapCanvas.addEventListener("pointermove", updateMapPointer);
mapCanvas.addEventListener("pointerup", (event) => {
  const drag = state.pointerDrag || state.pointerStroke;
  if (drag && drag.pointerId !== event.pointerId) return;
  if (drag) updateMapPointer(event);
  stopMapAutoScroll();
  if (state.pointerDrag) {
    if (state.pointerDrag.kind === "ground_rectangle") {
      finishGroundRectangle(event);
      return;
    }
    if (state.pointerDrag.kind === "range_selection") {
      const drag = state.pointerDrag;
      state.pointerDrag = null;
      if (drag.changed) {
        state.bulkSelection = rangeSelectionItems(state.selectionRect);
        clearSingleSelections();
        if (!state.bulkSelection.length) state.selectionRect = null;
        showToast(state.bulkSelection.length ? `${state.bulkSelection.length}件を選択しました。` : "範囲内に配置要素はありません。");
      } else {
        state.selectionRect = null;
        selectAnyAt(drag.start);
      }
      if (mapCanvas.hasPointerCapture(event.pointerId)) mapCanvas.releasePointerCapture(event.pointerId);
      renderAll();
      return;
    }
    if (!state.pointerDrag.changed) state.history.pop();
    state.pointerDrag = null;
    if (mapCanvas.hasPointerCapture(event.pointerId)) mapCanvas.releasePointerCapture(event.pointerId);
    renderAll();
    scheduleResolution(0);
    return;
  }
  if (!state.pointerStroke) return;
  if (!state.pointerStroke.changed) state.history.pop();
  state.pointerStroke = null;
  if (mapCanvas.hasPointerCapture(event.pointerId)) mapCanvas.releasePointerCapture(event.pointerId);
  renderAll();
});
mapCanvas.addEventListener("pointercancel", cancelMapPointer);
mapCanvas.addEventListener("lostpointercapture", cancelMapPointer);
mapCanvas.addEventListener("contextmenu", (event) => event.preventDefault());
mapCanvas.addEventListener("pointerleave", () => {
  if (state.pointerDrag || state.pointerStroke) return;
  byId("cursor-status").textContent = "セル —";
  state.hoveredCell = null;
  drawMap(performance.now());
});
window.addEventListener("blur", cancelMapPointer);
document.addEventListener("visibilitychange", () => { if (document.hidden) cancelMapPointer(); });

window.addEventListener("keydown", (event) => {
  if (rightClickWithEscape(event)) return;
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") { event.preventDefault(); save(); }
  else if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") { event.preventDefault(); if (event.shiftKey) redo(); else undo(); }
  else if ((event.key === "Delete" || event.key === "Backspace") && state.bulkSelection.length && !["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName)) {
    event.preventDefault();
    deleteBulkSelection();
  }
  else if ((event.key === "Delete" || event.key === "Backspace") && state.tab === "object" && state.selectedInstanceId && event.target.tagName !== "INPUT") {
    event.preventDefault();
    handleInspectorAction({ dataset: { action: "delete-instance" } });
  } else if ((event.key === "Delete" || event.key === "Backspace") && state.tab === "site" && state.selectedSiteId && event.target.tagName !== "INPUT") {
    event.preventDefault();
    handleInspectorAction({ dataset: { action: "delete-site" } });
  } else if ((event.key === "Delete" || event.key === "Backspace") && state.tab === "site" && state.selectedArrivalId && event.target.tagName !== "INPUT") {
    event.preventDefault();
    handleInspectorAction({ dataset: { action: "delete-arrival" } });
  } else if ((event.key === "Delete" || event.key === "Backspace") && state.tab === "event" && state.selectedTriggerId && event.target.tagName !== "INPUT") {
    event.preventDefault();
    handleInspectorAction({ dataset: { action: "delete-trigger" } });
  } else if ((event.key === "Delete" || event.key === "Backspace") && state.tab === "event" && state.selectedActorId && event.target.tagName !== "INPUT") {
    event.preventDefault();
    handleInspectorAction({ dataset: { action: "delete-actor" } });
  }
});
document.addEventListener("cancel", (event) => event.preventDefault(), true);
window.addEventListener("beforeunload", (event) => {
  if (state.dirty) { event.preventDefault(); event.returnValue = ""; }
});

requestAnimationFrame(animationLoop);
configureEditorNavigation();
initialize();
