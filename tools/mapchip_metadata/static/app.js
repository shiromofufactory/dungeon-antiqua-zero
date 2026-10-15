"use strict";

document.addEventListener("contextmenu", (event) => event.preventDefault(), { capture: true });

const DIRECTIONS = ["nw", "n", "ne", "w", "center", "e", "sw", "s", "se"];
const NEIGHBOR_CYCLE = ["any", "same", "different"];
const OBJECT_COLLISION_STATES = ["blocked", "passable", "passable_override"];
const OBJECT_COLLISION_LABELS = {
  blocked: "通行不可",
  passable: "通行を妨げない",
  passable_override: "通行可で上書き",
};
const OBJECT_LAYER_CLASSES = {
  object: "map-layer-back",
  object_y_sorted: "map-layer-normal",
  object_foreground: "map-layer-front",
  object_overlay: "map-layer-top",
};
const OBJECT_LAYERS = [["object", "背面"], ["object_y_sorted", "通常"], ["object_foreground", "前面"], ["object_overlay", "最前面"]];
const SOURCE_USAGE_COLORS = [
  ["ground", "--ground-color"], ["boundary", "--boundary-color"],
  ["object", "--layer-back-color"], ["object_y_sorted", "--layer-normal-color"],
  ["object_foreground", "--layer-front-color"], ["object_overlay", "--layer-top-color"],
];
const SESSION_CLIENT_HEADER = "mapchip-metadata-ui";
const PREVIEW_SETTINGS_VERSION = 1;
const LAST_TILESET_STORAGE_KEY = "da0.mapchip-metadata.last-tileset.v1";
let token = new URLSearchParams(window.location.search).get("token") || "";
const editorRoute = window.location.pathname.match(/^\/(tileset|map|event)(?:\/|$)/)?.[1] || null;

const state = {
  data: null,
  imageInfo: null,
  imageUrl: "",
  diagnostics: [],
  tilesetCatalog: [],
  sourceImages: [],
  dirty: false,
  history: [],
  future: [],
  objectOrigins: [],
  tab: "ground",
  groundIndex: 0,
  boundaryIndex: 0,
  objectIndex: 0,
  objectLayer: "object_y_sorted",
  choiceIndex: 0,
  frameIndex: 0,
  selection: { x: 0, y: 0, width: 1, height: 1 },
  zoom: 3,
  dragStart: null,
  definitionDrag: null,
  suppressDefinitionClickUntil: 0,
  previewGrounds: [],
  previewShowCollision: false,
  previewPaused: false,
  previewStartedAt: performance.now(),
  validateTimer: null,
};
let pendingEditorNavigationUrl = null;
let pendingTilesetNavigationId = null;
let navigationBusy = false;

const rawImage = new Image();
const processedImage = document.createElement("canvas");
let processedImageUrl = "";

const byId = (id) => document.getElementById(id);
const clone = (value) => JSON.parse(JSON.stringify(value));
const escapeHtml = (value) => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");

function previewSettingsKey() {
  const tilesetId = state.data?.tileset_id || "unknown";
  return `da0.mapchip-metadata.preview.v${PREVIEW_SETTINGS_VERSION}:${tilesetId}`;
}

function savePreviewSettings() {
  if (!state.data) return;
  try {
    window.localStorage.setItem(previewSettingsKey(), JSON.stringify({
      grounds: state.previewGrounds,
      showCollision: state.previewShowCollision,
      paused: state.previewPaused,
    }));
  } catch (_error) {
    // Preview settings are optional and must not block metadata editing.
  }
}

function restorePreviewSettings() {
  try {
    const stored = window.localStorage.getItem(previewSettingsKey());
    if (!stored) return;
    const settings = JSON.parse(stored);
    if (Array.isArray(settings.grounds) && settings.grounds.length === 9 && settings.grounds.every((id) => typeof id === "string")) {
      state.previewGrounds = settings.grounds;
    }
    if (typeof settings.showCollision === "boolean") state.previewShowCollision = settings.showCollision;
    if (typeof settings.paused === "boolean") state.previewPaused = settings.paused;
  } catch (_error) {
    // Ignore corrupt or unavailable browser storage and use the defaults.
  }
}

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
      tileset: state.data?.tileset_id,
      map: new URLSearchParams(window.location.search).get("map"),
    });
  });
}

function navigateToEditor(url) {
  if (!url || navigationBusy) return;
  if (!state.dirty) {
    window.location.assign(url);
    return;
  }
  pendingEditorNavigationUrl = url;
  pendingTilesetNavigationId = null;
  byId("unsaved-navigation-message").textContent = "変更を保存してからエディタを切り替えますか？";
  byId("unsaved-navigation-dialog").showModal();
  byId("unsaved-navigation-dialog").querySelector('[data-navigation-choice="save"]').focus();
}

async function switchTilesetDocument(tilesetId) {
  try {
    await loadTilesetDocument(tilesetId);
    return true;
  } catch (error) {
    showToast(error.message, true);
    renderTilesetSelector();
    return false;
  }
}

async function requestTilesetSwitch(tilesetId) {
  if (navigationBusy || tilesetId === state.data?.tileset_id) {
    renderTilesetSelector();
    return;
  }
  if (!state.dirty) {
    await switchTilesetDocument(tilesetId);
    return;
  }
  pendingEditorNavigationUrl = null;
  pendingTilesetNavigationId = tilesetId;
  renderTilesetSelector();
  byId("unsaved-navigation-message").textContent = "変更を保存してからタイルセットを切り替えますか？";
  byId("unsaved-navigation-dialog").showModal();
  byId("unsaved-navigation-dialog").querySelector('[data-navigation-choice="save"]').focus();
}

function closeNavigationDialog() {
  pendingEditorNavigationUrl = null;
  pendingTilesetNavigationId = null;
  byId("unsaved-navigation-dialog").close();
}

async function handleNavigationChoice(choice) {
  if (navigationBusy) return;
  const url = pendingEditorNavigationUrl;
  const tilesetId = pendingTilesetNavigationId;
  if ((!url && !tilesetId) || choice === "cancel") {
    closeNavigationDialog();
    return;
  }
  if (choice !== "save" && choice !== "discard") return;
  const buttons = byId("unsaved-navigation-dialog").querySelectorAll("button");
  navigationBusy = true;
  buttons.forEach((button) => { button.disabled = true; });
  try {
    if (choice === "save" && !await save()) return;
    if (url !== pendingEditorNavigationUrl || tilesetId !== pendingTilesetNavigationId) return;
    if (tilesetId) {
      if (await switchTilesetDocument(tilesetId)) closeNavigationDialog();
    } else {
      state.dirty = false;
      window.location.assign(url);
    }
  } finally {
    navigationBusy = false;
    buttons.forEach((button) => { button.disabled = false; });
  }
}

function syncPreviewControls() {
  byId("preview-collision").checked = state.previewShowCollision;
  byId("preview-pause").textContent = state.previewPaused ? "再生" : "一時停止";
}

async function renewSessionToken() {
  try {
    const response = await fetch(editorApiPath("/api/session-token"), {
      cache: "no-store",
      headers: { "X-Mapchip-Client": SESSION_CLIENT_HEADER },
    });
    if (!response.ok) return false;
    const value = await response.json();
    if (typeof value.token !== "string" || !value.token) return false;
    token = value.token;
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.set("token", token);
    window.history.replaceState(null, "", currentUrl);
    configureEditorNavigation();
    return true;
  } catch (_error) {
    return false;
  }
}

async function api(path, options = {}, retryAuthentication = true) {
  const response = await fetch(editorApiPath(path), {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Mapchip-Token": token,
      ...(options.headers || {}),
    },
  });
  if (response.status === 403 && retryAuthentication && await renewSessionToken()) {
    return api(path, options, false);
  }
  const value = await response.json();
  if (!response.ok) {
    const message = response.status === 403
      ? "認証セッションを更新できませんでした。ツールを再起動し、新しく開いた画面を使用してください。"
      : value.error || `HTTP ${response.status}`;
    throw new Error(message);
  }
  return value;
}

function currentTilesetCatalogRecord() {
  return state.tilesetCatalog.find((item) => item.tileset_id === state.data?.tileset_id) || null;
}

function renderTilesetSelector() {
  const select = byId("tileset-select");
  const records = [...state.tilesetCatalog];
  if (state.data && !records.some((item) => item.tileset_id === state.data.tileset_id)) {
    records.push({
      tileset_id: state.data.tileset_id,
      source_image_id: state.data.source_image_id,
      profile: state.data.profile,
      base_ground_id: state.data.grounds[0]?.id,
      map_ids: [],
      is_new: true,
    });
  }
  records.sort((left, right) => left.tileset_id.localeCompare(right.tileset_id));
  select.innerHTML = records.map((item) => `<option value="${escapeHtml(item.tileset_id)}" ${item.tileset_id === state.data?.tileset_id ? "selected" : ""}>${escapeHtml(item.tileset_id)} — ${escapeHtml(item.profile)} / ${escapeHtml(item.source_image_id)}${item.is_new ? "（未保存）" : ""}</option>`).join("");
  select.disabled = records.length === 0;
  const record = currentTilesetCatalogRecord();
  byId("delete-tileset-button").disabled = !record || state.data?.tileset_id === "worldmap";
}

function loadLastTilesetId() {
  try {
    return window.localStorage.getItem(LAST_TILESET_STORAGE_KEY) || null;
  } catch (_error) {
    return null;
  }
}

function saveLastTilesetId(tilesetId = state.data?.tileset_id) {
  if (!tilesetId || !state.tilesetCatalog.some((item) => item.tileset_id === tilesetId)) return;
  try {
    window.localStorage.setItem(LAST_TILESET_STORAGE_KEY, tilesetId);
  } catch (_error) {}
}

function sourceImageOptions(selected = "") {
  return state.sourceImages.map((item) => `<option value="${escapeHtml(item.image_id)}" ${item.image_id === selected ? "selected" : ""}>${escapeHtml(item.file_name)}</option>`).join("");
}

function applyDocumentPayload(payload) {
  window.clearTimeout(state.validateTimer);
  state.data = payload.data;
  state.imageInfo = payload.image_info;
  state.imageUrl = payload.image_url;
  state.diagnostics = payload.diagnostics;
  state.dirty = Boolean(payload.is_new);
  state.history = [];
  state.future = [];
  state.objectOrigins = (state.data.objects || []).map((object) => payload.is_new ? null : object.id);
  state.groundIndex = 0;
  state.boundaryIndex = 0;
  state.objectIndex = 0;
  state.choiceIndex = 0;
  state.frameIndex = 0;
  state.selection = { x: 0, y: 0, width: 1, height: 1 };
  const fallback = state.data.grounds.some((ground) => ground.id === "plain") ? "plain" : state.data.grounds[0]?.id;
  state.previewGrounds = Array(9).fill(fallback);
  if (state.data.grounds.some((ground) => ground.id === "sand")) state.previewGrounds[4] = "sand";
  restorePreviewSettings();
  byId("image-summary").textContent = `${state.imageInfo.width}×${state.imageInfo.height}px · ${state.imageInfo.columns}×${state.imageInfo.rows} cells · 16px · ${state.data.source_image_id}`;
  rawImage.onload = prepareProcessedImage;
  rawImage.onerror = () => showToast("ソース画像を表示できません。", true);
  rawImage.src = `${editorApiPath(state.imageUrl)}&revision=${Date.now()}`;
  const url = new URL(window.location.href);
  url.searchParams.set("tileset", state.data.tileset_id);
  window.history.replaceState(null, "", url);
  saveLastTilesetId();
  renderTilesetSelector();
  configureEditorNavigation();
  renderAll();
  savePreviewSettings();
  updateSaveState(payload.is_new ? "dirty" : "saved", payload.is_new ? "未保存" : "保存済み");
}

async function loadTilesetDocument(tilesetId) {
  const payload = await api(`/api/document?tileset=${encodeURIComponent(tilesetId)}`);
  applyDocumentPayload(payload);
}

async function refreshCatalog() {
  const catalog = await api("/api/catalog");
  state.tilesetCatalog = catalog.tilesets || [];
  state.sourceImages = catalog.source_images || [];
  renderTilesetSelector();
}

function showToast(message, error = false) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.classList.toggle("error", error);
  toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("visible"), 2400);
}

function canSave() {
  return Boolean(state.data) && (state.dirty || state.diagnostics.some((issue) => issue.severity === "error"));
}

function updateSaveState(kind = null, text = null) {
  const element = byId("save-state");
  const hasErrors = state.diagnostics.some((issue) => issue.severity === "error");
  element.className = "status-pill";
  if (kind) element.classList.add(kind);
  else if (hasErrors) element.classList.add("error");
  else if (state.dirty) element.classList.add("dirty");
  else element.classList.add("saved");
  element.textContent = text || (hasErrors
    ? state.dirty ? "未保存・エラー" : "保存済み・エラー"
    : state.dirty ? "未保存" : "保存済み");
  byId("undo-button").disabled = state.history.length === 0;
  byId("redo-button").disabled = state.future.length === 0;
  byId("save-button").disabled = !canSave();
}

function commit(mutator) {
  state.history.push(JSON.stringify({ data: state.data, objectOrigins: state.objectOrigins }));
  if (state.history.length > 100) state.history.shift();
  state.future = [];
  mutator();
  state.dirty = true;
  normalizeSelectionIndexes();
  renderAll();
  savePreviewSettings();
  scheduleValidation();
}

function undo() {
  if (!state.history.length) return;
  const selectedObject = currentObject();
  state.future.push(JSON.stringify({ data: state.data, objectOrigins: state.objectOrigins }));
  const previous = JSON.parse(state.history.pop());
  state.data = previous.data;
  state.objectOrigins = previous.objectOrigins;
  syncRestoredObjectLayer(selectedObject);
  state.dirty = true;
  normalizeSelectionIndexes();
  renderAll();
  savePreviewSettings();
  scheduleValidation();
}

function redo() {
  if (!state.future.length) return;
  const selectedObject = currentObject();
  state.history.push(JSON.stringify({ data: state.data, objectOrigins: state.objectOrigins }));
  const next = JSON.parse(state.future.pop());
  state.data = next.data;
  state.objectOrigins = next.objectOrigins;
  syncRestoredObjectLayer(selectedObject);
  state.dirty = true;
  normalizeSelectionIndexes();
  renderAll();
  savePreviewSettings();
  scheduleValidation();
}

function syncRestoredObjectLayer(selectedObject) {
  const restoredObject = state.data.objects?.[state.objectIndex];
  if (selectedObject && restoredObject?.id === selectedObject.id
      && restoredObject.default_draw_group !== selectedObject.default_draw_group) {
    state.objectLayer = restoredObject.default_draw_group;
  }
}

function normalizeSelectionIndexes() {
  const grounds = state.data?.grounds || [];
  const objects = state.data?.objects || [];
  state.groundIndex = Math.max(0, Math.min(state.groundIndex, grounds.length - 1));
  const boundaries = grounds[state.groundIndex]?.boundaries || [];
  state.boundaryIndex = Math.max(0, Math.min(state.boundaryIndex, boundaries.length - 1));
  const objectIndex = objects[state.objectIndex]?.default_draw_group === state.objectLayer
    ? state.objectIndex : objects.findIndex((object) => object.default_draw_group === state.objectLayer);
  if (state.objectIndex !== objectIndex) {
    state.objectIndex = objectIndex;
    if (state.tab === "object") {
      state.choiceIndex = 0;
      state.frameIndex = 0;
    }
  }
  const visual = activeVisual();
  state.choiceIndex = Math.max(0, Math.min(state.choiceIndex, (visual?.choices?.length || 1) - 1));
  const frames = visual?.choices?.[state.choiceIndex]?.frames || [];
  state.frameIndex = Math.max(0, Math.min(state.frameIndex, Math.max(0, frames.length - 1)));

  const groundIds = grounds.map((ground) => ground.id);
  const fallback = groundIds.includes("plain") ? "plain" : groundIds[0];
  if (state.previewGrounds.length !== 9) state.previewGrounds = Array(9).fill(fallback);
  state.previewGrounds = state.previewGrounds.map((id) => groundIds.includes(id) ? id : fallback);
}

function currentGround() {
  return state.data?.grounds?.[state.groundIndex] || null;
}

function currentBoundary() {
  return currentGround()?.boundaries?.[state.boundaryIndex] || null;
}

function currentObject() {
  return state.data?.objects?.[state.objectIndex] || null;
}

function currentVisual() {
  if (state.tab === "boundary") return currentBoundary()?.visual || null;
  if (state.tab === "ground") return currentGround()?.base_visual || null;
  return null;
}

function objectDisplayCells(object = currentObject()) {
  return (object?.cells || []).filter((cell) => cell.tile || cell.visual);
}

function currentObjectVisual() {
  const cell = objectDisplayCells()[0];
  if (!cell) return null;
  return cell.visual || singleTileVisual(cell.tile);
}

function activeVisual() {
  return state.tab === "object" ? currentObjectVisual() : currentVisual();
}

function normalizeObjectVisuals(object = currentObject()) {
  for (const cell of objectDisplayCells(object)) {
    if (cell.visual) continue;
    cell.visual = singleTileVisual(cell.tile);
    delete cell.tile;
  }
}

function objectSelectionMatches(object = currentObject()) {
  return Boolean(
    object
    && state.selection.width === object.size[0]
    && state.selection.height === object.size[1]
  );
}

function selectedObjectTile(cell) {
  return [
    state.selection.x + cell.offset[0],
    state.selection.y + cell.offset[1],
  ];
}

function uniqueId(base, items) {
  const used = new Set(items.map((item) => item.id));
  if (!used.has(base)) return base;
  let suffix = 2;
  while (used.has(`${base}_${suffix}`)) suffix += 1;
  return `${base}_${suffix}`;
}

function singleTileVisual(tile = null) {
  const selected = tile || [state.selection.x, state.selection.y];
  return {
    frame_interval: 1,
    choices: [{ id: "default", weight: 1, frames: [{ tile: [...selected] }] }],
  };
}

function prepareProcessedImage() {
  if (!rawImage.complete || !rawImage.naturalWidth) return;
  processedImage.width = rawImage.naturalWidth;
  processedImage.height = rawImage.naturalHeight;
  const context = processedImage.getContext("2d", { willReadFrequently: true });
  context.clearRect(0, 0, processedImage.width, processedImage.height);
  context.drawImage(rawImage, 0, 0);
  const pixels = context.getImageData(0, 0, processedImage.width, processedImage.height);
  for (let index = 0; index < pixels.data.length; index += 4) {
    if (pixels.data[index] === 255 && pixels.data[index + 1] === 0 && pixels.data[index + 2] === 128) {
      pixels.data[index + 3] = 0;
    }
  }
  context.putImageData(pixels, 0, 0);
  processedImageUrl = processedImage.toDataURL("image/png");
  drawSource();
  renderEditor();
  renderPreview();
}

function addVisualUsage(usage, visual, category) {
  for (const choice of visual?.choices || []) {
    for (const frame of choice?.frames || []) {
      const tile = frame?.tile;
      if (!Array.isArray(tile) || tile.length !== 2) continue;
      const key = tile.join(",");
      if (!usage.has(key)) usage.set(key, new Set());
      usage.get(key).add(category);
    }
  }
}

function sourceTileUsage() {
  const usage = new Map();
  for (const ground of state.data?.grounds || []) {
    addVisualUsage(usage, ground.base_visual, "ground");
    for (const boundary of ground.boundaries || []) addVisualUsage(usage, boundary.visual, "boundary");
  }
  for (const object of state.data?.objects || []) {
    const layer = OBJECT_LAYER_CLASSES[object.default_draw_group] ? object.default_draw_group : "object_y_sorted";
    for (const cell of object.cells || []) {
      if (Array.isArray(cell.tile)) {
        const key = cell.tile.join(",");
        if (!usage.has(key)) usage.set(key, new Set());
        usage.get(key).add(layer);
      }
      addVisualUsage(usage, cell.visual, layer);
    }
  }
  return usage;
}

function drawSourceUsage(context, zoom) {
  const usage = sourceTileUsage();
  const styles = getComputedStyle(document.documentElement);
  const categories = SOURCE_USAGE_COLORS.map(([category, variable]) => [category, styles.getPropertyValue(variable).trim()]);
  let usedCount = 0;
  for (let row = 0; row < state.imageInfo.rows; row += 1) {
    for (let column = 0; column < state.imageInfo.columns; column += 1) {
      const x = column * 16 * zoom;
      const y = row * 16 * zoom;
      const categoriesUsed = usage.get(`${column},${row}`);
      if (!categoriesUsed?.size) {
        context.fillStyle = "rgba(8,10,7,.52)";
        context.fillRect(x, y, 16 * zoom, 16 * zoom);
        continue;
      }
      usedCount += 1;
      context.fillStyle = "rgba(255,255,255,.05)";
      context.fillRect(x, y, 16 * zoom, 16 * zoom);
      let markerIndex = 0;
      for (const [category, color] of categories) {
        if (!categoriesUsed.has(category)) continue;
        context.fillStyle = color;
        context.fillRect(x + (markerIndex % 3) * 4 * zoom + zoom, y + Math.floor(markerIndex / 3) * 4 * zoom + zoom, 3 * zoom, 3 * zoom);
        markerIndex += 1;
      }
    }
  }
  const summary = byId("usage-summary");
  if (summary) summary.textContent = `使用 ${usedCount} / 未使用 ${state.imageInfo.columns * state.imageInfo.rows - usedCount}`;
}

function drawSource() {
  if (!state.imageInfo || !processedImage.width) return;
  const canvas = byId("source-canvas");
  const zoom = state.zoom;
  canvas.width = state.imageInfo.width * zoom;
  canvas.height = state.imageInfo.height * zoom;
  const context = canvas.getContext("2d");
  context.imageSmoothingEnabled = false;
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.drawImage(processedImage, 0, 0, canvas.width, canvas.height);
  drawSourceUsage(context, zoom);

  context.lineWidth = 1;
  context.strokeStyle = "rgba(238, 233, 215, .34)";
  context.beginPath();
  for (let column = 0; column <= state.imageInfo.columns; column += 1) {
    const x = column * 16 * zoom + .5;
    context.moveTo(x, 0);
    context.lineTo(x, state.imageInfo.rows * 16 * zoom);
  }
  for (let row = 0; row <= state.imageInfo.rows; row += 1) {
    const y = row * 16 * zoom + .5;
    context.moveTo(0, y);
    context.lineTo(state.imageInfo.columns * 16 * zoom, y);
  }
  context.stroke();

  const selection = state.selection;
  context.lineWidth = 3;
  context.strokeStyle = "#ff4fa3";
  context.fillStyle = "rgba(255, 79, 163, .14)";
  const x = selection.x * 16 * zoom;
  const y = selection.y * 16 * zoom;
  const width = selection.width * 16 * zoom;
  const height = selection.height * 16 * zoom;
  context.fillRect(x, y, width, height);
  context.strokeRect(x + 1.5, y + 1.5, width - 3, height - 3);
  byId("selection-label").textContent = `[${selection.x}, ${selection.y}] ${selection.width}×${selection.height}`;
  byId("zoom-label").textContent = `${zoom}×`;
}

function tileFromPointer(event) {
  const rect = byId("source-canvas").getBoundingClientRect();
  const x = Math.floor((event.clientX - rect.left) / (16 * state.zoom));
  const y = Math.floor((event.clientY - rect.top) / (16 * state.zoom));
  return {
    x: Math.max(0, Math.min(x, state.imageInfo.columns - 1)),
    y: Math.max(0, Math.min(y, state.imageInfo.rows - 1)),
  };
}

function updateDragSelection(current) {
  const start = state.dragStart;
  if (!start) return;
  state.selection = {
    x: Math.min(start.x, current.x),
    y: Math.min(start.y, current.y),
    width: Math.abs(start.x - current.x) + 1,
    height: Math.abs(start.y - current.y) + 1,
  };
  drawSource();
}

function tileThumbImage(tile) {
  const [column, row] = tile || [0, 0];
  const scale = 2;
  const style = processedImageUrl
    ? `background-image:url('${processedImageUrl}');background-size:${state.imageInfo.width * scale}px ${state.imageInfo.height * scale}px;background-position:${-column * 16 * scale}px ${-row * 16 * scale}px`
    : "";
  return `<span class="tile-thumb" style="${style}"></span>`;
}

function tileThumb(tile) {
  const [column, row] = tile || [0, 0];
  return `${tileThumbImage(tile)}<span>${column},${row}</span>`;
}

function objectFrameTiles(object, choiceIndex, frameIndex) {
  const byOffset = new Map();
  for (const cell of objectDisplayCells(object)) {
    let tile = cell.tile || null;
    if (cell.visual) {
      const choice = cell.visual.choices?.[choiceIndex];
      const frames = choice?.frames || [];
      tile = frames.length ? frames[frameIndex % frames.length]?.tile : null;
    }
    byOffset.set(cell.offset.join(","), tile);
  }
  const tiles = [];
  for (let y = 0; y < object.size[1]; y += 1) {
    for (let x = 0; x < object.size[0]; x += 1) {
      tiles.push(byOffset.get(`${x},${y}`) || null);
    }
  }
  return tiles;
}

function centerSourceSelection() {
  const scroll = byId("source-scroll");
  const scale = 16 * state.zoom;
  scroll.scrollLeft = state.selection.x * scale + state.selection.width * scale / 2 - scroll.clientWidth / 2;
  scroll.scrollTop = state.selection.y * scale + state.selection.height * scale / 2 - scroll.clientHeight / 2;
}

function focusVisualFrameInSource(element) {
  const visual = currentVisual();
  const choiceIndex = Number(element.dataset.choice);
  const frameIndex = Number(element.dataset.frame);
  const tile = visual?.choices?.[choiceIndex]?.frames?.[frameIndex]?.tile;
  if (!tile) return;
  state.choiceIndex = choiceIndex;
  state.frameIndex = frameIndex;
  state.selection = { x: tile[0], y: tile[1], width: 1, height: 1 };
  drawSource();
  renderEditor();
  centerSourceSelection();
}

function focusObjectFrameInSource(element) {
  const object = currentObject();
  if (!object) return;
  const choiceIndex = Number(element.dataset.choice);
  const frameIndex = Number(element.dataset.frame);
  const tiles = objectFrameTiles(object, choiceIndex, frameIndex);
  const tileIndex = tiles.findIndex(Boolean);
  if (tileIndex < 0) return;
  const tile = tiles[tileIndex];
  const offsetX = tileIndex % object.size[0];
  const offsetY = Math.floor(tileIndex / object.size[0]);
  state.choiceIndex = choiceIndex;
  state.frameIndex = frameIndex;
  state.selection = {
    x: tile[0] - offsetX,
    y: tile[1] - offsetY,
    width: object.size[0],
    height: object.size[1],
  };
  drawSource();
  renderEditor();
  centerSourceSelection();
}

function objectFrameThumb(object, choiceIndex, frameIndex) {
  return `<span class="object-frame-thumb" style="--object-columns:${object.size[0]}">
    ${objectFrameTiles(object, choiceIndex, frameIndex).map((tile) => tile ? tileThumbImage(tile) : `<span class="tile-thumb empty"></span>`).join("")}
  </span>`;
}

function objectLayerClass(object) {
  return OBJECT_LAYER_CLASSES[object?.default_draw_group] || OBJECT_LAYER_CLASSES.object_y_sorted;
}

function renderDefinitionList(items, activeIndex, action, addAction, addLabel, reorderKind, baseIndex = null) {
  const chips = items.map((item, index) => {
    if (reorderKind === "object" && item.default_draw_group !== state.objectLayer) return "";
    const layerClass = reorderKind === "object" ? `map-layer ${objectLayerClass(item)}` : "";
    return `
    <button type="button" class="definition-chip ${layerClass} ${index === activeIndex ? "active" : ""} ${index === baseIndex ? "" : "reorderable"}"
      data-action="${action}" data-index="${index}" data-reorder-kind="${reorderKind}"
      title="${index === baseIndex ? "ベース地面は先頭固定です" : "ドラッグで表示順を変更"}">${escapeHtml(item.id || `#${index + 1}`)}${index === baseIndex ? " · ベース" : ""}</button>
  `;
  }).join("");
  return `<div class="definition-list">${chips}<button type="button" class="definition-chip" data-action="${addAction}">＋ ${addLabel}</button></div>`;
}

function clearDefinitionDropIndicators() {
  byId("editor-content").querySelectorAll(".definition-chip.drop-before, .definition-chip.drop-after")
    .forEach((chip) => chip.classList.remove("drop-before", "drop-after"));
}

function reorderDefinitions(kind, fromIndex, insertionIndex) {
  const items = kind === "ground" ? state.data.grounds : state.data.objects;
  const minimumIndex = kind === "ground" ? 1 : 0;
  if (!items || fromIndex < minimumIndex || fromIndex >= items.length) return;
  const clampedInsertion = Math.max(minimumIndex, Math.min(insertionIndex, items.length));
  const destinationIndex = clampedInsertion > fromIndex ? clampedInsertion - 1 : clampedInsertion;
  if (destinationIndex === fromIndex) return;
  const activeItem = kind === "ground" ? currentGround() : currentObject();
  const movedLabel = items[fromIndex].id;
  commit(() => {
    const [item] = items.splice(fromIndex, 1);
    items.splice(destinationIndex, 0, item);
    if (kind === "object") {
      const [origin] = state.objectOrigins.splice(fromIndex, 1);
      state.objectOrigins.splice(destinationIndex, 0, origin);
      state.objectIndex = items.indexOf(activeItem);
    } else {
      state.groundIndex = items.indexOf(activeItem);
      state.boundaryIndex = 0;
    }
  });
  showToast(`${movedLabel} の表示順を変更しました。`);
}

function updateDefinitionDropTarget(event) {
  const drag = state.definitionDrag;
  if (!drag) return;
  const chip = document.elementFromPoint(event.clientX, event.clientY)?.closest(".definition-chip[data-reorder-kind]");
  if (!chip || chip.dataset.reorderKind !== drag.kind) {
    clearDefinitionDropIndicators();
    return;
  }
  const rect = chip.getBoundingClientRect();
  let after = event.clientX >= rect.left + rect.width / 2;
  if (drag.kind === "ground" && Number(chip.dataset.index) === 0) after = true;
  let insertionIndex = Number(chip.dataset.index) + (after ? 1 : 0);
  if (drag.kind === "ground") insertionIndex = Math.max(1, insertionIndex);
  drag.insertionIndex = insertionIndex;
  clearDefinitionDropIndicators();
  chip.classList.add(after ? "drop-after" : "drop-before");
}

function handleDefinitionPointerDown(event) {
  if (event.button !== 0) return;
  const chip = event.target.closest(".definition-chip.reorderable[data-reorder-kind]");
  if (!chip) return;
  const fromIndex = Number(chip.dataset.index);
  if (!Number.isInteger(fromIndex)) return;
  state.definitionDrag = {
    kind: chip.dataset.reorderKind,
    fromIndex,
    insertionIndex: fromIndex,
    startX: event.clientX,
    startY: event.clientY,
    pointerId: event.pointerId,
    active: false,
    chip,
  };
  chip.setPointerCapture(event.pointerId);
}

function handleDefinitionPointerMove(event) {
  const drag = state.definitionDrag;
  if (!drag || drag.pointerId !== event.pointerId) return;
  if (!drag.active && Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) < 5) return;
  event.preventDefault();
  if (!drag.active) {
    drag.active = true;
    drag.chip.classList.add("dragging");
    state.suppressDefinitionClickUntil = performance.now() + 250;
  }
  updateDefinitionDropTarget(event);
}

function finishDefinitionPointerDrag(event, cancelled = false) {
  const drag = state.definitionDrag;
  if (!drag || drag.pointerId !== event.pointerId) return;
  if (drag.chip.hasPointerCapture(event.pointerId)) drag.chip.releasePointerCapture(event.pointerId);
  state.definitionDrag = null;
  if (drag.active) state.suppressDefinitionClickUntil = performance.now() + 250;
  clearDefinitionDropIndicators();
  drag.chip.classList.remove("dragging");
  if (drag.active && !cancelled) reorderDefinitions(drag.kind, drag.fromIndex, drag.insertionIndex);
}

function renderBoundaryRuleList(items) {
  const rules = items.map((item, index) => `
    <button type="button" role="tab" aria-selected="${index === state.boundaryIndex}" aria-label="境界ルール ${index + 1}"
      class="boundary-rule-tab ${index === state.boundaryIndex ? "active" : ""}"
      data-action="select-boundary" data-index="${index}" title="優先順位 ${index + 1}">
      <span class="boundary-tab-number">${index + 1}</span>
      ${tileThumbImage(item.visual?.choices?.[0]?.frames?.[0]?.tile)}
    </button>
  `).join("");
  return `<div class="boundary-rule-tabs" role="tablist" aria-label="境界ルール（左ほど優先）">${rules}<button type="button" class="boundary-rule-add" data-action="add-boundary" aria-label="境界ルールを追加">＋</button></div>`;
}

function renderVisualEditor(visual) {
  if (!visual) return `<div class="empty-state">表示定義がありません。</div>`;
  const choices = visual.choices || [];
  return `
    <div class="form-grid">
      <div class="field">
        <label>フレーム間隔（60fps）</label>
        <input type="number" min="1" value="${escapeHtml(visual.frame_interval)}" data-change="visual-interval">
      </div>
      <div class="field">
        <label>現在のソース選択</label>
        <div class="row"><code>${state.selection.x}, ${state.selection.y}</code></div>
      </div>
    </div>
    <div class="frame-help">チップをクリックすると、現在のソース選択で置き換えます。</div>
    ${choices.map((choice, choiceIndex) => `
      <div class="choice-card ${choiceIndex === state.choiceIndex ? "active" : ""}">
        <div class="choice-head">
          <span class="choice-number">表示候補 ${choiceIndex + 1}</span>
          <div class="field"><label>重み</label><input type="number" min="0" value="${escapeHtml(choice.weight)}" data-change="choice-weight" data-choice="${choiceIndex}"></div>
          <button type="button" class="button danger small" data-action="delete-choice" data-choice="${choiceIndex}" ${choices.length <= 1 ? "disabled" : ""}>削除</button>
        </div>
        <div class="frames">
          ${(choice.frames || []).map((frame, frameIndex) => `
            <button type="button" class="frame-button ${choiceIndex === state.choiceIndex && frameIndex === state.frameIndex ? "active" : ""}"
              data-action="set-frame-tile" data-choice="${choiceIndex}" data-frame="${frameIndex}"
              title="左: 現在のソース選択で置き換える・右: ソース画像で表示" aria-label="表示候補 ${choiceIndex + 1} のフレーム ${frameIndex + 1}。左クリックで現在のソース選択に置き換え、右クリックでソース画像に表示">
              ${tileThumb(frame.tile)}
            </button>`).join("")}
          <button type="button" class="frame-button" data-action="add-frame" data-choice="${choiceIndex}">＋<span>frame</span></button>
        </div>
      </div>`).join("")}
    <div class="row between" style="margin-top:9px">
      <button type="button" class="button ghost small" data-action="add-choice">＋ 表示候補</button>
      <button type="button" class="button danger small" data-action="delete-frame">フレーム削除</button>
    </div>`;
}

function renderGroundEditor() {
  const grounds = state.data.grounds || [];
  const ground = currentGround();
  if (!ground) return `<div class="empty-state">地面定義がありません。</div>`;
  return `
    <div class="section">
      <div class="section-title"><h3>地面定義</h3><span class="subtle">最上位地面を1セルに保存</span></div>
      ${renderDefinitionList(grounds, state.groundIndex, "select-ground", "add-ground", "地面", "ground", 0)}
      <div class="divider"></div>
      <div class="form-grid">
        <div class="field"><label>地面ID${state.groundIndex === 0 ? "（ベース・変更不可）" : ""}</label><input type="text" value="${escapeHtml(ground.id)}" data-change="ground-id" ${state.groundIndex === 0 ? "disabled" : ""}></div>
        <div class="field"><label>描画上の親${state.groundIndex === 0 ? "（ベースは設定不可）" : ""}</label><select data-change="ground-parent" ${state.groundIndex === 0 ? "disabled" : ""}>
          <option value="">なし</option>
          ${grounds.map((candidate, index) => index === state.groundIndex ? "" : `<option value="${escapeHtml(candidate.id)}" ${ground.parent_id === candidate.id ? "selected" : ""}>${escapeHtml(candidate.id)}</option>`).join("")}
        </select></div>
        <div class="field"><label>通行</label><select data-change="ground-collision"><option value="passable" ${ground.collision === "passable" ? "selected" : ""}>通行可</option><option value="blocked" ${ground.collision === "blocked" ? "selected" : ""}>通行不可</option></select></div>
        <div class="field"><label>境界ルール数</label><input type="text" value="${ground.boundaries.length}" disabled></div>
      </div>
      <div class="row end" style="margin-top:10px"><button type="button" class="button danger small" data-action="delete-ground" ${grounds.length <= 1 || state.groundIndex === 0 ? "disabled" : ""}>地面を削除</button></div>
    </div>
    <div class="section">
      <div class="section-title"><h3>通常表示</h3><span class="subtle">境界ルールに一致しない場合</span></div>
      ${renderVisualEditor(ground.base_visual)}
    </div>`;
}

function renderBoundaryEditor() {
  const grounds = state.data.grounds || [];
  const ground = currentGround();
  const boundaries = ground?.boundaries || [];
  const rule = currentBoundary();
  return `
    <div class="section">
      <div class="section-title"><h3>対象地面</h3><span class="subtle">親を含むかでsame判定</span></div>
      ${renderDefinitionList(grounds, state.groundIndex, "select-ground", "add-ground", "地面", "ground", 0)}
    </div>
    <div class="section">
      <div class="section-title"><h3>境界ルール</h3><span class="subtle">左から順に最初の一致を採用</span></div>
      ${renderBoundaryRuleList(boundaries)}
      ${rule ? `
        <div class="divider"></div>
        <div class="neighbor-grid">
          ${DIRECTIONS.map((direction) => direction === "center"
            ? `<button type="button" class="neighbor-cell center" disabled>${escapeHtml(ground.id)}</button>`
            : `<button type="button" class="neighbor-cell ${rule.neighbors[direction]}" data-action="cycle-neighbor" data-direction="${direction}">${direction}<br>${rule.neighbors[direction]}</button>`
          ).join("")}
        </div>
        <div class="row between" style="margin-top:10px">
          <div class="row">
            <button type="button" class="button ghost small" data-action="move-boundary-left" ${state.boundaryIndex <= 0 ? "disabled" : ""}>← 左へ</button>
            <button type="button" class="button ghost small" data-action="move-boundary-right" ${state.boundaryIndex >= boundaries.length - 1 ? "disabled" : ""}>右へ →</button>
          </div>
          <button type="button" class="button danger small" data-action="delete-boundary">ルールを削除</button>
        </div>
      ` : `<div class="empty-state" style="margin-top:10px">境界ルールを追加してください。</div>`}
    </div>
    ${rule ? `<div class="section"><div class="section-title"><h3>境界表示</h3></div>${renderVisualEditor(rule.visual)}</div>` : ""}`;
}

function renderObjectVisualEditor(object) {
  const visual = currentObjectVisual();
  if (!visual) return `<div class="empty-state">表示を持つ構成セルがありません。</div>`;
  const choices = visual.choices || [];
  const selectionMatches = objectSelectionMatches(object);
  const selectionLabel = `[${state.selection.x}, ${state.selection.y}] ${state.selection.width}×${state.selection.height}`;
  return `
    <div class="form-grid">
      <div class="field">
        <label>フレーム間隔（60fps）</label>
        <input type="number" min="1" value="${escapeHtml(visual.frame_interval)}" data-change="object-visual-interval">
      </div>
      <div class="field">
        <label>現在のソース選択</label>
        <div class="row"><code>${selectionLabel}</code></div>
      </div>
    </div>
    <div class="frame-help ${selectionMatches ? "" : "error-text"}">候補の追加・置換には、オブジェクトと同じ ${object.size[0]}×${object.size[1]} の矩形を選択してください。</div>
    ${choices.map((choice, choiceIndex) => `
      <div class="choice-card ${choiceIndex === state.choiceIndex ? "active" : ""}">
        <div class="choice-head">
          <span class="choice-number">表示候補 ${choiceIndex + 1}</span>
          <div class="field"><label>重み</label><input type="number" min="0" value="${escapeHtml(choice.weight)}" data-change="object-choice-weight" data-choice="${choiceIndex}"></div>
          <button type="button" class="button danger small" data-action="object-delete-choice" data-choice="${choiceIndex}" ${choices.length <= 1 ? "disabled" : ""}>削除</button>
        </div>
        <div class="frames object-frames">
          ${(choice.frames || []).map((_frame, frameIndex) => `
            <button type="button" class="object-frame-button ${choiceIndex === state.choiceIndex && frameIndex === state.frameIndex ? "active" : ""}"
              data-action="object-set-frame" data-choice="${choiceIndex}" data-frame="${frameIndex}"
              title="左: 現在の同寸法の矩形で置き換える・右: ソース画像で表示" aria-label="表示候補 ${choiceIndex + 1} のフレーム ${frameIndex + 1}。左クリックで現在の矩形選択に置き換え、右クリックでソース画像に表示">
              ${objectFrameThumb(object, choiceIndex, frameIndex)}
              <span>frame ${frameIndex + 1}</span>
            </button>`).join("")}
          <button type="button" class="object-frame-button add" data-action="object-add-frame" data-choice="${choiceIndex}" ${selectionMatches ? "" : "disabled"}>＋<span>frame</span></button>
        </div>
      </div>`).join("")}
    <div class="row between" style="margin-top:9px">
      <button type="button" class="button ghost small" data-action="object-add-choice" ${selectionMatches ? "" : "disabled"}>＋ 表示候補</button>
      <button type="button" class="button danger small" data-action="object-delete-frame">フレーム削除</button>
    </div>`;
}

function renderObjectLayerSelect() {
  const layer = state.objectLayer;
  return `<fieldset class="object-layer-options"><legend>レイヤー</legend>
    ${OBJECT_LAYERS.map(([value, text]) => `<label class="layer-option map-layer ${OBJECT_LAYER_CLASSES[value]} ${value === layer ? "selected" : ""}">
      <input type="radio" name="object-layer" data-change="object-layer" value="${value}" ${value === layer ? "checked" : ""}>${text}
    </label>`).join("")}
  </fieldset>`;
}

function renderObjectEditor() {
  const objects = state.data.objects || [];
  const object = currentObject();
  const layerToolbar = `<div class="object-layer-toolbar">
    ${renderObjectLayerSelect()}
  </div>`;
  if (!object) return `
    <div class="section">
      <div class="section-title"><h3>オブジェクト定義</h3></div>
      ${layerToolbar}
      ${renderDefinitionList(objects, state.objectIndex, "select-object", "add-object", "オブジェクト", "object")}
      <div class="empty-state" style="margin-top:10px">このレイヤーのオブジェクト定義がありません。ソース画像を矩形選択してオブジェクトを追加してください。</div>
      <div class="row end" style="margin-top:10px"><button type="button" class="button primary" data-action="object-from-selection">選択矩形から生成</button></div>
    </div>`;

  const [width, height] = object.size;
  const cellsByOffset = new Map(object.cells.map((item) => [item.offset.join(","), item]));
  const grid = [];
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const item = cellsByOffset.get(`${x},${y}`);
      const collision = OBJECT_COLLISION_STATES.includes(item?.collision) ? item.collision : "passable";
      const collisionLabel = OBJECT_COLLISION_LABELS[collision];
      const tileLabel = item?.tile ? item.tile.join(",") : item?.visual ? "visual" : "表示なし";
      grid.push(`<button type="button" class="footprint-cell ${item ? "occupied" : "empty"} ${collision}"
        data-action="toggle-object-cell-collision" data-x="${x}" data-y="${y}"
        aria-label="セル ${x},${y}：${item ? collisionLabel : "構成なし"}"
        title="${item ? `画像 ${tileLabel}・左クリックで可／不可、右クリックで通行可上書き` : "構成セルがありません"}" ${item ? "" : "disabled"}>
        <span>${x},${y}</span><strong>${item ? collisionLabel : "構成なし"}</strong>
      </button>`);
    }
  }
  return `
    <div class="section">
      <div class="section-title"><h3>オブジェクト定義</h3></div>
      ${layerToolbar}
      ${renderDefinitionList(objects, state.objectIndex, "select-object", "add-object", "オブジェクト", "object")}
      <div class="divider"></div>
      <div class="object-identity-grid">
        <div class="field"><label>オブジェクトID</label><input type="text" value="${escapeHtml(object.id)}" data-change="object-id"></div>
        <div class="field"><label>幅</label><input type="number" min="1" value="${width}" data-change="object-width"></div>
        <div class="field"><label>高さ</label><input type="number" min="1" value="${height}" data-change="object-height"></div>
        <div class="field"><label for="object-group">レイヤー変更</label><select id="object-group" data-change="object-group">${OBJECT_LAYERS.map(([value, label]) => `<option value="${value}" ${object.default_draw_group === value ? "selected" : ""}>${label}</option>`).join("")}</select></div>
      </div>
      <label class="object-interact-toggle"><input type="checkbox" data-change="object-interact-through" ${object.interact_through === true ? "checked" : ""}>このオブジェクト越しに1セル先を調べる</label>
      <div class="row between" style="margin-top:10px">
        <button type="button" class="button secondary small" data-action="object-from-selection">選択矩形で置換</button>
        <button type="button" class="button danger small" data-action="delete-object">削除</button>
      </div>
    </div>
    <div class="section">
      <div class="section-title"><h3>構成セル</h3><span class="subtle">左: 可／不可・右: 通行可上書き</span></div>
      <div class="footprint-grid" style="--object-columns:${width}">${grid.join("")}</div>
    </div>
    <div class="section">
      <div class="section-title"><h3>表示</h3><span class="subtle">候補単位で矩形を選択</span></div>
      ${renderObjectVisualEditor(object)}
    </div>`;
}

function renderEditor() {
  if (!state.data) return;
  document.querySelectorAll(".tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === state.tab));
  const content = byId("editor-content");
  if (state.tab === "ground") content.innerHTML = renderGroundEditor();
  else if (state.tab === "boundary") {
    content.innerHTML = renderBoundaryEditor();
    window.requestAnimationFrame(() => {
      const strip = content.querySelector(".boundary-rule-tabs");
      const active = strip?.querySelector(".boundary-rule-tab.active");
      if (!strip || !active) return;
      strip.scrollLeft = Math.max(0, active.offsetLeft - strip.offsetLeft - (strip.clientWidth - active.offsetWidth) / 2);
    });
  }
  else content.innerHTML = renderObjectEditor();
}

function stackFor(groundId) {
  const byGround = new Map(state.data.grounds.map((ground) => [ground.id, ground]));
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

function ruleMatches(rule, neighbors) {
  return Object.entries(rule.neighbors || {}).every(([direction, expected]) => expected === "any" || (expected === "same") === Boolean(neighbors[direction]));
}

function visualForLayer(layer, cellIndex) {
  const cx = cellIndex % 3;
  const cy = Math.floor(cellIndex / 3);
  const neighbors = {};
  const offsets = { n: [0,-1], ne: [1,-1], e: [1,0], se: [1,1], s: [0,1], sw: [-1,1], w: [-1,0], nw: [-1,-1] };
  for (const [direction, [dx, dy]] of Object.entries(offsets)) {
    const x = cx + dx;
    const y = cy + dy;
    if (x < 0 || x >= 3 || y < 0 || y >= 3) {
      // The preview edge represents the visible ground continuing off-canvas.
      // Only relationships configured in the 3×3 controls should create a boundary.
      neighbors[direction] = true;
    } else {
      neighbors[direction] = stackFor(state.previewGrounds[y * 3 + x]).some((ground) => ground.id === layer.id);
    }
  }
  const matching = (layer.boundaries || []).find((rule) => ruleMatches(rule, neighbors));
  return matching?.visual || layer.base_visual;
}

function hashNumber(...parts) {
  let hash = 2166136261;
  for (const character of parts.join("|")) {
    hash ^= character.codePointAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function choiceFor(visual, seed) {
  const choices = (visual?.choices || []).filter((choice) => Number(choice.weight) > 0);
  const total = choices.reduce((sum, choice) => sum + Number(choice.weight), 0);
  if (!total) return null;
  let selected = hashNumber(seed) % total;
  for (const choice of choices) {
    selected -= Number(choice.weight);
    if (selected < 0) return choice;
  }
  return choices[0];
}

function frameFor(visual, choice, now) {
  const frames = choice?.frames || [];
  if (!frames.length) return null;
  if (state.previewPaused) return frames[0];
  const interval = Math.max(1, Number(visual.frame_interval) || 1);
  const frameNumber = Math.floor((now - state.previewStartedAt) / (1000 / 60 * interval));
  return frames[frameNumber % frames.length];
}

function drawTile(context, tile, dx, dy, size) {
  if (!tile || !processedImage.width) return;
  context.imageSmoothingEnabled = false;
  context.drawImage(processedImage, tile[0] * 16, tile[1] * 16, 16, 16, dx, dy, size, size);
}

function drawGroundPreview(now) {
  const canvas = byId("ground-preview-canvas");
  if (!canvas) return;
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  for (let index = 0; index < 9; index += 1) {
    const x = (index % 3) * 48;
    const y = Math.floor(index / 3) * 48;
    for (const layer of stackFor(state.previewGrounds[index])) {
      const visual = visualForLayer(layer, index);
      const choice = choiceFor(visual, `${index}:${layer.id}`);
      const frame = frameFor(visual, choice, now);
      drawTile(context, frame?.tile, x, y, 48);
    }
    const top = state.data.grounds.find((ground) => ground.id === state.previewGrounds[index]);
    if (state.previewShowCollision && top?.collision === "blocked") {
      context.strokeStyle = "rgba(239, 91, 80, .9)";
      context.lineWidth = 3;
      context.strokeRect(x + 1.5, y + 1.5, 45, 45);
    }
  }
}

function drawVisualSample(now) {
  const canvas = byId("visual-preview-canvas");
  const visual = activeVisual();
  if (!canvas || !visual) return;
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  for (let y = 0; y < 4; y += 1) {
    for (let x = 0; x < 8; x += 1) {
      const choice = choiceFor(visual, `${x},${y},sample`);
      const frame = frameFor(visual, choice, now);
      drawTile(context, frame?.tile, x * 32, y * 32, 32);
    }
  }
}

function drawObjectPreview(now) {
  const canvas = byId("object-preview-canvas");
  const object = currentObject();
  if (!canvas || !object) return;
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  const visual = currentObjectVisual();
  const selectedChoice = choiceFor(visual, `${object.id}:object`);
  const selectedChoiceIndex = Math.max(0, (visual?.choices || []).findIndex((choice) => choice.id === selectedChoice?.id));
  const frameCount = selectedChoice?.frames?.length || 1;
  const interval = Math.max(1, Number(visual?.frame_interval) || 1);
  const selectedFrameIndex = state.previewPaused
    ? 0
    : Math.floor((now - state.previewStartedAt) / (1000 / 60 * interval)) % frameCount;
  for (const cell of object.cells) {
    const x = cell.offset[0] * 48;
    const y = cell.offset[1] * 48;
    if (cell.tile) drawTile(context, cell.tile, x, y, 48);
    else if (cell.visual) {
      const choice = cell.visual.choices?.[selectedChoiceIndex];
      const frames = choice?.frames || [];
      const frame = frames.length ? frames[selectedFrameIndex % frames.length] : null;
      drawTile(context, frame?.tile, x, y, 48);
    }
    if (state.previewShowCollision && cell.collision === "blocked") {
      context.strokeStyle = "rgba(239, 91, 80, .9)";
      context.lineWidth = 3;
      context.strokeRect(x + 1.5, y + 1.5, 45, 45);
    } else if (state.previewShowCollision && cell.collision === "passable_override") {
      context.strokeStyle = "rgba(75, 214, 190, .95)";
      context.lineWidth = 3;
      context.strokeRect(x + 1.5, y + 1.5, 45, 45);
    }
  }
}

function renderPreview() {
  if (!state.data) return;
  const container = byId("preview-content");
  const groundButtons = state.previewGrounds.map((groundId, index) => `<button type="button" class="preview-ground-cell" data-action="cycle-preview-ground" data-index="${index}">${escapeHtml(groundId)}</button>`).join("");
  if (state.tab === "object") {
    const object = currentObject();
    const width = Math.max(1, object?.size?.[0] || 1);
    const height = Math.max(1, object?.size?.[1] || 1);
    container.innerHTML = `
      <div class="preview-card"><h3>Object footprint</h3><div class="preview-canvas-wrap"><canvas id="object-preview-canvas" width="${width * 48}" height="${height * 48}"></canvas></div></div>`;
  } else {
    container.innerHTML = `
      <div class="preview-card"><h3>3×3 Ground composition</h3><div class="preview-canvas-wrap"><canvas id="ground-preview-canvas" width="144" height="144"></canvas></div><div class="preview-ground-grid">${groundButtons}</div></div>
      <div class="preview-card"><h3>Random / animation sample</h3><div class="preview-canvas-wrap"><canvas id="visual-preview-canvas" width="256" height="128"></canvas></div></div>`;
  }
  drawPreviews(performance.now());
}

function drawPreviews(now) {
  drawGroundPreview(now);
  drawVisualSample(now);
  drawObjectPreview(now);
}

function animationLoop(now) {
  if (!state.previewPaused) drawPreviews(now);
  requestAnimationFrame(animationLoop);
}

function renderIssues() {
  const issues = byId("issues");
  const errors = state.diagnostics.filter((item) => item.severity === "error").length;
  const warnings = state.diagnostics.filter((item) => item.severity === "warning").length;
  byId("issue-count").textContent = errors ? `${errors} error / ${warnings} warning` : `${warnings} warning`;
  if (!state.diagnostics.length) {
    issues.innerHTML = `<div class="empty-state">問題はありません。</div>`;
  } else {
    issues.innerHTML = state.diagnostics.map((item) => `<div class="issue ${item.severity}"><strong>${escapeHtml(item.path)} · ${escapeHtml(item.code)}</strong><p>${escapeHtml(item.message)}</p></div>`).join("");
  }
  updateSaveState();
}

function renderAll() {
  normalizeSelectionIndexes();
  syncPreviewControls();
  renderEditor();
  renderPreview();
  renderIssues();
  drawSource();
}

async function validate() {
  if (!state.data) return;
  try {
    const result = await api("/api/validate", { method: "POST", body: JSON.stringify({ data: state.data }) });
    state.diagnostics = result.diagnostics;
    if (result.image_info) state.imageInfo = result.image_info;
    renderIssues();
  } catch (error) {
    showToast(error.message, true);
  }
}

function scheduleValidation() {
  window.clearTimeout(state.validateTimer);
  state.validateTimer = window.setTimeout(validate, 280);
  updateSaveState("dirty", "検証中…");
}

async function save() {
  if (!canSave()) return false;
  updateSaveState("dirty", "保存中…");
  try {
    const objectIdRenames = {};
    (state.data.objects || []).forEach((object, index) => {
      const originalId = state.objectOrigins[index];
      if (originalId && originalId !== object.id) objectIdRenames[originalId] = object.id;
    });
    const result = await api("/api/save", { method: "POST", body: JSON.stringify({ data: state.data, object_id_renames: objectIdRenames }) });
    state.diagnostics = result.diagnostics;
    if (result.saved) {
      state.dirty = false;
      state.history = [];
      state.future = [];
      state.objectOrigins = (state.data.objects || []).map((object) => object.id);
      await refreshCatalog();
      saveLastTilesetId();
      const updatedCount = result.updated_map_ids?.length || 0;
      const generatedCount = result.generated_map_ids?.length || 0;
      const removedCount = result.removed_map_object_count || 0;
      const replacedGroundCount = result.replaced_map_ground_count || 0;
      const errorCount = state.diagnostics.filter((item) => item.severity === "error").length;
      const details = [];
      if (updatedCount) details.push(`${updatedCount}件のマップを更新`);
      if (generatedCount) details.push(`${generatedCount}件のゲーム用マップを再生成`);
      if (removedCount) details.push(`配置済みオブジェクト${removedCount}件を削除`);
      if (replacedGroundCount) {
        details.push(`配置済み地面${replacedGroundCount}セルをベース地面へ置換`);
      }
      if (errorCount) details.push(`エラー${errorCount}件を保持`);
      showToast(details.length
        ? `メタデータを保存しました（${details.join("、")}）。`
        : "メタデータを保存しました。");
    } else {
      showToast("エラーを修正してから保存してください。", true);
    }
    renderIssues();
    return Boolean(result.saved);
  } catch (error) {
    updateSaveState("error", "保存失敗");
    showToast(error.message, true);
    return false;
  }
}

function mutateVisual(action, element) {
  const visual = currentVisual();
  if (!visual) return false;
  if (action === "add-choice") {
    commit(() => {
      const id = uniqueId("variant", visual.choices);
      visual.choices.push({ id, weight: 1, frames: [{ tile: [state.selection.x, state.selection.y] }] });
      state.choiceIndex = visual.choices.length - 1;
      state.frameIndex = 0;
    });
  } else if (action === "delete-choice") {
    if (visual.choices.length <= 1) return true;
    const choiceIndex = Number(element.dataset.choice);
    commit(() => visual.choices.splice(choiceIndex, 1));
  } else if (action === "add-frame") {
    const choiceIndex = Number(element.dataset.choice);
    commit(() => {
      visual.choices[choiceIndex].frames.push({ tile: [state.selection.x, state.selection.y] });
      state.choiceIndex = choiceIndex;
      state.frameIndex = visual.choices[choiceIndex].frames.length - 1;
    });
  } else if (action === "set-frame-tile") {
    const choiceIndex = element.dataset.choice === undefined ? state.choiceIndex : Number(element.dataset.choice);
    const frameIndex = element.dataset.frame === undefined ? state.frameIndex : Number(element.dataset.frame);
    const frame = visual.choices[choiceIndex]?.frames[frameIndex];
    if (!frame) return true;
    state.choiceIndex = choiceIndex;
    state.frameIndex = frameIndex;
    if (frame.tile?.[0] === state.selection.x && frame.tile?.[1] === state.selection.y) {
      renderEditor();
      return true;
    }
    commit(() => { frame.tile = [state.selection.x, state.selection.y]; });
  } else if (action === "delete-frame") {
    const frames = visual.choices[state.choiceIndex]?.frames;
    if (!frames || frames.length <= 1) {
      showToast("フレームは1件以上必要です。", true);
      return true;
    }
    commit(() => frames.splice(state.frameIndex, 1));
  } else return false;
  return true;
}

function mutateObjectVisual(action, element) {
  if (!action.startsWith("object-") || ![
    "object-add-choice",
    "object-delete-choice",
    "object-add-frame",
    "object-set-frame",
    "object-delete-frame",
  ].includes(action)) return false;

  const object = currentObject();
  const visual = currentObjectVisual();
  if (!object || !visual) return true;
  const needsSelection = ["object-add-choice", "object-add-frame", "object-set-frame"].includes(action);
  if (needsSelection && !objectSelectionMatches(object)) {
    showToast(`オブジェクトと同じ ${object.size[0]}×${object.size[1]} の矩形を選択してください。`, true);
    return true;
  }

  if (action === "object-add-choice") {
    const id = uniqueId("variant", visual.choices);
    commit(() => {
      normalizeObjectVisuals(object);
      for (const cell of objectDisplayCells(object)) {
        cell.visual.choices.push({
          id,
          weight: 1,
          frames: [{ tile: selectedObjectTile(cell) }],
        });
      }
      state.choiceIndex = objectDisplayCells(object)[0].visual.choices.length - 1;
      state.frameIndex = 0;
    });
  } else if (action === "object-delete-choice") {
    if (visual.choices.length <= 1) return true;
    const choiceIndex = Number(element.dataset.choice);
    commit(() => {
      normalizeObjectVisuals(object);
      for (const cell of objectDisplayCells(object)) cell.visual.choices.splice(choiceIndex, 1);
    });
  } else if (action === "object-add-frame") {
    const choiceIndex = Number(element.dataset.choice);
    commit(() => {
      normalizeObjectVisuals(object);
      for (const cell of objectDisplayCells(object)) {
        cell.visual.choices[choiceIndex].frames.push({ tile: selectedObjectTile(cell) });
      }
      state.choiceIndex = choiceIndex;
      state.frameIndex = objectDisplayCells(object)[0].visual.choices[choiceIndex].frames.length - 1;
    });
  } else if (action === "object-set-frame") {
    const choiceIndex = Number(element.dataset.choice);
    const frameIndex = Number(element.dataset.frame);
    state.choiceIndex = choiceIndex;
    state.frameIndex = frameIndex;
    commit(() => {
      normalizeObjectVisuals(object);
      for (const cell of objectDisplayCells(object)) {
        cell.visual.choices[choiceIndex].frames[frameIndex].tile = selectedObjectTile(cell);
      }
    });
  } else if (action === "object-delete-frame") {
    const frames = visual.choices[state.choiceIndex]?.frames;
    if (!frames || frames.length <= 1) {
      showToast("フレームは1件以上必要です。", true);
      return true;
    }
    commit(() => {
      normalizeObjectVisuals(object);
      for (const cell of objectDisplayCells(object)) {
        cell.visual.choices[state.choiceIndex].frames.splice(state.frameIndex, 1);
      }
    });
  }
  return true;
}

function handleAction(element) {
  const action = element.dataset.action;
  if (!action) return;
  if ((action === "select-ground" || action === "select-object")
    && performance.now() < state.suppressDefinitionClickUntil) return;
  if (mutateObjectVisual(action, element)) return;
  if (mutateVisual(action, element)) return;
  const grounds = state.data.grounds;
  const objects = state.data.objects;

  if (action === "select-ground") {
    state.groundIndex = Number(element.dataset.index);
    state.boundaryIndex = 0;
    state.choiceIndex = 0;
    state.frameIndex = 0;
    renderAll();
  } else if (action === "add-ground") {
    commit(() => {
      const id = uniqueId("ground", grounds);
      grounds.push({ id, parent_id: null, collision: "passable", base_visual: singleTileVisual(), boundaries: [] });
      state.groundIndex = grounds.length - 1;
    });
  } else if (action === "delete-ground") {
    if (!window.confirm(`地面 ${currentGround().id} を削除しますか？`)) return;
    commit(() => grounds.splice(state.groundIndex, 1));
  } else if (action === "select-boundary") {
    state.boundaryIndex = Number(element.dataset.index);
    state.choiceIndex = 0;
    state.frameIndex = 0;
    renderAll();
  } else if (action === "add-boundary") {
    commit(() => {
      const boundaries = currentGround().boundaries;
      boundaries.push({
        id: uniqueId("boundary", boundaries),
        neighbors: { n: "different", ne: "any", e: "any", se: "any", s: "any", sw: "any", w: "any", nw: "any" },
        visual: singleTileVisual(),
      });
      state.boundaryIndex = boundaries.length - 1;
    });
  } else if (action === "move-boundary-left" || action === "move-boundary-right") {
    const boundaries = currentGround().boundaries;
    const offset = action === "move-boundary-left" ? -1 : 1;
    const destination = state.boundaryIndex + offset;
    if (destination < 0 || destination >= boundaries.length) return;
    commit(() => {
      const [rule] = boundaries.splice(state.boundaryIndex, 1);
      boundaries.splice(destination, 0, rule);
      state.boundaryIndex = destination;
    });
  } else if (action === "delete-boundary") {
    commit(() => currentGround().boundaries.splice(state.boundaryIndex, 1));
  } else if (action === "cycle-neighbor") {
    const direction = element.dataset.direction;
    commit(() => {
      const neighbors = currentBoundary().neighbors;
      neighbors[direction] = NEIGHBOR_CYCLE[(NEIGHBOR_CYCLE.indexOf(neighbors[direction]) + 1) % NEIGHBOR_CYCLE.length];
    });
  } else if (action === "select-object") {
    if (objects[Number(element.dataset.index)]?.default_draw_group !== state.objectLayer) return;
    state.objectIndex = Number(element.dataset.index);
    state.choiceIndex = 0;
    state.frameIndex = 0;
    renderAll();
  } else if (action === "add-object" || action === "object-from-selection") {
    commit(() => {
      let object = action === "add-object" ? null : currentObject();
      if (!object) {
        object = { id: uniqueId("object", objects), size: [1, 1], default_draw_group: state.objectLayer, interact_through: false, cells: [] };
        objects.push(object);
        state.objectOrigins.push(null);
        state.objectIndex = objects.length - 1;
      }
      object.size = [state.selection.width, state.selection.height];
      object.cells = [];
      for (let y = 0; y < state.selection.height; y += 1) {
        for (let x = 0; x < state.selection.width; x += 1) {
          object.cells.push({ offset: [x, y], collision: "blocked", tile: [state.selection.x + x, state.selection.y + y] });
        }
      }
      state.choiceIndex = 0;
      state.frameIndex = 0;
    });
  } else if (action === "delete-object") {
    if (!window.confirm(`オブジェクト ${currentObject().id} を削除しますか？`)) return;
    commit(() => {
      objects.splice(state.objectIndex, 1);
      state.objectOrigins.splice(state.objectIndex, 1);
    });
  } else if (action === "toggle-object-cell-collision") {
    const x = Number(element.dataset.x);
    const y = Number(element.dataset.y);
    const cell = currentObject().cells.find((item) => item.offset[0] === x && item.offset[1] === y);
    if (!cell) return;
    commit(() => { cell.collision = cell.collision === "blocked" ? "passable" : "blocked"; });
  } else if (action === "toggle-object-cell-override") {
    const x = Number(element.dataset.x);
    const y = Number(element.dataset.y);
    const cell = currentObject().cells.find((item) => item.offset[0] === x && item.offset[1] === y);
    if (!cell) return;
    commit(() => { cell.collision = cell.collision === "passable_override" ? "passable" : "passable_override"; });
  } else if (action === "cycle-preview-ground") {
    const index = Number(element.dataset.index);
    const ids = grounds.map((ground) => ground.id);
    const current = ids.indexOf(state.previewGrounds[index]);
    state.previewGrounds[index] = ids[(current + 1) % ids.length];
    renderPreview();
    savePreviewSettings();
  }
}

function handleChange(element) {
  const action = element.dataset.change;
  if (!action) return;
  const value = element.value;
  const ground = currentGround();
  const object = currentObject();
  const visual = currentVisual();

  if (action === "object-layer") {
    if (!OBJECT_LAYERS.some(([layer]) => layer === value)) return;
    state.objectLayer = value;
    state.choiceIndex = 0;
    state.frameIndex = 0;
    renderAll();
    byId("editor-content").querySelector('input[name="object-layer"]:checked')?.focus();
  } else if (action === "ground-id") {
    const oldId = ground.id;
    commit(() => {
      ground.id = value;
      state.data.grounds.forEach((item) => { if (item.parent_id === oldId) item.parent_id = value; });
      state.previewGrounds = state.previewGrounds.map((id) => id === oldId ? value : id);
    });
  } else if (action === "ground-parent") commit(() => { ground.parent_id = value || null; });
  else if (action === "ground-collision") commit(() => { ground.collision = value; });
  else if (action === "visual-interval") commit(() => { visual.frame_interval = Number(value); });
  else if (action === "choice-weight") commit(() => { visual.choices[Number(element.dataset.choice)].weight = Number(value); });
  else if (action === "object-visual-interval") commit(() => {
    normalizeObjectVisuals(object);
    for (const cell of objectDisplayCells(object)) cell.visual.frame_interval = Number(value);
  });
  else if (action === "object-choice-weight") commit(() => {
    normalizeObjectVisuals(object);
    const choiceIndex = Number(element.dataset.choice);
    for (const cell of objectDisplayCells(object)) cell.visual.choices[choiceIndex].weight = Number(value);
  });
  else if (action === "object-id") commit(() => { object.id = value; });
  else if (action === "object-width") commit(() => { object.size[0] = Number(value); });
  else if (action === "object-height") commit(() => { object.size[1] = Number(value); });
  else if (action === "object-group") {
    if (!object || object.default_draw_group === value || !OBJECT_LAYERS.some(([layer]) => layer === value)) return;
    commit(() => {
      object.default_draw_group = value;
      state.objectLayer = value;
    });
  }
  else if (action === "object-interact-through") commit(() => { object.interact_through = element.checked; });
}

async function initialize() {
  if (!token) {
    showToast("起動URLの認証トークンがありません。", true);
    updateSaveState("error", "接続不可");
    return;
  }
  try {
    const requestedTileset = new URLSearchParams(window.location.search).get("tileset");
    const catalog = await api("/api/catalog");
    const storedTileset = loadLastTilesetId();
    const storedTilesetExists = (catalog.tilesets || []).some((item) => item.tileset_id === storedTileset);
    const initialTileset = requestedTileset || (storedTilesetExists ? storedTileset : null);
    const payload = await api(initialTileset ? `/api/document?tileset=${encodeURIComponent(initialTileset)}` : "/api/document");
    state.tilesetCatalog = catalog.tilesets || [];
    state.sourceImages = catalog.source_images || [];
    applyDocumentPayload(payload);
  } catch (error) {
    showToast(error.message, true);
    updateSaveState("error", "読込失敗");
  }
}

byId("tileset-select").addEventListener("change", (event) => {
  requestTilesetSwitch(event.target.value);
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
  pendingTilesetNavigationId = null;
});
byId("new-tileset-button").addEventListener("click", () => {
  if (state.dirty && !window.confirm("未保存の変更を破棄して新規タイルセットを作成しますか？")) return;
  byId("new-tileset-id").value = "";
  byId("new-tileset-source").innerHTML = sourceImageOptions();
  byId("new-tileset-dialog").showModal();
});
byId("new-tileset-dialog").addEventListener("click", (event) => {
  if (event.target === event.currentTarget || event.target.dataset.action === "close-new-tileset-dialog") byId("new-tileset-dialog").close();
});
byId("new-tileset-profile").addEventListener("change", () => {
  const world = byId("new-tileset-profile").value === "world";
  const baseInput = byId("new-tileset-base-id");
  const collisionInput = byId("new-tileset-base-collision");
  if (world) {
    baseInput.value = "sea";
    collisionInput.value = "blocked";
  }
  baseInput.disabled = world;
  collisionInput.disabled = world;
});
byId("new-tileset-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const payload = await api("/api/create", {
      method: "POST",
      body: JSON.stringify({
        tileset_id: byId("new-tileset-id").value.trim(),
        source_image_id: byId("new-tileset-source").value,
        profile: byId("new-tileset-profile").value,
        base_ground_id: byId("new-tileset-base-id").value.trim(),
        base_collision: byId("new-tileset-base-collision").value,
      }),
    });
    byId("new-tileset-dialog").close();
    applyDocumentPayload(payload);
  } catch (error) {
    showToast(error.message, true);
  }
});
byId("delete-tileset-button").addEventListener("click", async () => {
  const record = currentTilesetCatalogRecord();
  if (!record) return;
  const maps = record.map_ids || [];
  if (maps.length) {
    showToast(`次のマップで使用中のため削除できません: ${maps.join(", ")}`, true);
    return;
  }
  if (state.dirty) {
    showToast("未保存の変更があるため削除できません。", true);
    return;
  }
  if (!window.confirm(`タイルセット ${state.data.tileset_id} を削除しますか？この操作は元に戻せません。`)) return;
  try {
    const result = await api("/api/delete", {
      method: "POST",
      body: JSON.stringify({ tileset_id: state.data.tileset_id }),
    });
    state.tilesetCatalog = result.tilesets || [];
    if (result.next_tileset_id) await loadTilesetDocument(result.next_tileset_id);
    showToast(`タイルセット ${result.tileset_id} を削除しました。`);
  } catch (error) {
    showToast(error.message, true);
  }
});

document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => {
  state.tab = button.dataset.tab;
  state.choiceIndex = 0;
  state.frameIndex = 0;
  renderAll();
}));

byId("editor-content").addEventListener("click", (event) => {
  const target = event.target.closest("[data-action]");
  if (target) handleAction(target);
});
byId("editor-content").addEventListener("pointerdown", handleDefinitionPointerDown);
byId("editor-content").addEventListener("pointermove", handleDefinitionPointerMove);
byId("editor-content").addEventListener("pointerup", (event) => finishDefinitionPointerDrag(event));
byId("editor-content").addEventListener("pointercancel", (event) => finishDefinitionPointerDrag(event, true));
byId("editor-content").addEventListener("contextmenu", (event) => {
  const visualFrame = event.target.closest('[data-action="set-frame-tile"]');
  if (visualFrame) {
    event.preventDefault();
    focusVisualFrameInSource(visualFrame);
    return;
  }
  const objectFrame = event.target.closest('[data-action="object-set-frame"]');
  if (objectFrame) {
    event.preventDefault();
    focusObjectFrameInSource(objectFrame);
    return;
  }
  const target = event.target.closest('[data-action="toggle-object-cell-collision"]');
  if (!target) return;
  event.preventDefault();
  handleAction({ dataset: { action: "toggle-object-cell-override", x: target.dataset.x, y: target.dataset.y } });
});
byId("editor-content").addEventListener("change", (event) => handleChange(event.target));
byId("preview-content").addEventListener("click", (event) => {
  const target = event.target.closest("[data-action]");
  if (target) handleAction(target);
});
byId("undo-button").addEventListener("click", undo);
byId("redo-button").addEventListener("click", redo);
byId("save-button").addEventListener("click", save);
byId("zoom-in").addEventListener("click", () => { state.zoom = Math.min(6, state.zoom + 1); drawSource(); });
byId("zoom-out").addEventListener("click", () => { state.zoom = Math.max(1, state.zoom - 1); drawSource(); });
byId("preview-collision").addEventListener("change", (event) => {
  state.previewShowCollision = event.target.checked;
  savePreviewSettings();
  drawPreviews(performance.now());
});
byId("preview-pause").addEventListener("click", () => {
  state.previewPaused = !state.previewPaused;
  if (!state.previewPaused) state.previewStartedAt = performance.now();
  syncPreviewControls();
  savePreviewSettings();
  drawPreviews(performance.now());
});

const sourceCanvas = byId("source-canvas");
sourceCanvas.addEventListener("pointerdown", (event) => {
  if (!state.imageInfo) return;
  sourceCanvas.setPointerCapture(event.pointerId);
  state.dragStart = tileFromPointer(event);
  updateDragSelection(state.dragStart);
});
sourceCanvas.addEventListener("pointermove", (event) => {
  if (state.dragStart) updateDragSelection(tileFromPointer(event));
});
sourceCanvas.addEventListener("pointerup", (event) => {
  if (!state.dragStart) return;
  updateDragSelection(tileFromPointer(event));
  state.dragStart = null;
  renderEditor();
});

window.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    save();
  } else if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
    event.preventDefault();
    if (event.shiftKey) redo(); else undo();
  }
});
window.addEventListener("beforeunload", (event) => {
  if (state.dirty) {
    event.preventDefault();
    event.returnValue = "";
  }
});

requestAnimationFrame(animationLoop);
configureEditorNavigation();
initialize();
