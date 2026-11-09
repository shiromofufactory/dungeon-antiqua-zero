import { History, addStep, moveStep, newId, clone } from "./model.js";

const byId = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
let token = new URL(location.href).searchParams.get("token") || "";
let history, catalogs, saving = false, navigationUrl = null, pendingEdit = false;
let validationRevision = 0, validationTimer;
const state = () => history.value;
const dungeon = () => state().data.dungeons.find((entry) => entry.id === state().dungeonId);
const step = () => dungeon()?.steps.find((entry) => entry.id === state().stepId);
const labels = { random_encounter: "ランダムエンカウント", treasure: "宝箱", event_battle: "イベント戦闘" };

async function api(path, data) {
  const response = await fetch(`/dungeon/api/${path}`, {
    method: data === undefined ? "GET" : "POST",
    headers: { "X-Dungeon-Editor-Token": token, "Content-Type": "application/json" },
    body: data === undefined ? undefined : JSON.stringify({ data }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "通信に失敗しました。");
  return payload;
}

function optionList(options, selected) {
  return options.map(([value, text]) => `<option value="${escapeHtml(value)}" ${String(value) === String(selected) ? "selected" : ""}>${escapeHtml(text)}</option>`).join("");
}
function selectField(field, label, options, selected) {
  return `<label>${label}<select data-field="${field}">${optionList(options, selected)}</select></label>`;
}
function numberField(field, label, value, min, max) {
  return `<label>${label}<input data-field="${field}" type="number" min="${min}" max="${max}" value="${value}"></label>`;
}
function catalogOptions(name) { return catalogs[name].map((entry) => [entry.key, `${entry.name} (${entry.key})`]); }
function summary(entry) {
  if (entry.type === "random_encounter") return `${entry.count}回 · LV ${entry.encounter.monster_level === "dynamic" ? "変動" : entry.encounter.monster_level} · 危険度${entry.encounter.danger === "high" ? "高" : "低"}`;
  if (entry.type === "event_battle") return entry.battle_id;
  return entry.contents.type === "gold" ? `${entry.contents.amount} Gold` : entry.contents.item_key;
}
function detail(entry) {
  let html = "";
  if (entry.type === "random_encounter") {
    const e = entry.encounter;
    html = numberField("count", "戦闘回数", entry.count, 1, 9999)
      + selectField("monster_level", "モンスターレベル", [...Array.from({length:9}, (_,i) => [i+1,i+1]), ["dynamic","変動"]], e.monster_level)
      + selectField("danger", "危険度", [["low","低"],["high","高"]], e.danger)
      + selectField("polarity", "傾向", [["yang","陽"],["neutral","中立"],["yin","陰"]], e.polarity);
    for (const [key,label] of [["allow_demons","悪魔出現"],["allow_humans","人間出現"],["allow_giants","巨人出現"],["allow_large_animals","大型動物出現"]]) {
      html += selectField(key, label, [[false,"なし"],[true,"あり"]], e[key]);
    }
  } else if (entry.type === "treasure") {
    html = selectField("contents_type", "中身", [["gold","Gold"],["item","アイテム"]], entry.contents.type);
    html += entry.contents.type === "gold" ? numberField("amount", "金額", entry.contents.amount, 1, 999999)
      : selectField("item_key", "アイテム（1個）", catalogOptions("items"), entry.contents.item_key);
  } else {
    html = selectField("battle_id", "バトルID", [["", "選択してください"], ...catalogs.battle_ids.map((id) => [id,id])], entry.battle_id);
  }
  html = `<div class="fields">${html}</div>`;
  if (entry.type === "event_battle") {
    const battle = catalogs.battles.find((battle) => battle.battle_id === entry.battle_id);
    const names = (battle?.monster_keys || []).map((key) => catalogs.monsters.find((monster) => monster.key === key)?.name || key);
    html += `<p class="hint">${escapeHtml(names.join(" ／ ") || "イベントエディタの「イベントバトル」タブで登録してください。")}</p>`;
  }
  return html;
}

function render(rebuild = true) {
  if (!history) return;
  byId("save-state").textContent = saving ? "保存中…" : history.dirty || pendingEdit ? "未保存の変更あり" : "保存済み";
  byId("undo").disabled = !history.past.length || saving;
  byId("redo").disabled = !history.future.length || saving;
  byId("save").disabled = !(history.dirty || pendingEdit) || saving;
  byId("add-dungeon").disabled = saving;
  if (!rebuild) {
    // Keep focused controls and a clicked button alive while an input commits on blur.
    document.querySelectorAll("[data-dungeon]").forEach((button) => {
      const entry = state().data.dungeons.find((candidate) => candidate.id === button.dataset.dungeon);
      if (entry) button.textContent = entry.name;
    });
    document.querySelectorAll("[data-step]").forEach((button) => {
      const index = dungeon()?.steps.findIndex((candidate) => candidate.id === button.dataset.step);
      if (index >= 0) { const entry = dungeon().steps[index]; button.textContent = `${index+1}. ${labels[entry.type]} ${summary(entry)}`; }
    });
    return;
  }
  byId("dungeons").innerHTML = state().data.dungeons.map((entry) => `<button data-dungeon="${entry.id}" class="${entry.id === state().dungeonId ? "selected" : ""}">${escapeHtml(entry.name)}</button>`).join("") || '<p class="hint">「＋ 新規」でダンジョンを作成します。</p>';
  const d = dungeon();
  if (!d) { byId("workspace").innerHTML = '<p class="empty">ダンジョンを選択してください。</p>'; return; }
  byId("workspace").innerHTML = `<div class="heading"><h2>入口から最奥部まで</h2><button data-action="delete-dungeon" class="danger">ダンジョンを削除</button></div>
    <div class="metadata"><label>ダンジョン名<input data-field="name" maxlength="24" value="${escapeHtml(d.name)}"></label>${selectField("bgm_id","探索中のBGM",catalogs.bgm_ids.map((key)=>[key,key]),d.bgm_id)}<span class="muted source-id">ID: ${d.id}</span></div>
    <div class="add-step"><span>選択行の後に追加：</span><button data-add="random_encounter">＋ ランダム戦闘</button><button data-add="treasure">＋ 宝箱</button><button data-add="event_battle">＋ イベント戦闘</button></div>
    <div>${d.steps.map((entry,index) => `<article class="step ${entry.id === state().stepId ? "selected" : ""}"><button class="step-title" data-step="${entry.id}">${index+1}. ${labels[entry.type]} <span class="muted">${escapeHtml(summary(entry))}</span></button><div class="toolbar"><button data-action="up" data-id="${entry.id}" ${index===0 ? "disabled":""} aria-label="上へ移動">↑</button><button data-action="down" data-id="${entry.id}" ${index===d.steps.length-1 ? "disabled":""} aria-label="下へ移動">↓</button><button data-action="delete-step" data-id="${entry.id}">削除</button></div>${entry.id === state().stepId ? `<div class="step-detail">${detail(entry)}</div>` : ""}</article>`).join("") || '<p class="empty">戦闘や宝箱を追加してください。</p>'}</div>`;
}

function showIssues(issues) {
  byId("issues").replaceChildren(...issues.map((issue) => {
    const p = document.createElement("p"); p.className = "error"; p.textContent = issue.message; return p;
  }));
  if (!issues.length) byId("issues").textContent = "問題はありません。";
}
function changed(edit, rebuild = true) {
  history.change(edit);
  render(rebuild);
  const revision = ++validationRevision;
  clearTimeout(validationTimer);
  validationTimer = setTimeout(async () => {
    try { const result = await api("validate", clone(state().data)); if (revision === validationRevision) showIssues(result.diagnostics); }
    catch (error) { if (revision === validationRevision) showIssues([{message:error.message}]); }
  }, 200);
}
async function save() {
  if (!history || saving) return false;
  const submitted = clone(state().data);
  saving = true; render();
  try {
    const result = await api("save", submitted);
    showIssues(result.diagnostics);
    if (result.saved) history.markSaved(submitted);
    return result.saved;
  } catch (error) { showIssues([{message:error.message}]); return false; }
  finally { saving = false; render(); }
}

document.addEventListener("click", (event) => {
  const target = event.target.closest("button,a");
  if (!target || target.disabled) return;
  if (target.dataset.editor) {
    event.preventDefault();
    if (target.dataset.editor === "dungeon") return;
    if (!history?.dirty) location.assign(target.href);
    else { navigationUrl = target.href; byId("navigation-dialog").showModal(); }
    return;
  }
  if (target.dataset.navigation) {
    void (async () => {
      const action = target.dataset.navigation;
      if (action === "save" && !await save()) return;
      byId("navigation-dialog").close();
      if (action !== "cancel") { history.markSaved(state().data); location.assign(navigationUrl); }
    })();
    return;
  }
  if (!history || saving) return;
  if (target.id === "save") { void save(); return; }
  if (target.id === "undo" || target.id === "redo") { history[target.id](); changed(() => {}); return; }
  if (target.dataset.dungeon) { state().dungeonId = target.dataset.dungeon; state().stepId = null; render(); return; }
  if (target.dataset.step) { state().stepId = target.dataset.step; render(); return; }
  if (target.id === "add-dungeon") {
    changed((value) => { const id = newId("dungeon"); value.data.dungeons.push({id,name:"新しいダンジョン",bgm_id:catalogs.bgm_ids.includes("da3-dungeon1") ? "da3-dungeon1" : catalogs.bgm_ids[0] || "",steps:[]}); value.dungeonId = id; value.stepId = null; }); return;
  }
  if (target.dataset.add) {
    changed((value) => { const d = dungeon(); const index = d.steps.findIndex((entry) => entry.id === value.stepId); value.stepId = addStep(d,target.dataset.add,catalogs,index < 0 ? d.steps.length : index + 1).id; }); return;
  }
  const action = target.dataset.action;
  if (action === "delete-dungeon") {
    if (!confirm("このダンジョンを削除しますか？")) return;
    changed((value) => { value.data.dungeons = value.data.dungeons.filter((entry) => entry.id !== value.dungeonId); value.dungeonId = value.data.dungeons[0]?.id ?? null; value.stepId = null; });
  } else if (action === "delete-step") {
    changed((value) => { const d = dungeon(); const index = d.steps.findIndex((entry) => entry.id === target.dataset.id); d.steps.splice(index,1); value.stepId = d.steps[Math.min(index,d.steps.length-1)]?.id ?? null; });
  } else if (action === "up" || action === "down") {
    changed((value) => { value.stepId = target.dataset.id; moveStep(dungeon(),target.dataset.id,action === "up" ? -1 : 1); });
  }
});

document.addEventListener("change", (event) => {
  if (!history || saving) return;
  const target = event.target;
  pendingEdit = false;
  const field = target.dataset.field;
  if (!field) return;
  changed(() => {
    const d = dungeon(), s = step(), value = target.value;
    if (field === "name" || field === "bgm_id") d[field] = value;
    else if (field === "contents_type") s.contents = value === "gold" ? {type:"gold",amount:100} : {type:"item",item_key:catalogs.items[0]?.key || ""};
    else if (field === "count") s.count = Number(value);
    else if (field === "amount") s.contents.amount = Number(value);
    else if (field === "item_key") s.contents.item_key = value;
    else if (field === "battle_id") s.battle_id = value;
    else s.encounter[field] = field.startsWith("allow_") ? value === "true" : field === "monster_level" && value !== "dynamic" ? Number(value) : value;
  }, field === "contents_type" || field === "battle_id");
});
document.addEventListener("input", (event) => {
  if (history && event.target.dataset.field && !saving) { pendingEdit = true; render(false); }
});
document.addEventListener("focusout", () => { if (history && pendingEdit) { pendingEdit = false; render(false); } });
document.addEventListener("keydown", (event) => {
  if (!(event.metaKey || event.ctrlKey) || !history) return;
  const key = event.key.toLowerCase();
  if (key === "s") { event.preventDefault(); document.activeElement?.blur(); void save(); }
  if (key === "z" && !["INPUT","TEXTAREA"].includes(event.target.tagName) && !saving) { event.preventDefault(); history[event.shiftKey ? "redo" : "undo"](); changed(() => {}); }
});
document.addEventListener("contextmenu", (event) => event.preventDefault(), { capture: true });
window.addEventListener("beforeunload", (event) => { if (history?.dirty || pendingEdit) { event.preventDefault(); event.returnValue = ""; } });

async function initialize() {
  try {
    // A restarted local server can issue a fresh token to its own editor UI.
    const response = await fetch("/dungeon/api/session-token", {headers:{"X-Dungeon-Editor-Client":"dungeon-editor-ui"}});
    if (response.ok) token = (await response.json()).token;
    document.querySelectorAll("[data-editor]").forEach((link) => { const url = new URL(`/${link.dataset.editor}/`,location.origin); url.searchParams.set("token",token); link.href = url.href; });
    const payload = await api("document");
    catalogs = payload.catalogs;
    history = new History(payload.data);
    showIssues(payload.diagnostics);
    render();
  } catch (error) { byId("save-state").textContent = "読み込み失敗"; showIssues([{message:error.message}]); }
}
void initialize();
