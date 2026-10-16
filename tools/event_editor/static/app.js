"use strict";

document.addEventListener("contextmenu", (event) => event.preventDefault(), { capture: true });

const CLIENT = "event-editor-ui";
const UI_STORAGE_KEY = "da0.event-editor.ui.v1";
const LIST_TABS = ["flag", "event", "mission", "message"];
const COMMAND_OPTIONS = [
  ["message", "message"],
  ["set_flag", "set_flag"],
  ["branch", "branch"],
  ["end_event", "イベント終了"],
  ["join_party", "join_party"],
  ["leave_party", "leave_party"],
  ["give_item", "give_item"],
  ["take_item", "take_item"],
  ["recover_party", "パーティ全快"],
  ["open_shop", "ショップを開く"],
  ["start_battle", "イベントバトル開始"],
  ["play_se", "play_se"],
  ["change_bgm", "change_bgm"],
  ["stop_bgm", "stop_bgm（BGM停止）"],
  ["reset_game", "ゲームをリセット"],
  ["flash_screen", "画面をフラッシュ"],
  ["change_brightness", "画面の明るさを変更"],
  ["shake_screen", "画面を横揺れ"],
  ["wait", "wait（待機）"],
  ["move_party", "move_party"],
  ["move_actor", "move_actor"],
  ["face_party", "face_party（パーティの向き変更）"],
  ["face_actor", "face_actor（actorの向き変更）"],
];
let token = new URLSearchParams(location.search).get("token") || "";
const editorRoute = location.pathname.match(/^\/(tileset|map|event)(?:\/|$)/)?.[1] || null;
const state = {
  data: null,
  flags: [],
  messages: [],
  missions: [],
  selectedMission: 0,
  catalogs: {},
  faceSheet: null,
  diagnostics: [],
  filterText: "",
  selectedFlag: 0,
  selectedEvent: 0,
  selectedMessage: 0,
  mode: "event",
  dirty: false,
  history: [],
  future: [],
  timer: null,
  revision: 0,
  pendingActorEventId: null,
};
let draggedCommand = null;
let draggedListItem = null;
let pendingEditorNavigationUrl = null;
const pendingActorEventDraftId = new URLSearchParams(location.search).get("new_actor_event");
let pendingActorEventDraft = null;
let actorEventReturnMapId = null;

const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");

function loadUiSettings() {
  try {
    const value = JSON.parse(localStorage.getItem(UI_STORAGE_KEY) || "null");
    return value && typeof value === "object" ? value : {};
  } catch (_error) {
    return {};
  }
}

function saveUiSettings() {
  if (!state.data) return;
  try {
    localStorage.setItem(UI_STORAGE_KEY, JSON.stringify({
      listTab: state.mode,
    }));
  } catch (_error) {}
}

function editorApiPath(path) {
  return editorRoute ? `/${editorRoute}${path}` : path;
}

function editorUrl(editor, parameters = {}) {
  if (!editorRoute) return null;
  const url = new URL(`/${editor}/`, location.origin);
  url.searchParams.set("token", token);
  for (const [key, value] of Object.entries(parameters)) {
    if (value) url.searchParams.set(key, value);
  }
  return url.href;
}

function faceSheetUrl() {
  const url = new URL(editorApiPath("/api/face-sheet"), location.origin);
  url.searchParams.set("token", token);
  return url.href;
}

function configureEditorNavigation() {
  const navigation = $("editor-switch");
  if (!navigation || !editorRoute) return;
  navigation.hidden = false;
  navigation.querySelectorAll("[data-editor-link]").forEach((link) => {
    link.href = editorUrl(link.dataset.editorLink, {
      map: pendingActorEventDraft?.data?.map_id || actorEventReturnMapId,
    });
  });
}

function loadPendingActorEventDraft() {
  if (!pendingActorEventDraftId) return null;
  try {
    const value = JSON.parse(sessionStorage.getItem(`da0.pending-actor-event:${pendingActorEventDraftId}`) || "null");
    return value && typeof value === "object" ? value : null;
  } catch (_error) {
    return null;
  }
}

async function mapApi(path, options = {}, retry = true) {
  const response = await fetch(`/map${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Map-Editor-Token": token,
      ...(options.headers || {}),
    },
  });
  if (response.status === 403 && retry && await renew()) {
    return mapApi(path, options, false);
  }
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || `HTTP ${response.status}`);
  return value;
}

async function savePendingActorEventLink() {
  if (!pendingActorEventDraft || !pendingActorEventDraftId) return null;
  const eventId = state.pendingActorEventId;
  const eventExists = state.data.events.some((event) => event.id === eventId);
  if (!eventId || !eventExists) {
    throw new Error("actorへ紐づける新規イベントがありません。");
  }
  const mapData = JSON.parse(JSON.stringify(pendingActorEventDraft.data));
  const actorId = pendingActorEventDraft.actor_id;
  const actorExists = mapData.actors?.some((actor) => actor.id === actorId);
  const trigger = mapData.event_triggers?.find(
    (item) => item.anchor?.kind === "actor" && item.anchor.actor_id === actorId,
  );
  if (!actorExists || !trigger) {
    throw new Error("紐づけ先のactorまたはtriggerが見つかりません。");
  }
  trigger.event_id = eventId;
  const result = await mapApi("/api/save", {
    method: "POST",
    body: JSON.stringify({
      data: mapData,
      site_names_ja: pendingActorEventDraft.site_names_ja,
    }),
  });
  if (!result.saved) {
    const reason = result.diagnostics?.find((item) => item.severity === "error")?.message;
    throw new Error(reason || "actorへのイベント紐づけを保存できませんでした。");
  }
  sessionStorage.removeItem(`da0.pending-actor-event:${pendingActorEventDraftId}`);
  actorEventReturnMapId = mapData.map_id;
  pendingActorEventDraft = null;
  state.pendingActorEventId = null;
  return {mapId: mapData.map_id, actorId};
}

function navigateToEditor(url) {
  if (!url) return;
  if (!state.dirty) {
    location.assign(url);
    return;
  }
  pendingEditorNavigationUrl = url;
  $("unsaved-navigation-dialog").showModal();
}

function closeNavigationDialog() {
  pendingEditorNavigationUrl = null;
  $("unsaved-navigation-dialog").close();
}

function discardPendingActorEventDraft() {
  if (!pendingActorEventDraftId) return;
  sessionStorage.removeItem(`da0.pending-actor-event:${pendingActorEventDraftId}`);
  pendingActorEventDraft = null;
  state.pendingActorEventId = null;
}

async function handleNavigationChoice(choice) {
  const url = pendingEditorNavigationUrl;
  if (!url || choice === "cancel") {
    closeNavigationDialog();
    return;
  }
  if (choice === "discard") {
    discardPendingActorEventDraft();
    state.dirty = false;
    location.assign(url);
    return;
  }
  const buttons = $("unsaved-navigation-dialog").querySelectorAll("button");
  buttons.forEach((button) => { button.disabled = true; });
  const saved = await save();
  buttons.forEach((button) => { button.disabled = false; });
  if (saved) location.assign(url);
}

async function renew() {
  const response = await fetch(editorApiPath("/api/session-token"), {
    headers: {"X-Event-Editor-Client": CLIENT},
  });
  if (!response.ok) return false;
  token = (await response.json()).token;
  const url = new URL(location.href);
  url.searchParams.set("token", token);
  history.replaceState(null, "", url);
  configureEditorNavigation();
  return true;
}

async function api(path, options = {}, retry = true) {
  const response = await fetch(editorApiPath(path), {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Event-Editor-Token": token,
      ...(options.headers || {}),
    },
  });
  if (response.status === 403 && retry && await renew()) {
    return api(path, options, false);
  }
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || `HTTP ${response.status}`);
  return value;
}

function toast(message) {
  const node = $("toast");
  node.textContent = message;
  node.classList.add("visible");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove("visible"), 2400);
}

function snapshot() {
  return JSON.stringify({
    data: state.data,
    flags: state.flags,
    messages: state.messages,
    missions: state.missions,
    selectedMission: state.selectedMission,
    selectedFlag: state.selectedFlag,
    selectedEvent: state.selectedEvent,
    selectedMessage: state.selectedMessage,
    mode: state.mode,
    pendingActorEventId: state.pendingActorEventId,
  });
}

function begin() {
  state.history.push(snapshot());
  if (state.history.length > 100) state.history.shift();
  state.future = [];
}

function commit(change) {
  begin();
  change();
  state.dirty = true;
  normalize();
  render();
  schedule();
}

function restore(value) {
  const restored = JSON.parse(value);
  state.data = restored.data;
  state.flags = restored.flags;
  state.messages = restored.messages;
  state.missions = restored.missions || [];
  state.selectedMission = restored.selectedMission || 0;
  state.selectedFlag = restored.selectedFlag || 0;
  state.selectedEvent = restored.selectedEvent;
  state.selectedMessage = restored.selectedMessage;
  state.mode = restored.mode;
  state.pendingActorEventId = restored.pendingActorEventId || null;
  normalize();
  state.dirty = true;
  render();
  schedule(0);
}

function undo() {
  if (!state.history.length) return;
  state.future.push(snapshot());
  restore(state.history.pop());
}

function redo() {
  if (!state.future.length) return;
  state.history.push(snapshot());
  restore(state.future.pop());
}

function normalize() {
  if (!Array.isArray(state.missions)) state.missions = [];
  state.selectedMission = Math.max(0, Math.min(state.selectedMission, state.missions.length - 1));
  if (!Array.isArray(state.flags)) state.flags = [];
  state.selectedFlag = Math.max(0, Math.min(state.selectedFlag || 0, state.flags.length - 1));
  if (!Array.isArray(state.data.events)) state.data.events = [];
  if (!Array.isArray(state.messages)) state.messages = [];
  if (!LIST_TABS.includes(state.mode)) state.mode = "event";
  state.selectedEvent = Math.max(
    0,
    Math.min(state.selectedEvent, state.data.events.length - 1),
  );
  state.selectedMessage = Math.max(
    0,
    Math.min(state.selectedMessage, state.messages.length - 1),
  );
  for (const event of state.data.events) {
    if (!Array.isArray(event.commands)) event.commands = [];
  }
}

function currentFlag() {
  return state.flags[state.selectedFlag] || null;
}

function currentEvent() {
  return state.data.events[state.selectedEvent] || null;
}

function currentMission() {
  return state.missions[state.selectedMission] || null;
}

function currentMessage() {
  if (state.mode === "mission") return state.messages.find((message) => message.message_id === currentMission()?.message_id) || null;
  return state.messages[state.selectedMessage] || null;
}

function fullFlags() {
  return state.flags
    .filter((item) => item && typeof item.flag_id === "string")
    .map((item) => item.flag_id)
    .sort();
}

function messageIds() {
  return state.messages
    .filter((item) => item && typeof item.message_id === "string")
    .map((item) => item.message_id)
    .sort();
}

function renderMessagePreview(messageId) {
  const message = state.messages.find((item) => item?.message_id === messageId);
  let content = '<p class="message-preview-status">メッセージを選択してください。</p>';
  let modifier = " empty";
  if (messageId && !message) {
    content = '<p class="message-preview-status">メッセージが見つかりません。</p>';
    modifier = " missing";
  } else if (message) {
    const lines = Array.isArray(message.text_ja)
      ? message.text_ja.filter((line) => typeof line === "string")
      : [];
    if (lines.some((line) => line.trim())) {
      content = lines.map((line) => `<p>${line.trim() ? esc(line) : "<br>"}</p>`).join("");
      modifier = "";
    } else {
      content = '<p class="message-preview-status">日本語は未入力です。</p>';
    }
  }
  return field(
    "日本語プレビュー",
    `<div class="message-preview${modifier}" data-message-preview aria-live="polite">${content}</div>`,
  );
}

function messagePortraitPosition(message) {
  if (Number.isInteger(message.portrait_x) && Number.isInteger(message.portrait_y)) {
    return {x: message.portrait_x, y: message.portrait_y, characterKey: null};
  }
  const characterKey = message.portrait_character_key;
  const face = state.faceSheet?.character_faces?.find(
    (item) => item.character_key === characterKey,
  );
  return face ? {x: face.x, y: face.y, characterKey} : null;
}

function renderFacePicker(message) {
  const sheet = state.faceSheet;
  if (!sheet || !sheet.width || !sheet.height || !sheet.face_size) {
    return '<div class="empty">顔画像を読み込めません。</div>';
  }
  const selected = messagePortraitPosition(message);
  const columns = Math.floor(sheet.width / sheet.face_size);
  const rows = Math.floor(sheet.height / sheet.face_size);
  const cells = [];
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      const x = column * sheet.face_size;
      const y = row * sheet.face_size;
      const character = sheet.character_faces?.find(
        (item) => item.x === x && item.y === y,
      );
      const isSelected = selected?.x === x && selected?.y === y;
      const label = character
        ? `${character.character_key}（${x}, ${y}）`
        : `顔（${x}, ${y}）`;
      cells.push(`<button type="button" class="face-cell${isSelected ? " selected" : ""}" data-action="select-message-face" data-face-x="${x}" data-face-y="${y}" aria-label="${esc(label)}" title="${esc(label)}" aria-pressed="${isSelected}"></button>`);
    }
  }
  const scale = 2;
  return `<div class="face-picker">
    <div class="face-picker-toolbar"><button type="button" class="${selected ? "" : "selected"}" data-action="select-message-face" data-face-none="true" aria-pressed="${!selected}">顔なし</button></div>
    <div class="face-sheet" style="width:${sheet.width * scale}px;height:${sheet.height * scale}px;--face-columns:${columns};--face-rows:${rows};--face-cell:${sheet.face_size * scale}px">
      <img src="${esc(faceSheetUrl())}" width="${sheet.width * scale}" height="${sheet.height * scale}" alt="faces.png 顔一覧">
      <div class="face-grid">${cells.join("")}</div>
    </div>
  </div>`;
}

function renderFacePickerControl(message) {
  const selected = messagePortraitPosition(message);
  const scale = 2;
  const preview = selected
    ? `<span class="selected-face-preview" role="img" aria-label="選択中の顔" style="background-image:url('${esc(faceSheetUrl())}');background-position:-${selected.x * scale}px -${selected.y * scale}px;background-size:${state.faceSheet.width * scale}px ${state.faceSheet.height * scale}px"></span>`
    : "";
  return `<div class="face-picker-control"><button type="button" data-action="open-face-picker">顔を選択</button>${preview}</div>`;
}

function noteSummary(note) {
  const characters = Array.from((note || "").replace(/\s+/g, " ").trim());
  return characters.slice(0, 20).join("") + (characters.length > 20 ? "…" : "");
}

function flagOptions(selected) {
  return options(fullFlags(), selected, "選択してください", (id) => {
    const summary = noteSummary(state.flags.find((flag) => flag.flag_id === id)?.note);
    return summary ? `${id} — ${summary}` : id;
  });
}

function options(values, selected, empty = "選択してください", label = (value) => value) {
  const all = [...values];
  if (selected && !all.includes(selected)) all.push(selected);
  return `<option value="" ${selected ? "" : "selected"}>${empty}</option>`
    + all.map((value) => `<option value="${esc(value)}" ${value === selected ? "selected" : ""}>${esc(label(value))}${values.includes(value) ? "" : "（不明）"}</option>`).join("");
}

function filteredList(kind) {
  const fieldName = kind === "flag" ? "flag_id" : kind === "message" ? "message_id" : "id";
  const query = (state.filterText || "").trim().toLowerCase();
  return listForKind(kind)
    .map((item, index) => ({item, index}))
    .filter(({item}) => String(item[fieldName] || "").toLowerCase().includes(query));
}

function listEnd(kind, rows, emptyLabel) {
  return rows.length
    ? renderListDropZone(kind, rows.at(-1).index + 1)
    : `<div class="empty">${state.filterText?.trim() ? "一致するIDはありません。" : emptyLabel}</div>`;
}

function setIdFilter(value) {
  state.filterText = value;
  clearListItemDrag();
  renderLists();
}

function eventIdPrefix() {
  const map = pendingActorEventDraft?.data;
  if (map) return map.area_parent_id || map.map_id;
  return currentEvent()?.id.split(".")[0] || "common";
}

function canSave() {
  return Boolean(state.data) && (state.dirty || state.diagnostics.some((item) => item.severity === "error"));
}

function updateStatus() {
  const errors = state.diagnostics.some((item) => item.severity === "error");
  const node = $("save-state");
  node.className = `pill ${errors ? "error" : state.dirty ? "dirty" : "saved"}`;
  node.textContent = errors ? "要修正" : state.dirty ? "未保存" : "保存済み";
  $("save").disabled = !canSave();
  $("undo").disabled = !state.history.length;
  $("redo").disabled = !state.future.length;
}

function listForKind(kind) {
  if (kind === "flag") return state.flags;
  if (kind === "event") return state.data.events;
  if (kind === "message") return state.messages;
  if (kind === "mission") return state.missions;
  return null;
}

function insertListItem(kind, item) {
  const items = listForKind(kind);
  const selectionKey = `selected${kind[0].toUpperCase()}${kind.slice(1)}`;
  const selectedIndex = state[selectionKey];
  const insertionIndex = Number.isInteger(selectedIndex) && selectedIndex >= 0 && selectedIndex < items.length
    ? selectedIndex + 1 : items.length;
  items.splice(insertionIndex, 0, item);
  const fieldName = kind === "flag" ? "flag_id" : kind === "message" ? "message_id" : "id";
  if (!String(item[fieldName] || "").toLowerCase().includes((state.filterText || "").trim().toLowerCase())) {
    state.filterText = "";
  }
  state[selectionKey] = insertionIndex;
}

function moveListItem(kind, sourceIndex, targetIndex) {
  const items = listForKind(kind);
  if (!items || !items[sourceIndex] || targetIndex < 0 || targetIndex > items.length) {
    return false;
  }
  let insertionIndex = targetIndex;
  if (sourceIndex < insertionIndex) insertionIndex -= 1;
  if (sourceIndex === insertionIndex) return false;

  const selectedFlag = currentFlag();
  const selectedMission = currentMission();
  const selectedEvent = currentEvent();
  const selectedMessage = currentMessage();
  commit(() => {
    const [item] = items.splice(sourceIndex, 1);
    items.splice(insertionIndex, 0, item);
    if (selectedFlag) state.selectedFlag = state.flags.indexOf(selectedFlag);
    if (selectedMission) state.selectedMission = state.missions.indexOf(selectedMission);
    if (selectedEvent) state.selectedEvent = state.data.events.indexOf(selectedEvent);
    if (selectedMessage) state.selectedMessage = state.messages.indexOf(selectedMessage);
  });
  return true;
}

function renderListDropZone(kind, index) {
  return `<div class="list-drop-zone" data-list-drop-kind="${kind}" data-list-drop-index="${index}"></div>`;
}

function renderLists() {
  document.querySelectorAll("[data-list-tab]").forEach((button) => {
    const active = button.dataset.listTab === state.mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll("[data-list-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.listPanel !== state.mode;
  });

  const flags = filteredList("flag");
  const events = filteredList("event");
  const missions = filteredList("mission");
  const messages = filteredList("message");
  $("flags").className = "list";
  $("flags").innerHTML = flags.map(({item: flag, index}) => `
    ${renderListDropZone("flag", index)}
    <div class="list-item reorderable-list-item ${state.mode === "flag" && index === state.selectedFlag ? "active" : ""}" data-list-item-kind="flag">
      <span class="list-drag-handle" draggable="true" role="button" aria-label="${esc(flag.flag_id)}を移動" title="ドラッグして移動" data-list-item-drag data-list-kind="flag" data-index="${index}">⠿</span>
      <button type="button" class="list-item-select" data-action="select-flag" data-index="${index}">
        <strong>${esc(flag.flag_id)}</strong>
        <small>${esc(noteSummary(flag.note) || "メモなし")}</small>
      </button>
    </div>
  `).join("") + listEnd("flag", flags, "フラグはありません。");

  $("events").className = "list";
  $("events").innerHTML = events.map(({item: event, index}) => `
    ${renderListDropZone("event", index)}
    <div class="list-item reorderable-list-item ${state.mode === "event" && index === state.selectedEvent ? "active" : ""}" data-list-item-kind="event">
      <span class="list-drag-handle" draggable="true" role="button" aria-label="${esc(event.id)}を移動" title="ドラッグして移動" data-list-item-drag data-list-kind="event" data-index="${index}">⠿</span>
      <button type="button" class="list-item-select" data-action="select-event" data-index="${index}">
        <strong>${esc(event.id)}</strong>
        <small>${event.commands?.length || 0} commands · ${esc(event.note || "メモなし")}</small>
      </button>
    </div>
  `).join("") + listEnd("event", events, "イベントはありません。");

  if ($("missions")) {
    $("missions").className = "list";
    $("missions").innerHTML = missions.map(({item: mission, index}) => `
      ${renderListDropZone("mission", index)}
      <div class="list-item reorderable-list-item ${state.mode === "mission" && index === state.selectedMission ? "active" : ""}" data-list-item-kind="mission">
        <span class="list-drag-handle" draggable="true" role="button" aria-label="${esc(mission.id)}を移動" title="ドラッグして表示順を変更" data-list-item-drag data-list-kind="mission" data-index="${index}">⠿</span>
        <button type="button" class="list-item-select" data-action="select-mission" data-index="${index}"><strong>${index + 1}. ${esc(mission.id)}</strong><small>${esc(mission.note || mission.message_id)}</small></button>
      </div>
    `).join("") + listEnd("mission", missions, "ミッションはありません。");
  }

  $("messages").className = "list";
  $("messages").innerHTML = messages.map(({item: message, index}) => `
    ${renderListDropZone("message", index)}
    <div class="list-item reorderable-list-item ${state.mode === "message" && index === state.selectedMessage ? "active" : ""}" data-list-item-kind="message">
      <span class="list-drag-handle" draggable="true" role="button" aria-label="${esc(message.message_id)}を移動" title="ドラッグして移動" data-list-item-drag data-list-kind="message" data-index="${index}">⠿</span>
      <button type="button" class="list-item-select" data-action="select-message" data-index="${index}">
        <strong>${esc(message.message_id)}</strong>
        <small>${esc((message.text_ja || [])[0] || "日本語未入力")}</small>
      </button>
    </div>
  `).join("") + listEnd("message", messages, "メッセージはありません。");
}

function field(label, html, full = false) {
  return `<div class="field ${full ? "full" : ""}"><label>${label}</label>${html}</div>`;
}

function commandAt(path) {
  if (path === "mission") return currentMission();
  let commands = currentEvent().commands;
  let command = null;
  const parts = path.split("/").filter(Boolean);
  for (const part of parts) {
    if (/^\d+$/.test(part)) command = commands[Number(part)];
    else commands = command[part];
  }
  return command;
}

function listAt(path) {
  if (!path) return currentEvent().commands;
  const parts = path.split("/").filter(Boolean);
  const branch = parts.pop();
  return commandAt(parts.join("/"))[branch];
}

function commandPath(listPath, index) {
  return listPath ? `${listPath}/${index}` : String(index);
}

function isDescendantList(sourceListPath, sourceIndex, targetListPath) {
  return targetListPath.startsWith(`${commandPath(sourceListPath, sourceIndex)}/`);
}

function moveCommand(sourceListPath, sourceIndex, targetListPath, targetIndex) {
  const source = listAt(sourceListPath);
  const target = listAt(targetListPath);
  if (!source[sourceIndex] || targetIndex < 0 || targetIndex > target.length) return false;
  if (isDescendantList(sourceListPath, sourceIndex, targetListPath)) return false;

  let insertionIndex = targetIndex;
  if (source === target && sourceIndex < insertionIndex) insertionIndex -= 1;
  if (source === target && sourceIndex === insertionIndex) return false;

  commit(() => {
    const [command] = source.splice(sourceIndex, 1);
    target.splice(insertionIndex, 0, command);
  });
  return true;
}

function conditionAt(command, path) {
  let value = command;
  for (const part of path.split("/").filter(Boolean)) {
    value = /^\d+$/.test(part) ? value[Number(part)] : value[part];
  }
  return value;
}

function renderCondition(condition, commandPath, path) {
  const type = condition?.type || "flag_set";
  let fields = "";
  if (type === "launch_mode") {
    fields = field("起動モード", `<select data-cond-command="${commandPath}" data-cond-path="${path}" data-cond-field="mode">${[["normal", "通常モード"], ["exhibition", "試遊版モード"], ["demo", "体験版モード"], ["beta", "βテスト版モード"]].map(([value, label]) => `<option value="${value}" ${value === condition.mode ? "selected" : ""}>${label}</option>`).join("")}</select>`, true);
  } else if (type === "flag_set") {
    fields = field("フラグ", `<select data-cond-command="${commandPath}" data-cond-path="${path}" data-cond-field="flag_id">${flagOptions(condition.flag_id)}</select>`, true);
  } else if (type === "member_in_party") {
    fields = field("メンバー", `<select data-cond-command="${commandPath}" data-cond-path="${path}" data-cond-field="character_key">${options(state.catalogs.character_keys || [], condition.character_key)}</select>`, true);
  } else if (type === "item_at_least") {
    fields = field("アイテム", `<select data-cond-command="${commandPath}" data-cond-path="${path}" data-cond-field="item_key">${options(state.catalogs.item_keys || [], condition.item_key)}</select>`)
      + field("個数", `<input type="number" min="1" value="${Number(condition.quantity) || 1}" data-cond-command="${commandPath}" data-cond-path="${path}" data-cond-field="quantity">`);
  } else if (type === "not") {
    fields = `<div class="condition-children">${renderCondition(condition.condition, commandPath, `${path}/condition`)}</div>`;
  } else if (type === "all" || type === "any") {
    fields = `<div class="condition-children">${(condition.conditions || []).map((child, index) => `
      <div>${renderCondition(child, commandPath, `${path}/conditions/${index}`)}<button class="danger icon" data-action="delete-condition" data-command-path="${commandPath}" data-condition-path="${path}" data-index="${index}">条件を削除</button></div>
    `).join("")}<button class="icon" data-action="add-condition" data-command-path="${commandPath}" data-condition-path="${path}">子条件を追加</button></div>`;
  }
  const types = ["flag_set", "member_in_party", "any_member_dead", "item_at_least", "launch_mode", "all", "any", "not"];
  return `<div class="condition">
    <div class="field"><label>条件</label><select data-cond-command="${commandPath}" data-cond-path="${path}" data-cond-field="type">${types.map((value) => `<option value="${value}" ${value === type ? "selected" : ""}>${value === "any_member_dead" ? "誰かが死亡状態のとき" : value === "launch_mode" ? "起動モード" : value}</option>`).join("")}</select></div>
    <div class="command-fields compact">${fields}</div>
  </div>`;
}

function renderCommand(command, path, listPath, index) {
  const type = command.command;
  let fields = "";
  const attr = (name) => `data-command-path="${path}" data-command-field="${name}"`;
  if (type === "set_flag") {
    fields = field("フラグ", `<select ${attr("flag_id")}>${flagOptions(command.flag_id)}</select>`, true);
  } else if (type === "join_party" || type === "leave_party") {
    fields = field("キャラクター", `<select ${attr("character_key")}>${options(state.catalogs.character_keys || [], command.character_key)}</select>`, true);
  } else if (type === "give_item" || type === "take_item") {
    fields = field("アイテム", `<select ${attr("item_key")}>${options(state.catalogs.item_keys || [], command.item_key)}</select>`)
      + field("個数", `<input type="number" min="1" value="${Number(command.quantity) || 1}" ${attr("quantity")}>`);
    if (type === "give_item") {
      fields += field("入手メッセージを表示", `<input type="checkbox" ${attr("show_message")} ${command.show_message === true ? "checked" : ""}>`);
    }
  } else if (type === "message") {
    fields = field("メッセージID", `<select ${attr("message_id")}>${options(messageIds(), command.message_id)}</select>`)
      + renderMessagePreview(command.message_id);
  } else if (type === "play_se") {
    fields = field("SE", `<select ${attr("se_id")}>${options(state.catalogs.se_ids || [], command.se_id)}</select>`, true);
  } else if (type === "change_bgm") {
    fields = field("BGM", `<select ${attr("bgm_id")}>${options(state.catalogs.bgm_ids || [], command.bgm_id)}</select>`, true);
  } else if (type === "stop_bgm") {
    fields = '<p class="command-description full">BGMをフェードアウトして停止します。</p>';
  } else if (type === "reset_game") {
    fields = '<p class="command-description full">現在のプレイを終了してタイトル画面に戻ります。後続のコマンドは実行しません。</p>';
  } else if (type === "flash_screen") {
    fields = field("色", `<select ${attr("color")}>${options(["white"], command.color)}</select>`, true);
  } else if (type === "change_brightness") {
    fields = field("明るさ", `<select ${attr("percent")}>${[0, 25, 50, 75, 100].map((value) => `<option value="${value}" ${command.percent === value ? "selected" : ""}>${value}%</option>`).join("")}</select>`, true);
  } else if (type === "wait" || type === "shake_screen") {
    const label = type === "wait" ? "待機時間" : "振動時間";
    fields = field(`${label}（フレーム・6フレーム単位）`, `<input type="number" min="6" step="6" value="${Number(command.frames) || 6}" ${attr("frames")}>`, true);
  } else if (type === "recover_party") {
    fields = '<p class="command-description full">パーティ全員のHP・MP・状態異常を全て回復します。</p>';
  } else if (type === "open_shop") {
    fields = field("ショップID", `<select ${attr("shop_key")}>${options(state.catalogs.shop_keys || [], command.shop_key)}</select>`, true);
  } else if (type === "start_battle") {
    fields = field("バトルID", `<input ${attr("battle_id")} value="${esc(command.battle_id || "")}" placeholder="例: shrine_guard">`, true)
      + `<div class="full"><label>敵編成（1〜5体）</label>${(command.monster_keys || []).map((key, monsterIndex) => `
        <div class="add-row"><select data-battle-monster-index="${monsterIndex}" data-command-path="${esc(path)}">${options(state.catalogs.monster_keys || [], key)}</select>
        <button class="danger icon" data-action="remove-battle-monster" data-command-path="${esc(path)}" data-index="${monsterIndex}">削除</button></div>
      `).join("")}<button data-action="add-battle-monster" data-command-path="${esc(path)}" ${(command.monster_keys || []).length >= 5 ? "disabled" : ""}>敵を追加</button></div>`;
  } else if (["move_party", "move_actor", "face_party", "face_actor"].includes(type)) {
    fields = (type.endsWith("_actor") ? field("actor ID", `<select ${attr("actor_id")}>${options(state.catalogs.actor_ids || [], command.actor_id)}</select>`) : "")
      + field("方向", `<select ${attr("direction")}>${options(["up", "right", "down", "left"], command.direction)}</select>`);
    if (type.startsWith("move_")) {
      fields += field("歩数", `<input type="number" min="1" max="255" value="${Number(command.steps) || 1}" ${attr("steps")}>`);
    }
  } else if (type === "branch") {
    fields = `<div class="full">${renderCondition(command.condition, path, "condition")}${renderBranch(command.then, path, "then")}${renderBranch(command.else, path, "else")}</div>`;
  } else if (type === "end_event") {
    fields = '<p class="command-description full">ここでイベント全体を終了し、後続のコマンドを実行しません。</p>';
  }
  const label = COMMAND_OPTIONS.find(([value]) => value === type)?.[1] || type;
  const typeOptions = (COMMAND_OPTIONS.some(([value]) => value === type)
    ? "" : `<option value="${esc(type)}" selected>未対応: ${esc(type)}</option>`)
    + COMMAND_OPTIONS.map(([value, name]) =>
    `<option value="${value}" ${value === type ? "selected" : ""}>${name}</option>`,
  ).join("");
  return `<article class="command" data-command-path="${esc(path)}">
    <div class="command-head"><div class="command-title"><span class="drag-handle" draggable="true" role="button" aria-label="${esc(label)}を移動" title="ドラッグして移動" data-command-drag data-list-path="${esc(listPath)}" data-index="${index}">⠿</span><code>${index + 1}. ${esc(label)}</code></div><button class="danger icon" data-action="delete-command" data-list-path="${esc(listPath)}" data-index="${index}">削除</button></div>
    <div class="command-fields">${field("コマンド", `<select data-command-type="${esc(path)}">${typeOptions}</select>`, true)}${fields}</div>
  </article>`;
}

function renderBranch(commands, parentPath, name) {
  const path = `${parentPath}/${name}`;
  return `<div class="branch"><h3>${name}</h3>${renderCommandList(commands, path, "コマンドなし")}${addCommand(path)}</div>`;
}

function renderDropZone(listPath, index, emptyMessage = "") {
  return `<div class="command-drop-zone ${emptyMessage ? "empty-list" : ""}" data-drop-list-path="${esc(listPath)}" data-drop-index="${index}">${emptyMessage ? `<span>${esc(emptyMessage)}</span>` : ""}</div>`;
}

function renderCommandList(commands, listPath, emptyMessage) {
  const content = commands.map((command, index) =>
    `${renderDropZone(listPath, index)}${renderCommand(command, commandPath(listPath, index), listPath, index)}`,
  ).join("");
  return `<div class="commands" data-command-list="${esc(listPath)}">${content}${renderDropZone(listPath, commands.length, commands.length ? "" : emptyMessage)}</div>`;
}

function addCommand(listPath = "") {
  return `<div class="add-row"><button data-action="add-command" data-list-path="${esc(listPath)}">コマンド追加</button></div>`;
}

function renderEventEditor() {
  const event = currentEvent();
  if (!event) {
    $("event-editor").className = "empty";
    $("event-editor").innerHTML = "イベントを選択してください。";
    return;
  }
  $("event-editor").className = "";
  $("event-editor").innerHTML = `
    <div class="event-meta">${field("イベントID", `<input data-event-field="id" value="${esc(event.id)}">`)}${field("制作メモ", `<input data-event-field="note" value="${esc(event.note || "")}">`)}<button class="danger" data-action="delete-event">イベントを削除</button></div>
    <div class="event-meta">${field("バトル開始時に発動", `<input type="checkbox" data-event-battle-enabled ${event.battle_start_id !== undefined ? "checked" : ""}>`)}${event.battle_start_id !== undefined ? field("対象バトルID", `<input data-event-field="battle_start_id" value="${esc(event.battle_start_id)}" placeholder="開始コマンドと同じID">`) : ""}</div>
    <div class="heading"><h2>${esc(event.id)}</h2><span class="pill">${event.commands.length} commands</span></div>
    ${renderCommandList(event.commands, "", "コマンドはありません。")}
    ${addCommand()}
  `;
}

function renderMessageEditor() {
  const message = currentMessage();
  if (!message) {
    $("event-editor").className = "empty";
    $("event-editor").innerHTML = "メッセージを選択してください。";
    return;
  }
  $("event-editor").className = "";
  $("event-editor").innerHTML = `
    <div class="heading"><h2>メッセージ編集</h2><button class="danger" data-action="delete-message">メッセージを削除</button></div>
    <div class="message-form">
      ${field("メッセージID", `<input data-message-field="message_id" value="${esc(message.message_id)}">`, true)}
      ${field("顔（任意）", renderFacePickerControl(message), true)}
      ${field("日本語（1行ごとにゲーム内の1行）", `<textarea rows="6" data-message-field="text_ja">${esc((message.text_ja || []).join("\n"))}</textarea>`, true)}
      ${field("英語（未翻訳なら空欄）", `<textarea rows="6" data-message-field="text_en">${esc((message.text_en || []).join("\n"))}</textarea>`, true)}
      ${field("簡体字中国語（未翻訳なら空欄）", `<textarea rows="6" data-message-field="text_zhcn">${esc((message.text_zhcn || []).join("\n"))}</textarea>`, true)}
    </div>
  `;
}

function renderMissionEditor() {
  const mission = currentMission();
  $("event-editor").className = mission ? "" : "empty";
  if (!mission) {
    $("event-editor").innerHTML = "ミッションを追加・選択してください。";
    return;
  }
  const message = currentMessage();
  $("event-editor").innerHTML = `
    <div class="event-meta">${field("ミッションID", `<input data-mission-field="id" value="${esc(mission.id)}">`)}${field("制作メモ", `<input data-mission-field="note" value="${esc(mission.note || "")}">`)}<button class="danger" data-action="delete-mission">ミッションを削除</button></div>
    <div class="heading"><h2>表示条件</h2><button data-action="toggle-mission-condition">${mission.condition ? "条件を外す（常に表示）" : "条件を設定"}</button></div>
    ${mission.condition ? renderCondition(mission.condition, "mission", "condition") : '<p class="compact">常に表示します。</p>'}
    <div class="heading compact"><h2>メッセージ</h2><button data-action="new-mission-message">専用メッセージを新規作成</button></div>
    ${field("メッセージID（イベントと共通）", `<select data-mission-field="message_id">${options(messageIds(), mission.message_id)}</select>`, true)}
    ${renderMessagePreview(mission.message_id)}
    ${message ? `<div class="message-form compact">${[
      ["text_ja", "日本語"], ["text_en", "英語（未翻訳なら空欄）"], ["text_zhcn", "簡体字中国語（未翻訳なら空欄）"],
    ].map(([key, label]) => field(label + "（1行ごとにゲーム内の1行）", `<textarea rows="5" data-message-field="${key}">${esc((message[key] || []).join("\n"))}</textarea>`, true)).join("")}</div>` : ""}
  `;
}

function newMissionMessage(mission) {
  const message = {message_id: uniqueId(`mission.${mission.id}`, state.messages, "message_id"), text_ja: ["ミッションの内容"], text_en: [], text_zhcn: []};
  state.messages.push(message);
  mission.message_id = message.message_id;
}

function renderFlagEditor() {
  const flag = currentFlag();
  $("event-editor").className = flag ? "" : "empty";
  if (!flag) {
    $("event-editor").innerHTML = "グローバルフラグを追加・選択してください。";
    return;
  }
  $("event-editor").innerHTML = `
    <div class="heading"><h2>グローバルフラグ編集</h2><button class="danger" data-action="delete-flag">フラグを削除</button></div>
    <div class="message-form">
      ${field("グローバルID", `<input data-flag-field="flag_id" value="${esc(flag.flag_id)}">`, true)}
      ${field("制作メモ", `<textarea rows="6" data-flag-field="note">${esc(flag.note || "")}</textarea>`, true)}
    </div>
  `;
}

function renderEditor() {
  if (state.mode === "mission") {
    renderMissionEditor();
  } else if (state.mode === "message") {
    renderMessageEditor();
  } else if (state.mode === "flag") {
    renderFlagEditor();
  } else {
    renderEventEditor();
  }
}

function renderIssues() {
  const errors = state.diagnostics.filter((item) => item.severity === "error").length;
  const warnings = state.diagnostics.filter((item) => item.severity === "warning").length;
  $("issue-count").textContent = errors ? `${errors} error / ${warnings} warning` : `${warnings} warning`;
  $("issues").innerHTML = state.diagnostics.map((item) => `
    <div class="issue ${item.severity}"><strong>${esc(item.path)} · ${esc(item.code)}</strong><p>${esc(item.message)}</p></div>
  `).join("") || '<div class="empty">問題はありません。</div>';
  updateStatus();
}

function render() {
  $("id-filter").value = state.filterText;
  renderLists();
  renderEditor();
  renderIssues();
  saveUiSettings();
}

function addEvent(linkToPendingActor = false) {
  let createdEvent = null;
  commit(() => {
    createdEvent = {id: uniqueId(`${eventIdPrefix()}.event`, state.data.events), note: "", commands: []};
    insertListItem("event", createdEvent);
    state.mode = "event";
    if (linkToPendingActor) state.pendingActorEventId = createdEvent.id;
  });
  return createdEvent;
}

function defaultCondition(type = "flag_set") {
  if (type === "launch_mode") return {type, mode: "normal"};
  if (type === "any_member_dead") return {type};
  if (type === "flag_set") return {type, flag_id: fullFlags()[0] || ""};
  if (type === "member_in_party") return {type, character_key: state.catalogs.character_keys?.[0] || ""};
  if (type === "item_at_least") return {type, item_key: state.catalogs.item_keys?.[0] || "", quantity: 1};
  if (type === "not") return {type, condition: defaultCondition()};
  return {type, conditions: [defaultCondition()]};
}

function defaultCommand(type) {
  const one = (key, values) => ({command: type, [key]: values?.[0] || ""});
  if (type === "set_flag") return one("flag_id", fullFlags());
  if (type === "join_party" || type === "leave_party") return one("character_key", state.catalogs.character_keys);
  if (type === "give_item") return {...one("item_key", state.catalogs.item_keys), quantity: 1, show_message: false};
  if (type === "take_item") return {...one("item_key", state.catalogs.item_keys), quantity: 1};
  if (type === "message") return one("message_id", messageIds());
  if (type === "play_se") return one("se_id", state.catalogs.se_ids);
  if (type === "change_bgm") return one("bgm_id", state.catalogs.bgm_ids);
  if (type === "stop_bgm" || type === "reset_game") return {command: type};
  if (type === "flash_screen") return {command: type, color: "white"};
  if (type === "change_brightness") return {command: type, percent: 100};
  if (type === "wait" || type === "shake_screen") return {command: type, frames: 6};
  if (type === "recover_party") return {command: type};
  if (type === "open_shop") return one("shop_key", state.catalogs.shop_keys);
  if (type === "start_battle") return {command: type, battle_id: "battle_1", monster_keys: [state.catalogs.monster_keys?.[0] || ""]};
  if (type === "move_party") return {command: type, direction: "down", steps: 1};
  if (type === "move_actor") return {command: type, actor_id: state.catalogs.actor_ids?.[0] || "", direction: "down", steps: 1};
  if (type === "face_party") return {command: type, direction: "down"};
  if (type === "face_actor") return {command: type, actor_id: state.catalogs.actor_ids?.[0] || "", direction: "down"};
  if (type === "end_event") return {command: type};
  return {command: "branch", condition: defaultCondition(), then: [], else: []};
}

function addDefaultCommand(listPath) {
  const list = listAt(listPath);
  const path = commandPath(listPath, list.length);
  commit(() => { list.push(defaultCommand("message")); });
  document.querySelector(`select[data-command-type="${CSS.escape(path)}"]`)?.focus();
}

function changeCommandType(path, type) {
  if (!COMMAND_OPTIONS.some(([value]) => value === type)) return;
  const parts = path.split("/");
  const index = Number(parts.pop());
  const list = listAt(parts.join("/"));
  if (!list[index] || list[index].command === type) return;
  commit(() => { list[index] = defaultCommand(type); });
}

function uniqueId(base, records, fieldName = "id") {
  const used = new Set(records.map((item) => item[fieldName]));
  let number = 1;
  while (used.has(`${base}_${number}`)) number += 1;
  return `${base}_${number}`;
}

function linesFromTextarea(value) {
  if (!value) return [];
  const lines = value.replaceAll("\r", "").split("\n");
  let start = 0;
  let end = lines.length;
  while (start < end && !lines[start].trim()) start += 1;
  while (end > start && !lines[end - 1].trim()) end -= 1;
  return lines.slice(start, end);
}

function requestBody() {
  return JSON.stringify({
    data: state.data,
    flags: state.flags,
    messages: state.messages,
    missions: state.missions,
  });
}

function schedule(delay = 100) {
  clearTimeout(state.timer);
  const revision = ++state.revision;
  state.timer = setTimeout(async () => {
    try {
      const result = await api("/api/validate", {method: "POST", body: requestBody()});
      if (revision !== state.revision) return;
      state.diagnostics = result.diagnostics;
      renderIssues();
    } catch (error) {
      toast(error.message);
    }
  }, delay);
}

async function save() {
  if (!canSave()) return false;
  try {
    const result = await api("/api/save", {method: "POST", body: requestBody()});
    state.diagnostics = result.diagnostics;
    if (result.saved) {
      const linkedActor = await savePendingActorEventLink();
      state.dirty = false;
      state.history = [];
      state.future = [];
      toast(linkedActor
        ? `イベントを保存し、${linkedActor.mapId}のactor ${linkedActor.actorId}へ紐づけました。`
        : "イベント・ミッション・メッセージを保存し、ゲーム用データを生成しました。");
    } else {
      toast("エラーを修正してください。");
    }
    render();
    return Boolean(result.saved);
  } catch (error) {
    toast(error.message);
    return false;
  }
}

function applyDocument(payload, selectedEventId = null, selectedListTab = "event") {
  clearTimeout(state.timer);
  state.revision += 1;
  state.data = payload.data;
  state.flags = payload.flags;
  state.messages = payload.messages;
  state.missions = payload.missions || [];
  state.selectedMission = 0;
  state.catalogs = payload.catalogs;
  state.faceSheet = payload.face_sheet;
  state.diagnostics = payload.diagnostics;
  const requestedEventIndex = selectedEventId === null
    ? -1
    : state.data.events.findIndex((event) => event.id === selectedEventId);
  state.selectedEvent = requestedEventIndex >= 0 ? requestedEventIndex : 0;
  state.selectedMessage = 0;
  state.selectedFlag = 0;
  state.pendingActorEventId = null;
  state.mode = selectedEventId !== null || !LIST_TABS.includes(selectedListTab)
    ? "event"
    : selectedListTab;
  state.dirty = payload.is_new;
  state.history = [];
  state.future = [];
  normalize();
  const url = new URL(location.href);
  url.searchParams.delete("namespace");
  if (requestedEventIndex >= 0) url.searchParams.set("event", selectedEventId);
  else url.searchParams.delete("event");
  history.replaceState(null, "", url);
  render();
}

document.body.addEventListener("click", (event) => {
  const target = event.target.closest("[data-action]");
  if (!target) return;
  const action = target.dataset.action;
  if (action === "select-list-tab") {
    state.mode = target.dataset.listTab;
    render();
  } else if (action === "add-flag") {
    commit(() => {
      insertListItem("flag", {flag_id: uniqueId("flag", state.flags, "flag_id"), note: ""});
      state.mode = "flag";
    });
  } else if (action === "select-flag") {
    state.selectedFlag = Number(target.dataset.index);
    state.mode = "flag";
    render();
  } else if (action === "delete-flag") {
    commit(() => state.flags.splice(state.selectedFlag, 1));
  } else if (action === "add-mission") {
    commit(() => {
      const mission = {id: uniqueId("mission", state.missions), note: "", condition: defaultCondition(), message_id: ""};
      newMissionMessage(mission);
      insertListItem("mission", mission);
      state.mode = "mission";
    });
  } else if (action === "select-mission") {
    state.selectedMission = Number(target.dataset.index);
    state.mode = "mission";
    render();
  } else if (action === "delete-mission") {
    commit(() => state.missions.splice(state.selectedMission, 1));
  } else if (action === "toggle-mission-condition") {
    commit(() => {
      const mission = currentMission();
      if (mission.condition) delete mission.condition;
      else mission.condition = defaultCondition();
    });
  } else if (action === "new-mission-message") {
    commit(() => newMissionMessage(currentMission()));
  } else if (action === "add-event") {
    addEvent();
  } else if (action === "select-event") {
    state.selectedEvent = Number(target.dataset.index);
    state.mode = "event";
    render();
  } else if (action === "delete-event") {
    commit(() => {
      const [deleted] = state.data.events.splice(state.selectedEvent, 1);
      if (deleted?.id === state.pendingActorEventId) state.pendingActorEventId = null;
    });
  } else if (action === "add-message") {
    commit(() => {
      const base = `${eventIdPrefix()}.message`;
      insertListItem("message", {
        message_id: uniqueId(base, state.messages, "message_id"),
        text_ja: ["メッセージ"],
        text_en: [],
        text_zhcn: [],
      });
      state.mode = "message";
    });
  } else if (action === "select-message") {
    state.selectedMessage = Number(target.dataset.index);
    state.mode = "message";
    render();
  } else if (action === "delete-message") {
    commit(() => state.messages.splice(state.selectedMessage, 1));
  } else if (action === "open-face-picker") {
    $("face-picker-dialog-content").innerHTML = renderFacePicker(currentMessage());
    $("face-picker-dialog").showModal();
  } else if (action === "close-face-picker") {
    $("face-picker-dialog").close();
  } else if (action === "select-message-face") {
    commit(() => {
      const message = currentMessage();
      delete message.portrait_character_key;
      delete message.portrait_x;
      delete message.portrait_y;
      if (!target.dataset.faceNone) {
        const x = Number(target.dataset.faceX);
        const y = Number(target.dataset.faceY);
        const character = state.faceSheet?.character_faces?.find(
          (item) => item.x === x && item.y === y,
        );
        if (character) {
          message.portrait_character_key = character.character_key;
        } else {
          message.portrait_x = x;
          message.portrait_y = y;
        }
      }
    });
    $("face-picker-dialog").close();
  } else if (action === "add-command") {
    addDefaultCommand(target.dataset.listPath);
  } else if (action === "delete-command") {
    commit(() => listAt(target.dataset.listPath).splice(Number(target.dataset.index), 1));
  } else if (action === "add-battle-monster") {
    commit(() => commandAt(target.dataset.commandPath).monster_keys.push(state.catalogs.monster_keys?.[0] || ""));
  } else if (action === "remove-battle-monster") {
    commit(() => commandAt(target.dataset.commandPath).monster_keys.splice(Number(target.dataset.index), 1));
  } else if (action === "add-condition") {
    commit(() => conditionAt(commandAt(target.dataset.commandPath), target.dataset.conditionPath).conditions.push(defaultCondition()));
  } else if (action === "delete-condition") {
    commit(() => conditionAt(commandAt(target.dataset.commandPath), target.dataset.conditionPath).conditions.splice(Number(target.dataset.index), 1));
  }
});

$("event-editor").addEventListener("change", (event) => {
  const target = event.target;
  if (target.dataset.flagField) {
    commit(() => { currentFlag()[target.dataset.flagField] = target.value; });
  } else if (target.dataset.missionField) {
    commit(() => { currentMission()[target.dataset.missionField] = target.value; });
  } else if (target.dataset.eventField) {
    commit(() => {
      const eventRecord = currentEvent();
      if (target.dataset.eventField === "id" && eventRecord.id === state.pendingActorEventId) {
        state.pendingActorEventId = target.value;
      }
      eventRecord[target.dataset.eventField] = target.value;
    });
  } else if (target.dataset.eventBattleEnabled !== undefined) {
    commit(() => {
      if (target.checked) currentEvent().battle_start_id = "battle_1";
      else delete currentEvent().battle_start_id;
    });
  } else if (target.dataset.battleMonsterIndex !== undefined) {
    commit(() => { commandAt(target.dataset.commandPath).monster_keys[Number(target.dataset.battleMonsterIndex)] = target.value; });
  } else if (target.dataset.commandType !== undefined) {
    changeCommandType(target.dataset.commandType, target.value);
  } else if (target.dataset.messageField) {
    commit(() => {
      const fieldName = target.dataset.messageField;
      currentMessage()[fieldName] = fieldName.startsWith("text_")
        ? linesFromTextarea(target.value)
        : target.value;
    });
  } else if (target.dataset.commandField) {
    commit(() => {
      const command = commandAt(target.dataset.commandPath);
      const fieldName = target.dataset.commandField;
      command[fieldName] = fieldName === "show_message" ? target.checked
        : ["quantity", "steps", "frames", "percent"].includes(fieldName)
        ? Number(target.value)
        : target.value;
    });
  } else if (target.dataset.condField) {
    commit(() => {
      const command = commandAt(target.dataset.condCommand);
      const condition = conditionAt(command, target.dataset.condPath);
      const fieldName = target.dataset.condField;
      if (fieldName === "type") {
        const replacement = defaultCondition(target.value);
        Object.keys(condition).forEach((key) => delete condition[key]);
        Object.assign(condition, replacement);
      } else {
        condition[fieldName] = fieldName === "quantity" ? Number(target.value) : target.value;
      }
    });
  }
});

function clearCommandDrag() {
  draggedCommand = null;
  document.body.classList.remove("command-dragging");
  document.querySelectorAll(".command.dragging, .command-drop-zone.active, .command-drop-zone.invalid").forEach((node) => {
    node.classList.remove("dragging", "active", "invalid");
  });
}

function findDropZone(target, selector) {
  // Keep accepting the highlighted destination after the pointer leaves its frame.
  return target.closest(selector) || document.querySelector(`${selector}.active`);
}

$("event-editor").addEventListener("dragstart", (event) => {
  const handle = event.target.closest("[data-command-drag]");
  if (!handle || !event.dataTransfer) return;
  draggedCommand = {
    listPath: handle.dataset.listPath,
    index: Number(handle.dataset.index),
  };
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", commandPath(draggedCommand.listPath, draggedCommand.index));
  handle.closest(".command").classList.add("dragging");
  document.body.classList.add("command-dragging");
  document.querySelectorAll(".command-drop-zone").forEach((zone) => {
    zone.classList.toggle("invalid", isDescendantList(
      draggedCommand.listPath,
      draggedCommand.index,
      zone.dataset.dropListPath,
    ));
  });
});

document.addEventListener("dragover", (event) => {
  if (!draggedCommand) return;
  const zone = findDropZone(event.target, ".command-drop-zone:not(.invalid)");
  if (!zone) return;
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
  document.querySelectorAll(".command-drop-zone.active").forEach((node) => node.classList.remove("active"));
  zone.classList.add("active");
});

document.addEventListener("drop", (event) => {
  if (!draggedCommand) return;
  const zone = document.querySelector(".command-drop-zone.active:not(.invalid)");
  if (!zone) return;
  event.preventDefault();
  const source = draggedCommand;
  moveCommand(
    source.listPath,
    source.index,
    zone.dataset.dropListPath,
    Number(zone.dataset.dropIndex),
  );
  clearCommandDrag();
});

$("event-editor").addEventListener("dragend", clearCommandDrag);

function clearListItemDrag() {
  draggedListItem = null;
  document.body.classList.remove("list-item-dragging");
  document.querySelectorAll(".reorderable-list-item.dragging, .list-drop-zone.active").forEach((node) => {
    node.classList.remove("dragging", "active");
  });
}

document.querySelector(".sidebar").addEventListener("dragstart", (event) => {
  const handle = event.target.closest("[data-list-item-drag]");
  if (!handle || !event.dataTransfer) return;
  draggedListItem = {
    kind: handle.dataset.listKind,
    index: Number(handle.dataset.index),
  };
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", `list:${draggedListItem.kind}:${draggedListItem.index}`);
  handle.closest(".reorderable-list-item").classList.add("dragging");
  document.body.classList.add("list-item-dragging");
});

document.addEventListener("dragover", (event) => {
  if (!draggedListItem) return;
  const zone = findDropZone(event.target, `.list-drop-zone[data-list-drop-kind="${draggedListItem.kind}"]`);
  if (!zone) return;
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
  document.querySelectorAll(".list-drop-zone.active").forEach((node) => node.classList.remove("active"));
  zone.classList.add("active");
});

document.addEventListener("drop", (event) => {
  if (!draggedListItem) return;
  const zone = document.querySelector(`.list-drop-zone.active[data-list-drop-kind="${draggedListItem.kind}"]`);
  if (!zone) return;
  event.preventDefault();
  moveListItem(
    draggedListItem.kind,
    draggedListItem.index,
    Number(zone.dataset.listDropIndex),
  );
  clearListItemDrag();
});

document.querySelector(".sidebar").addEventListener("dragend", clearListItemDrag);

$("undo").addEventListener("click", undo);
$("redo").addEventListener("click", redo);
$("save").addEventListener("click", save);
$("id-filter").addEventListener("input", (event) => setIdFilter(event.target.value));
$("editor-switch").addEventListener("click", (event) => {
  const link = event.target.closest("a");
  if (!link || !state.dirty) return;
  event.preventDefault();
  navigateToEditor(link.href);
});
$("unsaved-navigation-dialog").addEventListener("click", (event) => {
  const choice = event.target.closest("[data-navigation-choice]")?.dataset.navigationChoice;
  if (choice) handleNavigationChoice(choice);
});
$("unsaved-navigation-dialog").addEventListener("close", () => {
  pendingEditorNavigationUrl = null;
});
window.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    save();
  } else if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
    event.preventDefault();
    event.shiftKey ? redo() : undo();
  }
});
window.addEventListener("beforeunload", (event) => {
  if (state.dirty) {
    event.preventDefault();
    event.returnValue = "";
  }
});

configureEditorNavigation();

(async function initialize() {
  try {
    const parameters = new URLSearchParams(location.search);
    pendingActorEventDraft = loadPendingActorEventDraft();
    actorEventReturnMapId = pendingActorEventDraft?.data?.map_id || null;
    const uiSettings = loadUiSettings();
    // Accept older map-editor links while selecting by the complete ID.
    const namespace = parameters.get("namespace");
    const event = parameters.get("event");
    const requestedEvent = event && namespace && !event.includes(".") ? `${namespace}.${event}` : event;
    const requestedListTab = requestedEvent ? "event" : uiSettings.listTab;
    state.filterText = "";
    applyDocument(await api("/api/document"), requestedEvent, requestedListTab);
    if (pendingActorEventDraftId) {
      if (!pendingActorEventDraft?.data?.map_id) {
        throw new Error("イベント追加用のマップ内容を復元できませんでした。");
      }
      const created = addEvent(true);
      configureEditorNavigation();
      toast(`${pendingActorEventDraft.actor_id}用の${created.id}を追加しました。`);
    }
  } catch (error) {
    toast(error.message);
  }
})();
