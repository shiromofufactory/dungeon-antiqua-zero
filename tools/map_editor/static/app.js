"use strict";

const SESSION_CLIENT_HEADER = "map-editor-ui";
const CELL_SIZE = 16;
let token = new URLSearchParams(window.location.search).get("token") || "";

const state = {
  data: null,
  tileset: null,
  siteNamesJa: {},
  destinationOptions: [],
  siteOptions: [],
  resolved: null,
  diagnostics: [],
  dirty: false,
  history: [],
  future: [],
  tab: "ground",
  groundId: null,
  objectId: null,
  selectedInstanceId: null,
  selectedSiteId: null,
  selectedArrivalId: null,
  travelTool: "select",
  resizeHorizontal: "right",
  resizeVertical: "down",
  zoom: 2,
  showGrid: true,
  showCollision: false,
  paused: false,
  animationStartedAt: performance.now(),
  pointerStroke: null,
  pointerDrag: null,
  resolveTimer: null,
  resolveRevision: 0,
  siteNameEditing: false,
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
  }
  if (!grounds.some((ground) => ground.id === state.groundId)) state.groundId = grounds[0]?.id || null;
  if (!objects.some((object) => object.id === state.objectId)) state.objectId = objects[0]?.id || null;
  if (!state.data?.objects?.some((instance) => instance.id === state.selectedInstanceId)) state.selectedInstanceId = null;
  if (!state.data?.sites?.some((site) => site.id === state.selectedSiteId)) state.selectedSiteId = null;
  if (!state.data?.arrival_points?.some((arrival) => arrival.id === state.selectedArrivalId)) state.selectedArrivalId = null;
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
  } else if (state.tab === "object") {
    container.innerHTML = `
      <div class="section">
        <div class="section-title"><h2>オブジェクト</h2><span class="subtle">左クリックで配置・右クリック／ドラッグで選択・移動</span></div>
        <div class="palette-list">${state.tileset.objects.map((object, index) => `
          <button class="palette-item ${object.id === state.objectId ? "active" : ""}" type="button" data-action="select-object-definition" data-id="${escapeHtml(object.id)}">
            <canvas data-object-thumb="${index}" width="${object.size[0] * 16}" height="${object.size[1] * 16}"></canvas><span>${escapeHtml(object.id)}</span>${object.default_draw_group === "object_overlay" ? `<span class="palette-meta">前面パーツ</span>` : ""}
          </button>`).join("") || `<div class="empty-state">オブジェクト定義がありません。</div>`}</div>
        </div>`;
  } else {
    container.innerHTML = `
      <div class="section">
        <div class="section-title"><h2>拠点</h2><span class="subtle">${state.data.sites.length}件</span></div>
        <div class="travel-list">${state.data.sites.map((site) => `
          <button class="travel-item ${site.id === state.selectedSiteId ? "active" : ""}" type="button" data-action="select-site" data-id="${escapeHtml(site.id)}">
            <strong>${escapeHtml(site.id)}</strong>${escapeHtml(state.siteNamesJa[site.id] || "日本語名未入力")}
          </button>`).join("") || `<div class="empty-state">拠点がありません。</div>`}</div>
        ${state.data.profile === "world"
          ? `<div class="row" style="margin-top:9px"><button class="button secondary small" type="button" data-action="prepare-cell-site">座標拠点を追加</button></div>`
          : `<div class="empty-state">拠点はworld profileで編集します。</div>`}
      </div>
      <div class="section">
        <div class="section-title"><h2>到着地点</h2><span class="subtle">${state.data.arrival_points.length}件</span></div>
        <div class="travel-list">${state.data.arrival_points.map((arrival) => `
          <button class="travel-item ${arrival.id === state.selectedArrivalId ? "active" : ""}" type="button" data-action="select-arrival" data-id="${escapeHtml(arrival.id)}">
            <strong>${escapeHtml(arrival.id)}</strong>${arrival.position.join(", ")} / ${escapeHtml(arrival.facing)}${arrival.teleport_enabled ? " / テレポート対象" : ""}
          </button>`).join("") || `<div class="empty-state">到着地点がありません。</div>`}</div>
        <div class="row" style="margin-top:9px"><button class="button secondary small" type="button" data-action="prepare-arrival">到着地点を追加</button></div>
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

function siteForObject(objectId) {
  return state.data?.sites?.find((site) => site.anchor?.kind === "object" && site.anchor.object_id === objectId) || null;
}

function siteNameTextKey(siteId) {
  return `location.${siteId}`;
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
  return [...new Set([...state.siteOptions, ...state.data.sites.map((site) => site.id)])].sort();
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
  const attachedSite = instance ? siteForObject(instance.id) : null;
  const objectInspector = `
    <div class="section">
      <div class="section-title"><h2>選択オブジェクト</h2><span class="subtle">配置数 ${state.data.objects.length}</span></div>
      ${instance ? `
        <div class="instance-card"><strong>${escapeHtml(instance.definition_id)}</strong>ID: ${escapeHtml(instance.id)}<br>起点: ${instance.origin.join(", ")} / ${objectDefinition(instance)?.default_draw_group === "object_overlay" ? "前面パーツ" : "通常オブジェクト"}<br>同一下端内の順序: ${instance.order}</div>
        <div class="row between" style="margin-top:9px">
          <div class="row"><button class="button ghost small" type="button" data-action="object-back">背面へ</button><button class="button ghost small" type="button" data-action="object-front">前面へ</button></div>
          <button class="button danger small" type="button" data-action="delete-instance">配置を削除</button>
        </div>
        ${state.data.profile === "world" ? `<div class="row" style="margin-top:9px"><button class="button secondary small" type="button" data-action="${attachedSite ? "open-attached-site" : "attach-site"}">${attachedSite ? `拠点 ${escapeHtml(attachedSite.id)} を編集` : "拠点として設定"}</button></div>` : ""}`
        : `<div class="empty-state">マップ上のオブジェクトを右クリックすると選択できます。</div>`}
    </div>`;
  const siteInspector = `
    <div class="section">
      <div class="section-title"><h2>選択拠点</h2><span class="subtle">${state.data.sites.length}件</span></div>
      ${site ? `
        <div class="instance-card"><strong>${escapeHtml(site.id)}</strong>アンカー: ${site.anchor.kind === "object" ? `オブジェクト ${escapeHtml(site.anchor.object_id)}` : `セル ${site.anchor.position.join(", ")}`}<br>入口: ${site.entrance_offsets.length}セル</div>
        <div class="form-grid" style="margin-top:9px">
          <div class="field full">
            <label>拠点ID</label>
            <input type="text" value="${escapeHtml(site.id)}" data-site-field="id">
            <div class="field-note">文言キー：${escapeHtml(siteNameTextKey(site.id))}</div>
          </div>
          <div class="field full"><label>日本語名</label><input type="text" value="${escapeHtml(state.siteNamesJa[site.id] || "")}" data-site-name-ja="true"></div>
          <div class="field"><label>移動先マップID</label><select data-site-field="destination.map_id">${destinationMapOptions(site.destination.map_id)}</select></div>
          <div class="field"><label>移動先到着地点ID</label><select data-site-field="destination.arrival_id">${destinationArrivalOptions(site.destination.map_id, site.destination.arrival_id)}</select></div>
        </div>
        <div class="row" style="margin-top:9px">
          <button class="button ghost small" type="button" data-action="edit-site-entrances">入口セルを編集</button>
        </div>
        <div class="row end" style="margin-top:9px"><button class="button danger small" type="button" data-action="delete-site">拠点を削除</button></div>
      ` : `<div class="empty-state">左の一覧またはキャンバスから拠点を選択してください。</div>`}
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
  byId("inspector-content").innerHTML = `
    <div class="section">
      <div class="section-title"><h2>マップ設定</h2><span class="subtle">${escapeHtml(state.data.profile)} / ${escapeHtml(state.data.tileset_id)}</span></div>
      <div class="form-grid">
        <div class="field"><label>幅</label><input id="map-width" type="number" min="1" max="512" value="${width}"></div>
        <div class="field"><label>高さ</label><input id="map-height" type="number" min="1" max="512" value="${height}"></div>
        <div class="field"><label>横方向</label><select id="resize-horizontal"><option value="left" ${state.resizeHorizontal === "left" ? "selected" : ""}>左側を増減</option><option value="right" ${state.resizeHorizontal === "right" ? "selected" : ""}>右側を増減</option></select></div>
        <div class="field"><label>縦方向</label><select id="resize-vertical"><option value="up" ${state.resizeVertical === "up" ? "selected" : ""}>上側を増減</option><option value="down" ${state.resizeVertical === "down" ? "selected" : ""}>下側を増減</option></select></div>
        <div class="field full"><label>表示seed</label><input id="visual-seed" type="number" min="0" value="${state.data.visual_seed}" disabled></div>
      </div>
      <div class="row between" style="margin-top:9px">
        <button class="button ghost small" type="button" data-action="reroll">見た目を振り直す</button>
        <button class="button secondary small" type="button" data-action="resize-map">寸法を反映</button>
      </div>
    </div>
    ${state.tab === "site" ? siteInspector : objectInspector}
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
  byId("map-summary").textContent = `${state.data.size[0]}×${state.data.size[1]} cells · ${state.data.objects.length} objects · ${state.data.sites.length} sites`;
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

function drawTravelMarkers(context, scale) {
  for (const site of state.data.sites) {
    const selected = site.id === state.selectedSiteId;
    const origin = siteAnchorPosition(site);
    context.lineWidth = Math.max(selected ? 3 : 2, state.zoom);
    for (const entrance of siteEntrancePositions(site)) {
      context.fillStyle = selected ? "rgba(47,196,255,.42)" : "rgba(47,196,255,.24)";
      context.strokeStyle = selected ? "#71ddff" : "#319bc0";
      context.fillRect(entrance[0] * scale, entrance[1] * scale, scale, scale);
      context.strokeRect(entrance[0] * scale + 1, entrance[1] * scale + 1, scale - 2, scale - 2);
    }
    if (site.anchor?.kind === "cell" && origin) {
      context.strokeStyle = selected ? "#ff67bd" : "#9d4779";
      context.beginPath();
      context.moveTo(origin[0] * scale + scale * .2, origin[1] * scale + scale * .2);
      context.lineTo((origin[0] + .8) * scale, (origin[1] + .8) * scale);
      context.moveTo((origin[0] + .8) * scale, origin[1] * scale + scale * .2);
      context.lineTo(origin[0] * scale + scale * .2, (origin[1] + .8) * scale);
      context.stroke();
    }
  }
  for (const arrival of state.data.arrival_points) {
    const selected = arrival.id === state.selectedArrivalId;
    const color = selected ? "#91f090" : "#4b9652";
    context.strokeStyle = color;
    context.lineWidth = Math.max(selected ? 3 : 2, state.zoom);
    context.strokeRect(arrival.position[0] * scale + 5, arrival.position[1] * scale + 5, scale - 10, scale - 10);
    drawDirectionMarker(context, arrival.position, arrival.facing, scale, color);
  }
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
  drawTravelMarkers(context, scale);
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
  else if (state.tab === "object") byId("tool-status").textContent = `左: ${state.objectId || "—"}を配置 / 右: 選択・移動 / 選択後は左ドラッグでも移動`;
  else {
    const selectedSite = currentSite();
    const labels = {
      select: selectedSite?.anchor?.kind === "cell" ? "ピンクのアンカーを左ドラッグして移動" : "拠点または到着地点を選択",
      create_site: "座標アンカーにするセルを選択",
      entrance: "入口セルをクリックして追加・解除",
      create_arrival: "到着地点にするセルを選択",
      move_arrival: "到着地点の新しいセルを選択",
    };
    byId("tool-status").textContent = labels[state.travelTool] || labels.select;
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

function uniqueRecordId(base, records) {
  const used = new Set(records.map((record) => record.id));
  if (!used.has(base)) return base;
  let suffix = 2;
  while (used.has(`${base}_${suffix}`)) suffix += 1;
  return `${base}_${suffix}`;
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
  const siteId = uniqueRecordId(instance.id, state.data.sites);
  const offsets = definition.cells.length
    ? [...new Map(definition.cells.map((cell) => [cell.offset.join(","), [...cell.offset]])).values()]
    : [[0, 0]];
  commit(() => {
    state.data.sites.push(defaultSite(siteId, { kind: "object", object_id: instance.id }, offsets));
    state.siteNamesJa[siteId] = defaultSiteNameJa();
    state.selectedSiteId = siteId;
    state.selectedArrivalId = null;
    state.tab = "site";
    state.travelTool = "select";
  });
}

function createCellSite(position) {
  const siteId = uniqueRecordId("site_1", state.data.sites);
  commit(() => {
    state.data.sites.push(defaultSite(siteId, { kind: "cell", position: [...position] }, [[0, 0]]));
    state.siteNamesJa[siteId] = defaultSiteNameJa();
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
  if (action === "select-ground") {
    state.groundId = element.dataset.id;
    renderPalette();
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
  const [previousWidth, previousHeight] = state.data.size;
  const offsetX = state.resizeHorizontal === "left" ? width - previousWidth : 0;
  const offsetY = state.resizeVertical === "up" ? height - previousHeight : 0;
  const rootGround = state.data.profile === "world" && state.tileset.grounds.some((ground) => ground.id === "sea") ? "sea" : state.tileset.grounds[0].id;
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
}

function updateSiteField(path, value) {
  const site = currentSite();
  if (!site) return;
  commit(() => {
    if (path === "id") {
      const previousId = site.id;
      site.id = value;
      state.selectedSiteId = value;
      state.siteNamesJa[value] = state.siteNamesJa[previousId] || "";
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

function scheduleResolution(delay = 70) {
  window.clearTimeout(state.resolveTimer);
  const revision = ++state.resolveRevision;
  state.resolveTimer = window.setTimeout(async () => {
    try {
      const result = await api("/api/resolve", { method: "POST", body: JSON.stringify({ data: state.data, site_names_ja: state.siteNamesJa }) });
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
    const result = await api("/api/validate", { method: "POST", body: JSON.stringify({ data: state.data, site_names_ja: state.siteNamesJa }) });
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
    const result = await api("/api/save", { method: "POST", body: JSON.stringify({ data: state.data, site_names_ja: state.siteNamesJa }) });
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
    state.siteNamesJa = payload.site_names_ja;
    state.destinationOptions = payload.destination_options;
    state.siteOptions = payload.site_options;
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
  state.travelTool = "select";
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
  else if (event.target.dataset.siteNameJa) {
    state.siteNameEditing = false;
    renderPalette();
  }
  else if (event.target.dataset.siteField) updateSiteField(event.target.dataset.siteField, event.target.value);
  else if (event.target.dataset.arrivalField) updateArrivalField(event.target.dataset.arrivalField, event.target.type === "checkbox" ? event.target.checked : event.target.value);
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
  if (event.button === 2) {
    event.preventDefault();
    if (state.tab === "site") {
      state.travelTool = "select";
      selectTravelAt(cell);
      return;
    }
    state.selectedInstanceId = instanceAt(...cell)?.id || null;
    state.tab = "object";
    renderAll();
    beginObjectDrag(event, cell);
    return;
  }
  if (event.button !== 0) return;
  if (state.tab === "ground") {
    beginChange();
    state.pointerStroke = { changed: false, last: null, pointerId: event.pointerId };
    mapCanvas.setPointerCapture(event.pointerId);
    state.pointerStroke.changed = paintGround(...cell);
    state.pointerStroke.last = cell.join(",");
    if (state.pointerStroke.changed) { state.dirty = true; scheduleResolution(); updateSaveState(); }
  } else if (state.tab === "object") {
    if (!beginObjectDrag(event, cell)) placeObject(...cell);
  } else if (!beginSiteAnchorDrag(event, cell)) handleTravelCell(cell);
});
mapCanvas.addEventListener("pointermove", (event) => {
  const cell = mapCellFromPointer(event);
  byId("cursor-status").textContent = cell ? `セル ${cell[0]}, ${cell[1]}` : "セル —";
  if (cell && state.pointerDrag) {
    if (state.pointerDrag.kind === "object") dragObjectTo(cell);
    else if (state.pointerDrag.kind === "site_anchor") dragSiteAnchorTo(cell);
    return;
  }
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
  if (state.pointerDrag && !state.pointerDrag.changed) state.history.pop();
  state.pointerStroke = null;
  state.pointerDrag = null;
  renderAll();
});
mapCanvas.addEventListener("contextmenu", (event) => event.preventDefault());
mapCanvas.addEventListener("pointerleave", () => { byId("cursor-status").textContent = "セル —"; });

window.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") { event.preventDefault(); save(); }
  else if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") { event.preventDefault(); if (event.shiftKey) redo(); else undo(); }
  else if ((event.key === "Delete" || event.key === "Backspace") && state.tab === "object" && state.selectedInstanceId && event.target.tagName !== "INPUT") {
    event.preventDefault();
    handleInspectorAction({ dataset: { action: "delete-instance" } });
  } else if ((event.key === "Delete" || event.key === "Backspace") && state.tab === "site" && state.selectedSiteId && event.target.tagName !== "INPUT") {
    event.preventDefault();
    handleInspectorAction({ dataset: { action: "delete-site" } });
  } else if ((event.key === "Delete" || event.key === "Backspace") && state.tab === "site" && state.selectedArrivalId && event.target.tagName !== "INPUT") {
    event.preventDefault();
    handleInspectorAction({ dataset: { action: "delete-arrival" } });
  }
});
window.addEventListener("beforeunload", (event) => {
  if (state.dirty) { event.preventDefault(); event.returnValue = ""; }
});

requestAnimationFrame(animationLoop);
initialize();
