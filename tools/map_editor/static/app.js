"use strict";

const SESSION_CLIENT_HEADER = "map-editor-ui";
const CELL_SIZE = 16;
const MIN_MAP_WIDTH = 16;
const MIN_MAP_HEIGHT = 15;
let token = new URLSearchParams(window.location.search).get("token") || "";
const editorRoute = window.location.pathname.match(/^\/(tileset|map|event)(?:\/|$)/)?.[1] || null;

const state = {
  data: null,
  tileset: null,
  siteNamesJa: {},
  destinationOptions: [],
  siteOptions: [],
  eventOptions: [],
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
  groundTool: "brush",
  objectId: null,
  selectedInstanceId: null,
  selectedSiteId: null,
  selectedArrivalId: null,
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
  groundPaintRect: null,
  hoveredCell: null,
  resolveTimer: null,
  resolveRevision: 0,
  siteNameEditing: false,
  spritePickerActorId: null,
};

const rawImage = new Image();
const sourceImage = document.createElement("canvas");
const actorSheets = {
  prop: { image: new Image(), canvas: document.createElement("canvas"), ready: false },
  character: { image: new Image(), canvas: document.createElement("canvas"), ready: false },
};
const byId = (id) => document.getElementById(id);
const clone = (value) => JSON.parse(JSON.stringify(value));
const escapeHtml = (value) => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");

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
    });
  });
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
    };
    const index = records.findIndex((item) => item.map_id === state.data.map_id);
    if (index === -1) records.push({ ...current, is_new: true });
    else if (state.dirty) records[index] = { ...records[index], ...current, dirty: true };
  }
  records.sort((left, right) => left.map_id.localeCompare(right.map_id));
  select.innerHTML = records.map((item) => {
    const suffix = item.is_new ? "（未保存）" : `${item.profile} / ${item.tileset_id}${item.dirty ? "（未保存）" : ""}`;
    return `<option value="${escapeHtml(item.map_id)}" ${item.map_id === state.data?.map_id ? "selected" : ""}>${escapeHtml(item.map_id)} — ${escapeHtml(suffix)}</option>`;
  }).join("");
  select.disabled = records.length === 0;
  const persisted = state.data && state.mapCatalog.some((item) => item.map_id === state.data.map_id);
  const alternatives = state.tilesetCatalog.filter((item) => item.profile === state.data?.profile && item.tileset_id !== state.data?.tileset_id);
  byId("change-map-tileset-button").disabled = !persisted || alternatives.length === 0;
  byId("delete-map-button").disabled = !persisted || state.data?.map_id === "worldmap";
}

function applyDocumentPayload(payload) {
  window.clearTimeout(state.resolveTimer);
  state.resolveRevision += 1;
  state.data = payload.data;
  state.tileset = payload.tileset;
  state.siteNamesJa = payload.site_names_ja;
  state.destinationOptions = payload.destination_options;
  state.siteOptions = payload.site_options;
  state.eventOptions = payload.event_options;
  state.bgmOptions = payload.bgm_options || [];
  state.actorAssets = payload.actor_assets || {};
  state.resolved = payload.resolved;
  state.diagnostics = payload.diagnostics;
  state.dirty = Boolean(payload.is_new || payload.dirty);
  state.history = [];
  state.future = [];
  state.groundId = state.tileset.grounds[0]?.id || null;
  state.objectId = state.tileset.objects[0]?.id || null;
  state.selectedInstanceId = null;
  state.selectedSiteId = null;
  state.selectedArrivalId = null;
  state.selectedActorId = null;
  state.selectedTriggerId = null;
  state.bulkSelection = [];
  state.selectionRect = null;
  state.groundTool = "brush";
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
  renderMapSelector();
  configureEditorNavigation();
  renderAll();
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
  return JSON.stringify({ data: state.data, siteNamesJa: state.siteNamesJa });
}

function restoreChangeSnapshot(snapshot) {
  const value = JSON.parse(snapshot);
  state.data = value.data;
  state.siteNamesJa = value.siteNamesJa;
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
  if (!objects.some((object) => object.id === state.objectId)) state.objectId = objects[0]?.id || null;
  if (!state.data?.objects?.some((instance) => instance.id === state.selectedInstanceId)) state.selectedInstanceId = null;
  if (!state.data?.sites?.some((site) => site.id === state.selectedSiteId)) state.selectedSiteId = null;
  if (!state.data?.arrival_points?.some((arrival) => arrival.id === state.selectedArrivalId)) state.selectedArrivalId = null;
  if (!state.data?.actors?.some((actor) => actor.id === state.selectedActorId)) state.selectedActorId = null;
  if (!state.data?.event_triggers?.some((trigger) => trigger.id === state.selectedTriggerId)) state.selectedTriggerId = null;
  state.bulkSelection = (state.bulkSelection || []).filter((item) => bulkItemExists(item));
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

function actorAssetId(kind) {
  return kind === "prop" ? "prop" : "character";
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

function actorSpriteSource(assetId, spriteIndex, facing = "down") {
  const sheet = actorSheets[assetId];
  const size = state.actorAssets[assetId]?.sprite_size;
  if (!sheet?.ready || !Array.isArray(size) || !Number.isInteger(spriteIndex)) return null;
  const columns = Math.floor(sheet.canvas.width / size[0]);
  if (columns < 1 || spriteIndex < 0 || spriteIndex >= actorSpriteCapacity(assetId)) return null;
  let sourceX = (spriteIndex % columns) * size[0];
  let sourceY = Math.floor(spriteIndex / columns) * size[1];
  if (assetId === "character") {
    const facingRow = { up: 0, right: 1, down: 2, left: 3 }[facing] ?? 2;
    sourceY += facingRow * CELL_SIZE;
  }
  return { sheet, sourceX, sourceY };
}

function drawActorSprite(canvas, assetId, spriteIndex, facing = "down") {
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  const source = actorSpriteSource(assetId, spriteIndex, facing);
  if (!source) return;
  const scale = Math.max(1, Math.floor(Math.min(canvas.width, canvas.height) / CELL_SIZE));
  const drawSize = CELL_SIZE * scale;
  const drawX = Math.floor((canvas.width - drawSize) / 2);
  const drawY = Math.floor((canvas.height - drawSize) / 2);
  context.imageSmoothingEnabled = false;
  context.drawImage(source.sheet.canvas, source.sourceX, source.sourceY, CELL_SIZE, CELL_SIZE, drawX, drawY, drawSize, drawSize);
}

function drawActorOnMap(context, actor, scale) {
  const source = actorSpriteSource(actorAssetId(actor.kind), actor.sprite_index, actor.facing);
  if (!source) return false;
  context.imageSmoothingEnabled = false;
  context.drawImage(
    source.sheet.canvas,
    source.sourceX,
    source.sourceY,
    CELL_SIZE,
    CELL_SIZE,
    actor.position[0] * scale,
    actor.position[1] * scale,
    scale,
    scale,
  );
  return true;
}

function drawSelectedActorSprite() {
  const actor = currentActor();
  const canvas = document.querySelector("[data-selected-actor-sprite]");
  if (!actor || !canvas) return;
  drawActorSprite(canvas, actorAssetId(actor.kind), actor.sprite_index, actor.facing);
}

function renderActorSpriteDialog() {
  const actor = state.data?.actors?.find((item) => item.id === state.spritePickerActorId);
  const options = byId("actor-sprite-options");
  if (!actor) {
    options.innerHTML = `<div class="empty-state">actorが選択されていません。</div>`;
    return;
  }
  const assetId = actorAssetId(actor.kind);
  const capacity = actorSpriteCapacity(assetId);
  byId("actor-sprite-dialog-title").textContent = actor.kind === "prop" ? "固定物のスプライトを選択" : "キャラクターのスプライトを選択";
  byId("actor-sprite-dialog-summary").textContent = capacity
    ? `${capacity}件${assetId === "character" ? "・下向きの画像で表示" : ""}`
    : "画像を読み込んでいます…";
  options.innerHTML = capacity
    ? Array.from({ length: capacity }, (_, index) => `<button class="actor-sprite-option ${index === actor.sprite_index ? "selected" : ""}" type="button" role="option" aria-selected="${index === actor.sprite_index}" data-action="select-actor-sprite" data-sprite-index="${index}"><canvas width="48" height="48" data-actor-sprite-option="${index}"></canvas><span>#${index}</span></button>`).join("")
    : `<div class="empty-state">スプライト画像を表示できません。</div>`;
  options.querySelectorAll("[data-actor-sprite-option]").forEach((canvas) => {
    drawActorSprite(canvas, assetId, Number(canvas.dataset.actorSpriteOption));
  });
}

function openActorSpriteDialog() {
  const actor = currentActor();
  if (!actor) return;
  state.spritePickerActorId = actor.id;
  renderActorSpriteDialog();
  byId("actor-sprite-dialog").showModal();
}

function closeActorSpriteDialog() {
  const dialog = byId("actor-sprite-dialog");
  if (dialog.open) dialog.close();
}

function selectActorSprite(spriteIndex) {
  const actor = state.data?.actors?.find((item) => item.id === state.spritePickerActorId);
  const assetId = actor ? actorAssetId(actor.kind) : null;
  if (!actor || !Number.isInteger(spriteIndex) || spriteIndex < 0 || spriteIndex >= actorSpriteCapacity(assetId)) return;
  if (actor.sprite_index !== spriteIndex) commit(() => { actor.sprite_index = spriteIndex; });
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
        <p class="subtle" style="margin-bottom:9px">${state.groundTool === "rectangle" ? "左ドラッグした矩形をまとめて塗ります。" : "左ドラッグで通過したセルを塗ります。"}</p>
        <div class="palette-list">${state.tileset.grounds.map((ground, index) => `
          <button class="palette-item ${ground.id === state.groundId ? "active" : ""}" type="button" data-action="select-ground" data-id="${escapeHtml(ground.id)}">
            <canvas data-ground-thumb="${index}" width="48" height="48"></canvas><span>${escapeHtml(ground.id)}</span>
          </button>`).join("")}</div>
      </div>`;
  } else if (state.tab === "object") {
    container.innerHTML = `
      <div class="section">
        <div class="section-title"><h2>オブジェクト</h2><span class="subtle">左クリックで配置・右クリック／ドラッグで選択・移動</span></div>
        <div class="palette-list">${state.tileset.objects.map((object, index) => `
          <button class="palette-item ${object.id === state.objectId ? "active" : ""}" type="button" data-action="select-object-definition" data-id="${escapeHtml(object.id)}">
            <canvas data-object-thumb="${index}" width="${object.size[0] * 16}" height="${object.size[1] * 16}"></canvas><span>${escapeHtml(object.id)}</span>${object.default_draw_group === "object_overlay" ? `<span class="palette-meta">前面パーツ</span>` : ""}
          </button>`).join("") || `<div class="empty-state">オブジェクト定義がありません。</div>`}</div>
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
          <button class="travel-item ${actor.id === state.selectedActorId ? "active" : ""}" type="button" data-action="select-actor" data-id="${escapeHtml(actor.id)}"><strong>${escapeHtml(actor.id)}</strong>${actor.position.join(", ")} / ${escapeHtml(actor.kind)} #${actor.sprite_index}</button>`).join("") || `<div class="empty-state">actorがありません。</div>`}</div>
        <div class="row" style="margin-top:9px"><button class="button secondary small" type="button" data-action="prepare-actor">actorを配置</button></div>
      </div>
      <div class="section">
        <div class="section-title"><h2>トリガー</h2><span class="subtle">${standaloneTriggers().length}件</span></div>
        <div class="travel-list">${standaloneTriggers().map((trigger) => `
          <button class="travel-item ${trigger.id === state.selectedTriggerId ? "active" : ""}" type="button" data-action="select-trigger" data-id="${escapeHtml(trigger.id)}"><strong>${escapeHtml(trigger.event_id)}</strong>anchor: ${escapeHtml(trigger.anchor.kind)} / ${trigger.activations.join(", ")}</button>`).join("") || `<div class="empty-state">トリガーがありません。</div>`}</div>
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

function eventIdOptions(selected) {
  const ids = [...state.eventOptions];
  if (selected && !ids.includes(selected)) ids.push(selected);
  return `<option value="" ${selected ? "" : "selected"}>イベントを選択</option>` + ids.map((id) => `<option value="${escapeHtml(id)}" ${id === selected ? "selected" : ""}>${escapeHtml(id)}${state.eventOptions.includes(id) ? "" : "（未定義）"}</option>`).join("");
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
    arrival_ids: [...option.arrival_ids],
  }));
  const current = options.find((option) => option.map_id === state.data.map_id);
  const arrivalIds = state.data.arrival_points.map((arrival) => arrival.id);
  if (current) current.arrival_ids = arrivalIds;
  else options.push({ map_id: state.data.map_id, arrival_ids: arrivalIds });
  return options.sort((left, right) => left.map_id.localeCompare(right.map_id));
}

function destinationMapOptions(selected) {
  const mapIds = availableDestinations().map((option) => option.map_id);
  if (selected && !mapIds.includes(selected)) mapIds.push(selected);
  return `<option value="" ${selected ? "" : "selected"}>選択してください</option>` + mapIds.map((mapId) => `<option value="${escapeHtml(mapId)}" ${selected === mapId ? "selected" : ""}>${escapeHtml(mapId)}${availableDestinations().some((option) => option.map_id === mapId) ? "" : "（未作成）"}</option>`).join("");
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
        <div class="instance-card"><strong>${escapeHtml(instance.definition_id)}</strong>ID: ${escapeHtml(instance.id)}<br>起点: ${instance.origin.join(", ")} / ${objectDefinition(instance)?.default_draw_group === "object_overlay" ? "前面パーツ" : "通常オブジェクト"}<br>同一下端内の順序: ${instance.order}</div>
        <div class="row between" style="margin-top:9px">
          <div class="row"><button class="button ghost small" type="button" data-action="object-back">背面へ</button><button class="button ghost small" type="button" data-action="object-front">前面へ</button></div>
          <button class="button danger small" type="button" data-action="delete-instance">配置を削除</button>
        </div>
        <div class="row" style="margin-top:9px"><button class="button secondary small" type="button" data-action="${attachedSite ? "open-attached-site" : "attach-site"}">${attachedSite ? `${siteLabel} ${escapeHtml(attachedSite.id)} を編集` : `${siteLabel}として設定`}</button></div>`
        : `<div class="empty-state">マップ上のオブジェクトを右クリックすると選択できます。</div>`}
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
        <div class="row between" style="margin-top:9px"><button class="button ghost small" type="button" data-action="move-arrival">セルを移動</button><button class="button danger small" type="button" data-action="delete-arrival">到着地点を削除</button></div>
      ` : `<div class="empty-state">左の一覧またはキャンバスから到着地点を選択してください。</div>`}
    </div>`;
  const eventInspector = `
    <div class="section">
      <div class="section-title"><h2>選択actor</h2><span class="subtle">${state.data.actors.length}件</span></div>
      ${actor ? `<div class="instance-card"><strong>${escapeHtml(actor.id)}</strong>セル: ${actor.position.join(", ")}</div>
        <div class="form-grid" style="margin-top:9px">
          <div class="field full"><label>actor ID</label><input type="text" value="${escapeHtml(actor.id)}" data-actor-field="id"></div>
          <div class="field full"><label>種別</label><select data-actor-field="kind"><option value="prop" ${actor.kind === "prop" ? "selected" : ""}>固定物（向きなし）</option><option value="stationary" ${actor.kind === "stationary" ? "selected" : ""}>固定キャラ</option><option value="roaming" ${actor.kind === "roaming" ? "selected" : ""}>移動キャラ</option></select></div>
          <div class="field full"><label>スプライト</label><button class="button actor-sprite-select" type="button" data-action="open-actor-sprite-dialog"><canvas width="48" height="48" data-selected-actor-sprite></canvas><span class="actor-sprite-select-copy"><strong>番号 #${actor.sprite_index}</strong><span>画像から選択</span></span></button></div>
          ${actor.kind === "prop" ? "" : `<div class="field full"><label>向き</label><select data-actor-field="facing">${facingOptions(actor.facing)}</select></div>`}
          <div class="field full"><label>イベント</label><select data-actor-event-id="true">${eventIdOptions(linkedActorTrigger?.event_id || "")}</select><div class="field-note">touch・interactで自動的に起動します。</div></div>
        </div><div class="row between" style="margin-top:9px"><div class="row"><button class="button ghost small" data-action="move-actor">セルを移動</button>${editorRoute && linkedActorTrigger?.event_id ? `<button class="button secondary small" data-action="open-actor-event">イベント本文を編集</button>` : ""}</div><button class="button danger small" data-action="delete-actor">actorを削除</button></div>` : `<div class="empty-state">actorを選択してください。</div>`}
    </div>
    <div class="section">
      <div class="section-title"><h2>選択トリガー</h2><span class="subtle">${standaloneTriggers().length}件</span></div>
      ${trigger ? `<div class="instance-card"><strong>${escapeHtml(trigger.event_id)}</strong>anchor: ${escapeHtml(trigger.anchor.kind)} / 対象 ${trigger.offsets.length}セル</div>
        <div class="form-grid" style="margin-top:9px">
          <div class="field full"><label>イベント</label><select data-trigger-field="event_id">${eventIdOptions(trigger.event_id)}</select></div>
          <div class="field full"><label>発火方法</label><div class="row">${["step","touch"].map(value => `<label><input type="checkbox" data-trigger-activation="${value}" ${trigger.activations.includes(value) ? "checked" : ""}> ${value}</label>`).join("")}</div></div>
        </div><div class="row between" style="margin-top:9px"><div class="row"><button class="button ghost small" data-action="edit-trigger-offsets">対象セルを編集</button>${editorRoute ? `<button class="button secondary small" data-action="open-trigger-event">イベント本文を編集</button>` : ""}</div><button class="button danger small" data-action="delete-trigger">triggerを削除</button></div>` : `<div class="empty-state">トリガーを選択してください。</div>`}
    </div>`;
  const bgmOptions = [...new Set([...state.bgmOptions, state.data.bgm_id])]
    .filter(Boolean)
    .sort()
    .map((bgmId) => `<option value="${escapeHtml(bgmId)}" ${bgmId === state.data.bgm_id ? "selected" : ""}>${escapeHtml(bgmId)}</option>`)
    .join("");
  byId("inspector-content").innerHTML = `
    <div class="section">
      <div class="section-title"><h2>マップ設定</h2><span class="subtle">${escapeHtml(state.data.profile)} / ${escapeHtml(state.data.tileset_id)}</span></div>
      <div class="form-grid">
        <div class="field full"><label>BGM</label><select data-map-field="bgm_id">${bgmOptions}</select></div>
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
  normalizeSelections();
  clearSelectionsOutsideTab(state.tab);
  document.querySelectorAll(".tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === state.tab));
  byId("grid-toggle").checked = state.showGrid;
  byId("collision-toggle").checked = state.showCollision;
  byId("ground-only-toggle").checked = state.showGroundOnly;
  byId("ground-only-control").hidden = state.tab !== "ground";
  byId("animation-toggle").textContent = state.paused ? "再生" : "一時停止";
  byId("zoom-label").textContent = `${state.zoom}×`;
  byId("map-title").textContent = state.data.map_id;
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

function drawActors(context, scale) {
  for (const actor of state.data.actors) {
    const selected = actor.id === state.selectedActorId || isBulkSelected("actor", actor.id);
    const rendered = drawActorOnMap(context, actor, scale);
    if (!rendered) {
      const centerX = (actor.position[0] + .5) * scale;
      const centerY = (actor.position[1] + .5) * scale;
      context.fillStyle = selected ? "#ff67bd" : "#76d7c4";
      context.beginPath();
      context.arc(centerX, centerY, Math.max(5, scale * .22), 0, Math.PI * 2);
      context.fill();
      if (actor.kind !== "prop") drawDirectionMarker(context, actor.position, actor.facing, scale, selected ? "#ffb4dc" : "#b3fff0");
    }
    if (selected) drawCellSelectionFrame(context, actor.position, scale);
  }
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
  if (state.tab !== "object" || !state.hoveredCell || state.pointerDrag || state.bulkSelection.length) return;
  const definition = state.tileset.objects.find((object) => object.id === state.objectId);
  if (!definition) return;
  const selected = currentInstance();
  if (selected && instanceOccupies(selected, ...state.hoveredCell)) return;
  const [x, y] = state.hoveredCell;
  const valid = x + definition.size[0] <= state.data.size[0]
    && y + definition.size[1] <= state.data.size[1]
    && !state.data.objects.some((instance) => instance.origin[0] === x && instance.origin[1] === y);
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
      if (cell.draw_group === "object_foreground") continue;
      drawSourceTile(context, frameTile(cell, now), cell.position[0] * scale, cell.position[1] * scale, scale);
    }
    if (state.showCollision && !groundOnly) {
      context.fillStyle = "rgba(239,91,80,.32)";
      context.strokeStyle = "rgba(255,130,118,.9)";
      context.lineWidth = Math.max(1, state.zoom);
      state.resolved.collision.forEach((blocked, index) => {
        if (!blocked) return;
        const x = (index % width) * scale;
        const y = Math.floor(index / width) * scale;
        context.fillRect(x, y, scale, scale);
        context.strokeRect(x + .5, y + .5, scale - 1, scale - 1);
      });
    }
  }
  if (!groundOnly) drawActors(context, scale);
  if (state.resolved && !groundOnly) {
    for (const cell of state.resolved.object_cells) {
      if (cell.draw_group !== "object_foreground") continue;
      drawSourceTile(context, frameTile(cell, now), cell.position[0] * scale, cell.position[1] * scale, scale);
    }
  }
  if (!groundOnly) for (const selected of state.data.objects.filter((instance) => instance.id === state.selectedInstanceId || isBulkSelected("object", instance.id))) {
    const definition = state.tileset.objects.find((object) => object.id === selected.definition_id);
    if (definition) {
      context.strokeStyle = "#ff4fa3";
      context.lineWidth = Math.max(2, state.zoom);
      context.strokeRect(selected.origin[0] * scale + 1, selected.origin[1] * scale + 1, definition.size[0] * scale - 2, definition.size[1] * scale - 2);
    }
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
}

function animationLoop(now) {
  if (!state.paused) drawMap(now);
  requestAnimationFrame(animationLoop);
}

function updateToolStatus() {
  if (!state.data) return;
  const rangeHint = "右ドラッグ: 配置要素を範囲選択";
  if (state.bulkSelection.length) byId("tool-status").textContent = `${state.bulkSelection.length}件を範囲選択中 / 選択対象を左ドラッグ: 一括移動 / Delete: 一括削除`;
  else if (state.tab === "ground") byId("tool-status").textContent = `${state.groundTool === "rectangle" ? "矩形塗り" : "地面ブラシ"}: ${state.groundId || "—"} / ${rangeHint}`;
  else if (state.tab === "object") byId("tool-status").textContent = `左: ${state.objectId || "—"}を配置 / 右クリック: 選択 / ${rangeHint}`;
  else if (state.tab === "site") {
    const selectedSite = currentSite();
    const labels = {
      select: selectedSite?.anchor?.kind === "cell" ? "ピンクのアンカーを左ドラッグして移動" : "拠点または到着地点を選択",
      create_site: "座標アンカーにするセルを選択",
      entrance: "入口セルをクリックして追加・解除",
      create_arrival: "到着地点にするセルを選択",
      move_arrival: "到着地点の新しいセルを選択",
    };
    byId("tool-status").textContent = `${labels[state.travelTool] || labels.select} / ${rangeHint}`;
  } else {
    const labels = {
      select: "actorまたはtriggerを選択",
      create_actor: "actorを置くセルを選択",
      create_trigger: "triggerの基準セルを選択",
      create_object_trigger: "triggerを設定するobjectを選択",
      move_actor: "actorの新しいセルを選択",
      trigger_offsets: "trigger対象セルをクリックして追加・解除",
    };
    byId("tool-status").textContent = `${labels[state.eventTool] || labels.select} / ${rangeHint}`;
  }
}

function mapCellFromPointer(event) {
  const canvas = byId("map-canvas");
  const rect = canvas.getBoundingClientRect();
  const scale = CELL_SIZE * state.zoom;
  const x = Math.floor((event.clientX - rect.left) * canvas.width / rect.width / scale);
  const y = Math.floor((event.clientY - rect.top) * canvas.height / rect.height / scale);
  if (x < 0 || y < 0 || x >= state.data.size[0] || y >= state.data.size[1]) return null;
  return [x, y];
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
    if (definition?.cells.some((cell) => pointInCellRect(addPoint(instance.origin, cell.offset), rect))) {
      items.push({ kind: "object", id: instance.id });
    }
  }
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
    if (pointInCellRect(actor.position, rect)) items.push({ kind: "actor", id: actor.id });
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
    return Boolean(actor && actor.position[0] === cell[0] && actor.position[1] === cell[1]);
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
  const movedActors = new Map();
  for (const descriptor of state.pointerDrag.descriptors) {
    const position = candidatePosition(descriptor, delta);
    if (descriptor.kind === "object") {
      const instance = state.data.objects.find((record) => record.id === descriptor.id);
      const definition = objectDefinition(instance);
      if (!definition || position[0] < 0 || position[1] < 0
        || position[0] + definition.size[0] > width || position[1] + definition.size[1] > height) return false;
      movedObjects.set(descriptor.id, position);
    } else if (!inBounds(position)) return false;
    if (descriptor.kind === "actor") movedActors.set(descriptor.id, position);
    if (descriptor.kind === "site") {
      const site = state.data.sites.find((record) => record.id === descriptor.id);
      if (site && site.entrance_offsets.some((offset) => !inBounds(addPoint(position, offset)))) return false;
    } else if (descriptor.kind === "trigger") {
      const trigger = state.data.event_triggers.find((record) => record.id === descriptor.id);
      if (trigger && trigger.offsets.some((offset) => !inBounds(addPoint(position, offset)))) return false;
    }
  }
  const origins = new Set();
  for (const instance of state.data.objects) {
    const origin = movedObjects.get(instance.id) || instance.origin;
    const key = origin.join(",");
    if (origins.has(key)) return false;
    origins.add(key);
  }
  for (const site of state.data.sites) {
    if (site.anchor?.kind !== "object" || !movedObjects.has(site.anchor.object_id)) continue;
    const origin = movedObjects.get(site.anchor.object_id);
    if (site.entrance_offsets.some((offset) => !inBounds(addPoint(origin, offset)))) return false;
  }
  for (const trigger of state.data.event_triggers) {
    let origin = null;
    if (trigger.anchor?.kind === "object") origin = movedObjects.get(trigger.anchor.object_id) || null;
    else if (trigger.anchor?.kind === "actor") origin = movedActors.get(trigger.anchor.actor_id) || null;
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

function clearBulkSelectionWithEscape(event) {
  if (event.key !== "Escape" || !state.bulkSelection.length || state.pointerDrag || state.pointerStroke) return false;
  if (["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName) || event.target.isContentEditable) return false;
  if (document.querySelector("dialog[open]")) return false;
  event.preventDefault();
  clearBulkSelection();
  renderAll();
  showToast("範囲選択を解除しました。");
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
  if (state.travelTool === "move_arrival" && arrival) {
    commit(() => {
      arrival.position = [...cell];
      state.travelTool = "select";
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
    const actor = { id, position: [...position], kind: "stationary", sprite_index: 0, facing: "down" };
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
  if (actor && !actorTrigger(actor.id)) {
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
  for (const actor of state.data.actors) {
    if (actor.position[0] === x && actor.position[1] === y) candidates.push({ kind: "actor", id: actor.id, tab: "event" });
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
  const instance = instanceAt(x, y);
  if (instance) candidates.push({ kind: "object", id: instance.id, tab: "object" });
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
  else state.selectedInstanceId = candidate.id;
  const actor = candidate.kind === "actor" ? currentActor() : null;
  if (actor && !actorTrigger(actor.id)) commit(() => ensureActorTrigger(actor));
  else renderAll();
  return candidate;
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
  if (state.eventTool === "move_actor" && currentActor()) {
    commit(() => { currentActor().position = [...cell]; state.eventTool = "select"; });
    return;
  }
  if (state.eventTool === "trigger_offsets" && currentTrigger()) {
    const offset = triggerOffsetForCell(currentTrigger(), cell);
    if (!offset) return;
    commit(() => {
      const trigger = currentTrigger();
      const index = trigger.offsets.findIndex((item) => item[0] === offset[0] && item[1] === offset[1]);
      if (index >= 0 && trigger.offsets.length > 1) trigger.offsets.splice(index, 1);
      else if (index < 0) trigger.offsets.push(offset);
    });
    return;
  }
  selectEventAt(cell);
}

function placeObject(x, y) {
  const definition = state.tileset.objects.find((object) => object.id === state.objectId);
  if (!definition) return;
  if (x + definition.size[0] > state.data.size[0] || y + definition.size[1] > state.data.size[1]) {
    showToast("オブジェクトがマップ範囲外へはみ出します。", true);
    return;
  }
  const sameOrigin = state.data.objects.find((instance) => instance.origin[0] === x && instance.origin[1] === y);
  if (sameOrigin) {
    state.selectedInstanceId = sameOrigin.id;
    renderAll();
    showToast("同じ起点には配置できないため、既存の配置を選択しました。", true);
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

function objectBottom(instance) {
  const definition = objectDefinition(instance);
  return definition ? instance.origin[1] + definition.size[1] - 1 : instance.origin[1];
}

function objectDrawGroupOrder(instance) {
  return objectDefinition(instance)?.default_draw_group === "object_overlay" ? 1 : 0;
}

function compareObjectsBackToFront(left, right) {
  return objectDrawGroupOrder(left) - objectDrawGroupOrder(right)
    || objectBottom(left) - objectBottom(right)
    || left.order - right.order
    || left.origin[0] - right.origin[0]
    || left.id.localeCompare(right.id);
}

function instanceOccupies(instance, x, y) {
  const definition = objectDefinition(instance);
  return Boolean(definition?.cells.some((cell) => instance.origin[0] + cell.offset[0] === x && instance.origin[1] + cell.offset[1] === y));
}

function instanceAt(x, y) {
  return [...state.data.objects]
    .sort((left, right) => compareObjectsBackToFront(right, left))
    .find((instance) => instanceOccupies(instance, x, y)) || null;
}

function validObjectOrigin(instance, x, y) {
  const definition = objectDefinition(instance);
  if (!definition || x < 0 || y < 0 || x + definition.size[0] > state.data.size[0] || y + definition.size[1] > state.data.size[1]) return false;
  return !state.data.objects.some((item) => item.id !== instance.id && item.origin[0] === x && item.origin[1] === y);
}

function beginObjectDrag(event, cell) {
  const instance = currentInstance();
  if (!instance || !instanceOccupies(instance, ...cell)) return false;
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
  clearBulkSelection();
  if (action === "select-ground") {
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
    if (currentActor() && !actorTrigger(currentActor().id)) {
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
  });
}

function handleInspectorAction(element) {
  const action = element.dataset.action;
  if (action === "resize-map") resizeMap();
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
  else if (action === "object-front" || action === "object-back") commit(() => {
    const instance = currentInstance();
    const orders = state.data.objects.map((item) => item.order);
    instance.order = action === "object-front" ? Math.max(...orders) + 1 : Math.min(...orders) - 1;
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
  else if (action === "move-arrival") {
    state.travelTool = "move_arrival";
    renderAll();
  }
  else if (action === "delete-arrival") commit(() => {
    const index = state.data.arrival_points.findIndex((arrival) => arrival.id === state.selectedArrivalId);
    if (index >= 0) state.data.arrival_points.splice(index, 1);
    state.selectedArrivalId = null;
    state.travelTool = "select";
  });
  else if (action === "move-actor") {
    state.eventTool = "move_actor";
    renderAll();
  }
  else if (action === "open-actor-sprite-dialog") openActorSpriteDialog();
  else if (action === "open-actor-event" && currentActor()) {
    const trigger = actorTrigger(currentActor().id);
    if (!trigger?.event_id) return;
    const [namespace, eventId] = trigger.event_id.split(".", 2);
    const url = editorUrl("event", { namespace, event: eventId });
    if (url) window.location.assign(url);
  }
  else if (action === "delete-actor") commit(() => {
    const actorId = state.selectedActorId;
    state.data.actors = state.data.actors.filter((actor) => actor.id !== actorId);
    state.data.event_triggers = state.data.event_triggers.filter((trigger) => !(trigger.anchor?.kind === "actor" && trigger.anchor.actor_id === actorId));
    state.selectedActorId = null;
    state.selectedTriggerId = null;
    state.eventTool = "select";
  });
  else if (action === "edit-trigger-offsets") {
    state.eventTool = "trigger_offsets";
    renderAll();
  }
  else if (action === "open-trigger-event" && currentTrigger()) {
    const [namespace, eventId] = currentTrigger().event_id.split(".", 2);
    const url = editorUrl("event", { namespace, event: eventId });
    if (url) window.location.assign(url);
  }
  else if (action === "delete-trigger") commit(() => {
    state.data.event_triggers = state.data.event_triggers.filter((trigger) => trigger.id !== state.selectedTriggerId);
    state.selectedTriggerId = null;
    state.eventTool = "select";
  });
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
      if (value === "prop") delete actor.facing;
      else if (!actor.facing) actor.facing = "down";
      const capacity = actorSpriteCapacity(actorAssetId(value));
      if (capacity > 0 && actor.sprite_index >= capacity) actor.sprite_index = 0;
    } else if (path === "sprite_index") actor.sprite_index = Number(value);
    else actor[path] = value;
  });
}

function updateActorEventId(value) {
  const actor = currentActor();
  if (!actor) return;
  commit(() => {
    ensureActorTrigger(actor).event_id = value;
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
      const result = await api("/api/resolve", { method: "POST", body: JSON.stringify({ data: state.data, site_names_ja: state.siteNamesJa }) });
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
  if (!canSave()) return;
  updateSaveState("dirty", "保存・生成中…");
  try {
    const result = await api("/api/save", { method: "POST", body: JSON.stringify({ data: state.data, site_names_ja: state.siteNamesJa }) });
    applyValidationResult(result);
    if (result.saved) {
      state.dirty = false;
      state.history = [];
      state.future = [];
      const existing = state.mapCatalog.find((item) => item.map_id === state.data.map_id);
      const record = {
        map_id: state.data.map_id,
        profile: state.data.profile,
        tileset_id: state.data.tileset_id,
        size: state.data.size,
      };
      if (existing) Object.assign(existing, record, { is_new: false });
      else state.mapCatalog.push(record);
      showToast("制作用マップを保存し、ゲーム用データを生成しました。");
    } else showToast("エラーを修正してから保存してください。", true);
    renderMapSelector();
    renderAll();
  } catch (error) {
    updateSaveState("error", "保存失敗");
    showToast(error.message, true);
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
    const [catalog, payload] = await Promise.all([
      api("/api/catalog"),
      api(requestedMap ? `/api/document?map=${encodeURIComponent(requestedMap)}` : "/api/document"),
    ]);
    state.mapCatalog = catalog.maps || [];
    state.tilesetCatalog = catalog.tilesets || [];
    applyDocumentPayload(payload);
  } catch (error) {
    showToast(error.message, true);
    updateSaveState("error", "読込失敗");
  }
}

byId("map-select").addEventListener("change", async (event) => {
  const mapId = event.target.value;
  if (mapId === state.data?.map_id) return;
  if (state.dirty && !window.confirm("未保存の変更を破棄してマップを切り替えますか？")) {
    renderMapSelector();
    return;
  }
  try {
    await loadMapDocument(mapId);
  } catch (error) {
    showToast(error.message, true);
    renderMapSelector();
  }
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
  if (!window.confirm(`マップ ${state.data.map_id} の内容をすべてクリアしてマップチップを変更しますか？`)) return;
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
  else if (event.target.dataset.siteNameJa) {
    state.siteNameEditing = false;
    renderPalette();
  }
  else if (event.target.dataset.siteField) updateSiteField(event.target.dataset.siteField, event.target.value);
  else if (event.target.dataset.arrivalField) updateArrivalField(event.target.dataset.arrivalField, event.target.type === "checkbox" ? event.target.checked : event.target.value);
  else if (event.target.dataset.actorField) updateActorField(event.target.dataset.actorField, event.target.value);
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
  else if (target.dataset.action === "select-actor-sprite") selectActorSprite(Number(target.dataset.spriteIndex));
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
  const cell = mapCellFromPointer(event);
  if (!cell) return;
  state.hoveredCell = [...cell];
  if (event.button === 2) {
    event.preventDefault();
    if (beginBulkDrag(event, cell)) return;
    beginRangeSelection(event, cell);
    return;
  }
  if (event.button !== 0) return;
  if (beginBulkDrag(event, cell)) return;
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
  } else if (state.tab === "event") handleEventCell(cell);
  else if (!beginSiteAnchorDrag(event, cell)) handleTravelCell(cell);
});
mapCanvas.addEventListener("pointermove", (event) => {
  const cell = mapCellFromPointer(event);
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
});
mapCanvas.addEventListener("pointerup", (event) => {
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
mapCanvas.addEventListener("pointercancel", () => {
  if (state.pointerStroke && !state.pointerStroke.changed) state.history.pop();
  if (state.pointerDrag?.kind === "ground_rectangle") state.history.pop();
  else if (state.pointerDrag && state.pointerDrag.kind !== "range_selection" && !state.pointerDrag.changed) state.history.pop();
  if (state.pointerDrag?.kind === "range_selection") state.selectionRect = null;
  state.pointerStroke = null;
  state.pointerDrag = null;
  state.groundPaintRect = null;
  renderAll();
});
mapCanvas.addEventListener("contextmenu", (event) => event.preventDefault());
mapCanvas.addEventListener("pointerleave", () => {
  byId("cursor-status").textContent = "セル —";
  state.hoveredCell = null;
  drawMap(performance.now());
});

window.addEventListener("keydown", (event) => {
  if (clearBulkSelectionWithEscape(event)) return;
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
window.addEventListener("beforeunload", (event) => {
  if (state.dirty) { event.preventDefault(); event.returnValue = ""; }
});

requestAnimationFrame(animationLoop);
configureEditorNavigation();
initialize();
