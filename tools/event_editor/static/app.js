"use strict";

const CLIENT = "event-editor-ui";
const NAMESPACE_PATTERN = /^[a-z][a-z0-9_]*$/;
const UI_STORAGE_KEY = "da0.event-editor.ui.v1";
const LIST_TABS = ["flag", "event", "message"];
let token = new URLSearchParams(location.search).get("token") || "";
const editorRoute = location.pathname.match(/^\/(map|event)(?:\/|$)/)?.[1] || null;
const state = {
  data: null,
  flags: [],
  messages: [],
  catalogs: {},
  diagnostics: [],
  namespaceOptions: [],
  selectedEvent: 0,
  selectedMessage: 0,
  mode: "event",
  dirty: false,
  history: [],
  future: [],
  timer: null,
  revision: 0,
};

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
      namespace: state.data.namespace,
      listTab: state.mode,
    }));
  } catch (_error) {}
}

function editorApiPath(path) {
  return editorRoute ? `/${editorRoute}${path}` : path;
}

function editorUrl(editor) {
  if (!editorRoute) return null;
  const url = new URL(`/${editor}/`, location.origin);
  url.searchParams.set("token", token);
  return url.href;
}

function configureEditorNavigation() {
  const navigation = $("editor-switch");
  if (!navigation || !editorRoute) return;
  navigation.hidden = false;
  navigation.querySelectorAll("[data-editor-link]").forEach((link) => {
    link.href = editorUrl(link.dataset.editorLink);
  });
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
    selectedEvent: state.selectedEvent,
    selectedMessage: state.selectedMessage,
    mode: state.mode,
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
  state.selectedEvent = restored.selectedEvent;
  state.selectedMessage = restored.selectedMessage;
  state.mode = restored.mode;
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
  if (!Array.isArray(state.flags)) state.flags = [];
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

function currentEvent() {
  return state.data.events[state.selectedEvent] || null;
}

function currentMessage() {
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

function options(values, selected, empty = "選択してください") {
  const all = [...values];
  if (selected && !all.includes(selected)) all.push(selected);
  return `<option value="" ${selected ? "" : "selected"}>${empty}</option>`
    + all.map((value) => `<option value="${esc(value)}" ${value === selected ? "selected" : ""}>${esc(value)}${values.includes(value) ? "" : "（不明）"}</option>`).join("");
}

function renderNamespaceControls() {
  const values = [...new Set([
    ...state.namespaceOptions,
    state.data.namespace,
  ])].sort();
  $("namespace-select").innerHTML = values.map((value) =>
    `<option value="${esc(value)}" ${value === state.data.namespace ? "selected" : ""}>${esc(value)}.json</option>`,
  ).join("");
}

function updateStatus() {
  const errors = state.diagnostics.some((item) => item.severity === "error");
  const node = $("save-state");
  node.className = `pill ${errors ? "error" : state.dirty ? "dirty" : "saved"}`;
  node.textContent = errors ? "要修正" : state.dirty ? "未保存" : "保存済み";
  $("save").disabled = errors;
  $("undo").disabled = !state.history.length;
  $("redo").disabled = !state.future.length;
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

  $("flags").className = "list";
  $("flags").innerHTML = state.flags.map((flag, index) => `
    <div class="list-item">
      <div class="field"><label>グローバルID</label><input value="${esc(flag.flag_id)}" data-flag-index="${index}" data-flag-field="flag_id"></div>
      <div class="field compact"><label>制作メモ</label><input value="${esc(flag.note || "")}" data-flag-index="${index}" data-flag-field="note"></div>
      <div class="row compact"><button class="danger icon" data-action="delete-flag" data-index="${index}">削除</button></div>
    </div>
  `).join("") || '<div class="empty">フラグはありません。</div>';

  $("events").className = "list";
  $("events").innerHTML = state.data.events.map((event, index) => `
    <button class="list-item ${state.mode === "event" && index === state.selectedEvent ? "active" : ""}" data-action="select-event" data-index="${index}">
      <strong>${esc(event.id)}</strong>
      <small>${event.commands?.length || 0} commands · ${esc(event.note || "メモなし")}</small>
    </button>
  `).join("") || '<div class="empty">イベントはありません。</div>';

  $("messages").className = "list";
  $("messages").innerHTML = state.messages.map((message, index) => `
    <button class="list-item ${state.mode === "message" && index === state.selectedMessage ? "active" : ""}" data-action="select-message" data-index="${index}">
      <strong>${esc(message.message_id)}</strong>
      <small>${esc((message.text_ja || [])[0] || "日本語未入力")}</small>
    </button>
  `).join("") || '<div class="empty">メッセージはありません。</div>';
}

function field(label, html, full = false) {
  return `<div class="field ${full ? "full" : ""}"><label>${label}</label>${html}</div>`;
}

function commandAt(path) {
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
  if (type === "flag_set") {
    fields = field("フラグ", `<select data-cond-command="${commandPath}" data-cond-path="${path}" data-cond-field="flag_id">${options(fullFlags(), condition.flag_id)}</select>`, true);
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
  const types = ["flag_set", "member_in_party", "item_at_least", "all", "any", "not"];
  return `<div class="condition">
    <div class="field"><label>条件</label><select data-cond-command="${commandPath}" data-cond-path="${path}" data-cond-field="type">${types.map((value) => `<option ${value === type ? "selected" : ""}>${value}</option>`).join("")}</select></div>
    <div class="command-fields compact">${fields}</div>
  </div>`;
}

function renderCommand(command, path, listPath, index) {
  const type = command.command;
  let fields = "";
  const attr = (name) => `data-command-path="${path}" data-command-field="${name}"`;
  if (type === "set_flag") {
    fields = field("フラグ", `<select ${attr("flag_id")}>${options(fullFlags(), command.flag_id)}</select>`, true);
  } else if (type === "join_party" || type === "leave_party") {
    fields = field("キャラクター", `<select ${attr("character_key")}>${options(state.catalogs.character_keys || [], command.character_key)}</select>`, true);
  } else if (type === "give_item" || type === "take_item") {
    fields = field("アイテム", `<select ${attr("item_key")}>${options(state.catalogs.item_keys || [], command.item_key)}</select>`)
      + field("個数", `<input type="number" min="1" value="${Number(command.quantity) || 1}" ${attr("quantity")}>`);
  } else if (type === "message") {
    fields = field("メッセージID", `<select ${attr("message_id")}>${options(messageIds(), command.message_id)}</select>`)
      + field("顔（任意）", `<select ${attr("portrait_character_key")}>${options(state.catalogs.character_keys || [], command.portrait_character_key, "顔なし")}</select>`);
  } else if (type === "play_se") {
    fields = field("SE", `<select ${attr("se_id")}>${options(state.catalogs.se_ids || [], command.se_id)}</select>`, true);
  } else if (type === "change_bgm") {
    fields = field("BGM", `<select ${attr("bgm_id")}>${options(state.catalogs.bgm_ids || [], command.bgm_id)}</select>`, true);
  } else if (type === "move_party" || type === "move_actor") {
    fields = (type === "move_actor" ? field("actor ID", `<select ${attr("actor_id")}>${options(state.catalogs.actor_ids || [], command.actor_id)}</select>`) : "")
      + field("方向", `<select ${attr("direction")}>${options(["up", "right", "down", "left"], command.direction)}</select>`)
      + field("歩数", `<input type="number" min="1" max="255" value="${Number(command.steps) || 1}" ${attr("steps")}>`);
  } else if (type === "branch") {
    fields = `<div class="full">${renderCondition(command.condition, path, "condition")}${renderBranch(command.then, path, "then")}${renderBranch(command.else, path, "else")}</div>`;
  }
  return `<article class="command">
    <div class="command-head"><code>${index + 1}. ${esc(type)}</code><div class="row"><button class="icon" data-action="move-command-up" data-list-path="${listPath}" data-index="${index}">↑</button><button class="icon" data-action="move-command-down" data-list-path="${listPath}" data-index="${index}">↓</button><button class="danger icon" data-action="delete-command" data-list-path="${listPath}" data-index="${index}">削除</button></div></div>
    <div class="command-fields">${fields}</div>
  </article>`;
}

function renderBranch(commands, parentPath, name) {
  const path = `${parentPath}/${name}`;
  return `<div class="branch"><h3>${name}</h3><div class="commands">${commands.map((command, index) => renderCommand(command, `${path}/${index}`, path, index)).join("") || '<div class="empty">コマンドなし</div>'}</div>${addCommand(path)}</div>`;
}

function addCommand(listPath = "") {
  const types = ["message", "set_flag", "branch", "join_party", "leave_party", "give_item", "take_item", "play_se", "change_bgm", "move_party", "move_actor"];
  return `<div class="add-row"><select data-new-command="${listPath}">${types.map((value) => `<option>${value}</option>`).join("")}</select><button data-action="add-command" data-list-path="${listPath}">コマンドを追加</button></div>`;
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
    <div class="heading"><h2>${esc(state.data.namespace)}.${esc(event.id)}</h2><span class="pill">${event.commands.length} commands</span></div>
    <div class="commands">${event.commands.map((command, index) => renderCommand(command, String(index), "", index)).join("") || '<div class="empty">コマンドはありません。</div>'}</div>
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
      ${field("制作メモ", `<input data-message-field="note" value="${esc(message.note || "")}">`, true)}
      ${field("日本語（1行ごとにゲーム内の1行）", `<textarea rows="6" data-message-field="text_ja">${esc((message.text_ja || []).join("\n"))}</textarea>`, true)}
      ${field("英語（未翻訳なら空欄）", `<textarea rows="6" data-message-field="text_en">${esc((message.text_en || []).join("\n"))}</textarea>`, true)}
      ${field("簡体字中国語（未翻訳なら空欄）", `<textarea rows="6" data-message-field="text_zhcn">${esc((message.text_zhcn || []).join("\n"))}</textarea>`, true)}
    </div>
  `;
}

function renderEditor() {
  if (state.mode === "message") {
    renderMessageEditor();
  } else if (state.mode === "flag") {
    $("event-editor").className = "empty";
    $("event-editor").innerHTML = "グローバルフラグは左の一覧で編集します。";
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
  renderNamespaceControls();
  renderLists();
  renderEditor();
  renderIssues();
  saveUiSettings();
}

function defaultCondition(type = "flag_set") {
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
  if (type === "give_item" || type === "take_item") return {...one("item_key", state.catalogs.item_keys), quantity: 1};
  if (type === "message") return one("message_id", messageIds());
  if (type === "play_se") return one("se_id", state.catalogs.se_ids);
  if (type === "change_bgm") return one("bgm_id", state.catalogs.bgm_ids);
  if (type === "move_party") return {command: type, direction: "down", steps: 1};
  if (type === "move_actor") return {command: type, actor_id: state.catalogs.actor_ids?.[0] || "", direction: "down", steps: 1};
  return {command: "branch", condition: defaultCondition(), then: [], else: []};
}

function uniqueId(base, records, fieldName = "id") {
  const used = new Set(records.map((item) => item[fieldName]));
  let number = 1;
  while (used.has(`${base}_${number}`)) number += 1;
  return `${base}_${number}`;
}

function linesFromTextarea(value) {
  if (!value) return [];
  return value.replaceAll("\r", "").split("\n").filter((line) => line.trim());
}

function requestBody() {
  return JSON.stringify({
    namespace: state.data.namespace,
    data: state.data,
    flags: state.flags,
    messages: state.messages,
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
  try {
    const result = await api("/api/save", {method: "POST", body: requestBody()});
    state.diagnostics = result.diagnostics;
    if (result.saved) {
      state.dirty = false;
      state.history = [];
      state.future = [];
      state.namespaceOptions = result.namespace_options || state.namespaceOptions;
      toast("イベント定義とメッセージを保存し、ゲーム用データを生成しました。");
    } else {
      toast("エラーを修正してください。");
    }
    render();
  } catch (error) {
    toast(error.message);
  }
}

function applyDocument(payload, selectedEventId = null, selectedListTab = "event") {
  clearTimeout(state.timer);
  state.revision += 1;
  state.data = payload.data;
  state.flags = payload.flags;
  state.messages = payload.messages;
  state.catalogs = payload.catalogs;
  state.diagnostics = payload.diagnostics;
  state.namespaceOptions = payload.namespace_options || [];
  const requestedEventIndex = selectedEventId === null
    ? -1
    : state.data.events.findIndex((event) => event.id === selectedEventId);
  state.selectedEvent = requestedEventIndex >= 0 ? requestedEventIndex : 0;
  state.selectedMessage = 0;
  state.mode = selectedEventId !== null || !LIST_TABS.includes(selectedListTab)
    ? "event"
    : selectedListTab;
  state.dirty = payload.is_new;
  state.history = [];
  state.future = [];
  normalize();
  const url = new URL(location.href);
  url.searchParams.set("namespace", state.data.namespace);
  if (requestedEventIndex >= 0) url.searchParams.set("event", selectedEventId);
  else url.searchParams.delete("event");
  history.replaceState(null, "", url);
  render();
}

async function openNamespace(namespace, selectedListTab = state.mode) {
  if (!NAMESPACE_PATTERN.test(namespace) || ["flags", "messages"].includes(namespace)) {
    toast("namespaceはlower_snake_caseで入力してください（flagsとmessagesは予約名です）。");
    return;
  }
  if (namespace === state.data.namespace) return;
  if (state.dirty && !window.confirm("未保存の変更を破棄してイベントファイルを切り替えますか？")) {
    renderNamespaceControls();
    return;
  }
  try {
    const payload = await api(`/api/document?namespace=${encodeURIComponent(namespace)}`);
    applyDocument(payload, null, selectedListTab);
    toast(payload.is_new ? `${namespace}.jsonを新規作成します。` : `${namespace}.jsonへ切り替えました。`);
  } catch (error) {
    renderNamespaceControls();
    toast(error.message);
  }
}

document.body.addEventListener("click", (event) => {
  const target = event.target.closest("[data-action]");
  if (!target) return;
  const action = target.dataset.action;
  if (action === "select-list-tab") {
    state.mode = target.dataset.listTab;
    render();
  } else if (action === "create-namespace") {
    openNamespace($("namespace-new").value.trim());
  } else if (action === "add-flag") {
    commit(() => {
      state.flags.push({flag_id: uniqueId("flag", state.flags, "flag_id"), note: ""});
      state.mode = "flag";
    });
  } else if (action === "delete-flag") {
    commit(() => state.flags.splice(Number(target.dataset.index), 1));
  } else if (action === "add-event") {
    commit(() => {
      state.data.events.push({id: uniqueId("event", state.data.events), note: "", commands: []});
      state.selectedEvent = state.data.events.length - 1;
      state.mode = "event";
    });
  } else if (action === "select-event") {
    state.selectedEvent = Number(target.dataset.index);
    state.mode = "event";
    render();
  } else if (action === "delete-event") {
    commit(() => state.data.events.splice(state.selectedEvent, 1));
  } else if (action === "add-message") {
    commit(() => {
      const base = `${state.data.namespace}.message`;
      state.messages.push({
        message_id: uniqueId(base, state.messages, "message_id"),
        text_ja: ["メッセージ"],
        text_en: [],
        text_zhcn: [],
        note: "",
      });
      state.selectedMessage = state.messages.length - 1;
      state.mode = "message";
    });
  } else if (action === "select-message") {
    state.selectedMessage = Number(target.dataset.index);
    state.mode = "message";
    render();
  } else if (action === "delete-message") {
    commit(() => state.messages.splice(state.selectedMessage, 1));
  } else if (action === "add-command") {
    const path = target.dataset.listPath;
    const selector = `select[data-new-command="${CSS.escape(path)}"]`;
    const type = document.querySelector(selector).value;
    commit(() => listAt(path).push(defaultCommand(type)));
  } else if (action === "delete-command") {
    commit(() => listAt(target.dataset.listPath).splice(Number(target.dataset.index), 1));
  } else if (action === "move-command-up" || action === "move-command-down") {
    commit(() => {
      const list = listAt(target.dataset.listPath);
      const index = Number(target.dataset.index);
      const next = index + (action.endsWith("up") ? -1 : 1);
      if (next >= 0 && next < list.length) [list[index], list[next]] = [list[next], list[index]];
    });
  } else if (action === "add-condition") {
    commit(() => conditionAt(commandAt(target.dataset.commandPath), target.dataset.conditionPath).conditions.push(defaultCondition()));
  } else if (action === "delete-condition") {
    commit(() => conditionAt(commandAt(target.dataset.commandPath), target.dataset.conditionPath).conditions.splice(Number(target.dataset.index), 1));
  }
});

$("flags").addEventListener("change", (event) => {
  const target = event.target;
  if (target.dataset.flagField) {
    commit(() => {
      state.flags[Number(target.dataset.flagIndex)][target.dataset.flagField] = target.value;
    });
  }
});

$("event-editor").addEventListener("change", (event) => {
  const target = event.target;
  if (target.dataset.eventField) {
    commit(() => { currentEvent()[target.dataset.eventField] = target.value; });
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
      command[fieldName] = fieldName === "quantity" || fieldName === "steps"
        ? Number(target.value)
        : target.value;
      if (fieldName === "portrait_character_key" && !command[fieldName]) {
        delete command[fieldName];
      }
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

$("undo").addEventListener("click", undo);
$("redo").addEventListener("click", redo);
$("validate").addEventListener("click", () => {
  schedule(0);
  toast("検証しました。");
});
$("save").addEventListener("click", save);
$("namespace-select").addEventListener("change", (event) => {
  openNamespace(event.target.value);
});
$("namespace-new").addEventListener("keydown", (event) => {
  if (event.key === "Enter") openNamespace(event.target.value.trim());
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
    const uiSettings = loadUiSettings();
    const storedNamespace = typeof uiSettings.namespace === "string"
      && NAMESPACE_PATTERN.test(uiSettings.namespace)
      && !["flags", "messages"].includes(uiSettings.namespace)
      ? uiSettings.namespace
      : null;
    const requestedNamespace = parameters.get("namespace") || storedNamespace;
    const requestedEvent = parameters.get("event");
    const requestedListTab = requestedEvent ? "event" : uiSettings.listTab;
    const query = requestedNamespace ? `?namespace=${encodeURIComponent(requestedNamespace)}` : "";
    applyDocument(await api(`/api/document${query}`), requestedEvent, requestedListTab);
  } catch (error) {
    toast(error.message);
  }
})();
