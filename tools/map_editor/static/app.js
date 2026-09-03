"use strict";

const SESSION_CLIENT_HEADER = "map-editor-ui";
const CELL_SIZE = 16;
let token = new URLSearchParams(window.location.search).get("token") || "";

const state = {
  data: null,
  tileset: null,
  resolved: null,
  diagnostics: [],
  dirty: false,
  history: [],
  future: [],
  tab: "ground",
  groundId: null,
  objectId: null,
  objectTool: "place",
  selectedInstanceId: null,
  zoom: 2,
  showGrid: true,
  showCollision: false,
  paused: false,
  animationStartedAt: performance.now(),
  pointerStroke: null,
  resolveTimer: null,
  resolveRevision: 0,
};

const rawImage = new Image();
const sourceImage = document.createElement("canvas");
const byId = (id) => document.getElementById(id);
const clone = (value) => JSON.parse(JSON.stringify(value));
const escapeHtml = (value) => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");

async function renewSessionToken() {
  try {
    const response = await fetch("/api/session-token", { cache: "no-store", headers: { "X-Map-Editor-Client": SESSION_CLIENT_HEADER } });
    if (!response.ok) return false;
    const value = await response.json();
    if (typeof value.token !== "string" || !value.token) return false;
    token = value.token;
    const url = new URL(window.location.href);
    url.searchParams.set("token", token);
    window.history.replaceState(null, "", url);
    return true;
  } catch (_error) {
    return false;
  }
}

async function api(path, options = {}, retryAuthentication = true) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", "X-Map-Editor-Token": token, ...(options.headers || {}) },
  });
  if (response.status === 403 && retryAuthentication && await renewSessionToken()) return api(path, options, false);
  const value = await response.json();
  if (!response.ok) throw new Error(response.status === 403 ? "認証セッションを更新できませんでした。ツールを再起動してください。" : value.error || `HTTP ${response.status}`);
  return value;
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
    localStorage.setItem(settingsKey(), JSON.stringify({ zoom: state.zoom, showGrid: state.showGrid, showCollision: state.showCollision }));
  } catch (_error) {}
}

function restoreUiSettings() {
  try {
    const settings = JSON.parse(localStorage.getItem(settingsKey()) || "null");
    if (!settings) return;
    if (Number.isInteger(settings.zoom)) state.zoom = Math.max(1, Math.min(4, settings.zoom));
    if (typeof settings.showGrid === "boolean") state.showGrid = settings.showGrid;
    if (typeof settings.showCollision === "boolean") state.showCollision = settings.showCollision;
  } catch (_error) {}
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
  byId("save-button").disabled = errors;
}

function beginChange() {
  state.history.push(JSON.stringify(state.data));
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
  state.future.push(JSON.stringify(state.data));
  state.data = JSON.parse(state.history.pop());
  state.dirty = true;
  normalizeSelections();
  renderAll();
  scheduleResolution(0);
}

function redo() {
  if (!state.future.length) return;
  state.history.push(JSON.stringify(state.data));
  state.data = JSON.parse(state.future.pop());
  state.dirty = true;
  normalizeSelections();
  renderAll();
  scheduleResolution(0);
}

function normalizeSelections() {
  const grounds = state.tileset?.grounds || [];
  const objects = state.tileset?.objects || [];
  if (!grounds.some((ground) => ground.id === state.groundId)) state.groundId = grounds[0]?.id || null;
  if (!objects.some((object) => object.id === state.objectId)) state.objectId = objects[0]?.id || null;
  if (!state.data?.objects?.some((instance) => instance.id === state.selectedInstanceId)) state.selectedInstanceId = null;
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

function renderPalette() {
  if (!state.tileset) return;
  const container = byId("palette-content");
  if (state.tab === "ground") {
    container.innerHTML = `
      <div class="section">
        <div class="section-title"><h2>地面ブラシ</h2><span class="subtle">ドラッグで塗布</span></div>
        <div class="palette-list">${state.tileset.grounds.map((ground, index) => `
          <button class="palette-item ${ground.id === state.groundId ? "active" : ""}" type="button" data-action="select-ground" data-id="${escapeHtml(ground.id)}">
            <canvas data-ground-thumb="${index}" width="48" height="48"></canvas><span>${escapeHtml(ground.id)}</span>
          </button>`).join("")}</div>
      </div>`;
  } else {
    container.innerHTML = `
      <div class="section">
        <div class="section-title"><h2>オブジェクト</h2><span class="subtle">異なる起点なら重ねられます</span></div>
        <div class="tool-switch">
          <button class="button ghost small ${state.objectTool === "place" ? "active" : ""}" type="button" data-action="object-tool" data-tool="place">配置</button>
          <button class="button ghost small ${state.objectTool === "select" ? "active" : ""}" type="button" data-action="object-tool" data-tool="select">選択</button>
        </div>
        <div class="palette-list">${state.tileset.objects.map((object, index) => `
          <button class="palette-item ${object.id === state.objectId && state.objectTool === "place" ? "active" : ""}" type="button" data-action="select-object-definition" data-id="${escapeHtml(object.id)}">
            <canvas data-object-thumb="${index}" width="${object.size[0] * 16}" height="${object.size[1] * 16}"></canvas><span>${escapeHtml(object.id)}</span>
          </button>`).join("") || `<div class="empty-state">オブジェクト定義がありません。</div>`}</div>
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

function renderInspector() {
  if (!state.data) return;
  const [width, height] = state.data.size;
  const instance = currentInstance();
  byId("inspector-content").innerHTML = `
    <div class="section">
      <div class="section-title"><h2>マップ設定</h2><span class="subtle">${escapeHtml(state.data.profile)} / ${escapeHtml(state.data.tileset_id)}</span></div>
      <div class="form-grid">
        <div class="field"><label>幅</label><input id="map-width" type="number" min="1" max="512" value="${width}"></div>
        <div class="field"><label>高さ</label><input id="map-height" type="number" min="1" max="512" value="${height}"></div>
        <div class="field full"><label>表示seed</label><input id="visual-seed" type="number" min="0" value="${state.data.visual_seed}" disabled></div>
      </div>
      <div class="row between" style="margin-top:9px">
        <button class="button ghost small" type="button" data-action="reroll">見た目を振り直す</button>
        <button class="button secondary small" type="button" data-action="resize-map">寸法を反映</button>
      </div>
    </div>
    <div class="section">
      <div class="section-title"><h2>選択オブジェクト</h2><span class="subtle">配置数 ${state.data.objects.length}</span></div>
      ${instance ? `
        <div class="instance-card"><strong>${escapeHtml(instance.definition_id)}</strong>ID: ${escapeHtml(instance.id)}<br>起点: ${instance.origin.join(", ")} / 描画順: ${instance.order}</div>
        <div class="row between" style="margin-top:9px">
          <div class="row"><button class="button ghost small" type="button" data-action="object-back">背面へ</button><button class="button ghost small" type="button" data-action="object-front">前面へ</button></div>
          <button class="button danger small" type="button" data-action="delete-instance">配置を削除</button>
        </div>` : `<div class="empty-state">オブジェクトの「選択」で、マップ上の配置をクリックしてください。</div>`}
    </div>
    <div class="section"><div class="section-title"><h2>出力</h2></div><p class="subtle">保存時に制作用JSONとゲーム用マップを同時生成します。</p></div>`;
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
  normalizeSelections();
  document.querySelectorAll(".tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === state.tab));
  byId("grid-toggle").checked = state.showGrid;
  byId("collision-toggle").checked = state.showCollision;
  byId("animation-toggle").textContent = state.paused ? "再生" : "一時停止";
  byId("zoom-label").textContent = `${state.zoom}×`;
  byId("map-title").textContent = state.data.map_id;
  byId("map-summary").textContent = `${state.data.size[0]}×${state.data.size[1]} cells · ${state.data.objects.length} objects`;
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
  context.clearRect(0, 0, canvas.width, canvas.height);
  if (state.resolved) {
    state.resolved.ground_cells.forEach((cell, index) => {
      const x = (index % width) * scale;
      const y = Math.floor(index / width) * scale;
      for (const layer of cell.layers) drawSourceTile(context, frameTile(layer, now), x, y, scale);
    });
    for (const cell of state.resolved.object_cells) drawSourceTile(context, frameTile(cell, now), cell.position[0] * scale, cell.position[1] * scale, scale);
    if (state.showCollision) {
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
  const selected = currentInstance();
  if (selected) {
    const definition = state.tileset.objects.find((object) => object.id === selected.definition_id);
    if (definition) {
      context.strokeStyle = "#ff4fa3";
      context.lineWidth = Math.max(2, state.zoom);
      context.strokeRect(selected.origin[0] * scale + 1, selected.origin[1] * scale + 1, definition.size[0] * scale - 2, definition.size[1] * scale - 2);
    }
  }
  if (state.showGrid) {
    context.strokeStyle = "rgba(238,233,215,.18)";
    context.lineWidth = 1;
    context.beginPath();
    for (let x = 0; x <= width; x += 1) { context.moveTo(x * scale + .5, 0); context.lineTo(x * scale + .5, targetHeight); }
    for (let y = 0; y <= height; y += 1) { context.moveTo(0, y * scale + .5); context.lineTo(targetWidth, y * scale + .5); }
    context.stroke();
  }
}

function animationLoop(now) {
  if (!state.paused) drawMap(now);
  requestAnimationFrame(animationLoop);
}

function updateToolStatus() {
  if (!state.data) return;
  if (state.tab === "ground") byId("tool-status").textContent = `地面ブラシ: ${state.groundId || "—"}`;
  else if (state.objectTool === "select") byId("tool-status").textContent = "オブジェクト配置を選択";
  else byId("tool-status").textContent = `オブジェクト配置: ${state.objectId || "—"}`;
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

function paintGround(x, y) {
  if (state.data.grounds[y][x] === state.groundId) return false;
  state.data.grounds[y][x] = state.groundId;
  return true;
}

function uniqueInstanceId(definitionId) {
  const used = new Set(state.data.objects.map((instance) => instance.id));
  let suffix = 1;
  while (used.has(`${definitionId}_${suffix}`)) suffix += 1;
  return `${definitionId}_${suffix}`;
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
    state.objectTool = "select";
    renderAll();
    showToast("同じ起点には配置できないため、既存の配置を選択しました。", true);
    return;
  }
  commit(() => {
    const order = state.data.objects.length ? Math.max(...state.data.objects.map((instance) => instance.order)) + 1 : 0;
    const instance = { id: uniqueInstanceId(definition.id), definition_id: definition.id, origin: [x, y], order };
    state.data.objects.push(instance);
    state.selectedInstanceId = instance.id;
  });
}

function instanceAt(x, y) {
  const definitions = new Map(state.tileset.objects.map((object) => [object.id, object]));
  return [...state.data.objects]
    .sort((left, right) => right.order - left.order || right.origin[1] - left.origin[1] || right.origin[0] - left.origin[0])
    .find((instance) => {
      const definition = definitions.get(instance.definition_id);
      return definition && definition.cells.some((cell) => instance.origin[0] + cell.offset[0] === x && instance.origin[1] + cell.offset[1] === y);
    }) || null;
}

function handlePaletteAction(element) {
  const action = element.dataset.action;
  if (action === "select-ground") {
    state.groundId = element.dataset.id;
    renderPalette();
  } else if (action === "select-object-definition") {
    state.objectId = element.dataset.id;
    state.objectTool = "place";
    renderPalette();
  } else if (action === "object-tool") {
    state.objectTool = element.dataset.tool;
    renderPalette();
  }
}

function resizeMap() {
  const width = Number(byId("map-width").value);
  const height = Number(byId("map-height").value);
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 || width > 512 || height > 512) {
    showToast("幅と高さは1〜512の整数で指定してください。", true);
    return;
  }
  if (width === state.data.size[0] && height === state.data.size[1]) return;
  const rootGround = state.data.profile === "world" && state.tileset.grounds.some((ground) => ground.id === "sea") ? "sea" : state.tileset.grounds[0].id;
  commit(() => {
    const previous = state.data.grounds;
    state.data.grounds = Array.from({ length: height }, (_unused, y) => Array.from({ length: width }, (_empty, x) => previous[y]?.[x] || rootGround));
    state.data.size = [width, height];
  });
}

function handleInspectorAction(element) {
  const action = element.dataset.action;
  if (action === "resize-map") resizeMap();
  else if (action === "reroll") commit(() => { state.data.visual_seed += 1; });
  else if (action === "delete-instance") commit(() => {
    const index = state.data.objects.findIndex((instance) => instance.id === state.selectedInstanceId);
    if (index >= 0) state.data.objects.splice(index, 1);
    state.selectedInstanceId = null;
  });
  else if (action === "object-front" || action === "object-back") commit(() => {
    const instance = currentInstance();
    const orders = state.data.objects.map((item) => item.order);
    instance.order = action === "object-front" ? Math.max(...orders) + 1 : Math.min(...orders) - 1;
  });
}

function scheduleResolution(delay = 70) {
  window.clearTimeout(state.resolveTimer);
  const revision = ++state.resolveRevision;
  state.resolveTimer = window.setTimeout(async () => {
    try {
      const result = await api("/api/resolve", { method: "POST", body: JSON.stringify({ data: state.data }) });
      if (revision !== state.resolveRevision) return;
      state.diagnostics = result.diagnostics;
      state.resolved = result.resolved;
      renderIssues();
      drawMap(performance.now());
    } catch (error) {
      if (revision === state.resolveRevision) showToast(error.message, true);
    }
  }, delay);
}

async function validate(showResult = false) {
  try {
    const result = await api("/api/validate", { method: "POST", body: JSON.stringify({ data: state.data }) });
    state.diagnostics = result.diagnostics;
    state.resolved = result.resolved;
    renderIssues();
    drawMap(performance.now());
    if (showResult) showToast(state.diagnostics.some((issue) => issue.severity === "error") ? "修正が必要な項目があります。" : "検証に成功しました。", state.diagnostics.some((issue) => issue.severity === "error"));
  } catch (error) {
    showToast(error.message, true);
  }
}

async function save() {
  updateSaveState("dirty", "保存・生成中…");
  try {
    const result = await api("/api/save", { method: "POST", body: JSON.stringify({ data: state.data }) });
    state.diagnostics = result.diagnostics;
    state.resolved = result.resolved;
    if (result.saved) {
      state.dirty = false;
      state.history = [];
      state.future = [];
      showToast("制作用マップを保存し、ゲーム用データを生成しました。");
    } else showToast("エラーを修正してから保存してください。", true);
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
    const payload = await api("/api/document");
    state.data = payload.data;
    state.tileset = payload.tileset;
    state.resolved = payload.resolved;
    state.diagnostics = payload.diagnostics;
    state.dirty = payload.is_new;
    state.groundId = state.tileset.grounds[0]?.id || null;
    state.objectId = state.tileset.objects[0]?.id || null;
    restoreUiSettings();
    byId("document-path").textContent = `${payload.source_path} → ${payload.runtime_path}`;
    rawImage.onload = prepareSourceImage;
    rawImage.onerror = () => showToast("マップチップ画像を表示できません。", true);
    rawImage.src = payload.image_url;
    renderAll();
  } catch (error) {
    showToast(error.message, true);
    updateSaveState("error", "読込失敗");
  }
}

document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => {
  state.tab = button.dataset.tab;
  if (state.tab === "object") state.objectTool = "place";
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
byId("undo-button").addEventListener("click", undo);
byId("redo-button").addEventListener("click", redo);
byId("validate-button").addEventListener("click", () => validate(true));
byId("save-button").addEventListener("click", save);
byId("zoom-in").addEventListener("click", () => { state.zoom = Math.min(4, state.zoom + 1); saveUiSettings(); renderAll(); });
byId("zoom-out").addEventListener("click", () => { state.zoom = Math.max(1, state.zoom - 1); saveUiSettings(); renderAll(); });
byId("grid-toggle").addEventListener("change", (event) => { state.showGrid = event.target.checked; saveUiSettings(); drawMap(performance.now()); });
byId("collision-toggle").addEventListener("change", (event) => { state.showCollision = event.target.checked; saveUiSettings(); drawMap(performance.now()); });
byId("animation-toggle").addEventListener("click", () => {
  state.paused = !state.paused;
  if (!state.paused) state.animationStartedAt = performance.now();
  renderAll();
});

const mapCanvas = byId("map-canvas");
mapCanvas.addEventListener("pointerdown", (event) => {
  const cell = mapCellFromPointer(event);
  if (!cell) return;
  if (state.tab === "ground") {
    beginChange();
    state.pointerStroke = { changed: false, last: null, pointerId: event.pointerId };
    mapCanvas.setPointerCapture(event.pointerId);
    state.pointerStroke.changed = paintGround(...cell);
    state.pointerStroke.last = cell.join(",");
    if (state.pointerStroke.changed) { state.dirty = true; scheduleResolution(); updateSaveState(); }
  } else if (state.objectTool === "place") placeObject(...cell);
  else {
    state.selectedInstanceId = instanceAt(...cell)?.id || null;
    renderAll();
  }
});
mapCanvas.addEventListener("pointermove", (event) => {
  const cell = mapCellFromPointer(event);
  byId("cursor-status").textContent = cell ? `セル ${cell[0]}, ${cell[1]}` : "セル —";
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
  if (!state.pointerStroke) return;
  if (!state.pointerStroke.changed) state.history.pop();
  state.pointerStroke = null;
  if (mapCanvas.hasPointerCapture(event.pointerId)) mapCanvas.releasePointerCapture(event.pointerId);
  renderAll();
});
mapCanvas.addEventListener("pointercancel", () => {
  if (state.pointerStroke && !state.pointerStroke.changed) state.history.pop();
  state.pointerStroke = null;
  renderAll();
});
mapCanvas.addEventListener("pointerleave", () => { byId("cursor-status").textContent = "セル —"; });

window.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") { event.preventDefault(); save(); }
  else if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") { event.preventDefault(); if (event.shiftKey) redo(); else undo(); }
  else if ((event.key === "Delete" || event.key === "Backspace") && state.selectedInstanceId && event.target.tagName !== "INPUT") {
    event.preventDefault();
    handleInspectorAction({ dataset: { action: "delete-instance" } });
  }
});
window.addEventListener("beforeunload", (event) => {
  if (state.dirty) { event.preventDefault(); event.returnValue = ""; }
});

requestAnimationFrame(animationLoop);
initialize();
