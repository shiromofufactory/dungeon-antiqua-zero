"use strict";

const VIEW_SIZE = 64;
const DEFAULT_VIEW_ORIGIN = [24, 16];
const WEAPON_SIZE = [16, 16];

const state = {
  token: new URLSearchParams(location.search).get("token") || "",
  data: null,
  characters: [],
  characterImage: null,
  weaponImage: null,
  selectedCharacter: 0,
  selectedPose: 0,
  selectedWeapon: 0,
  moveTarget: "origin",
  viewOrigin: [...DEFAULT_VIEW_ORIGIN],
  dirty: false,
  dragging: null,
};

const byId = (id) => document.getElementById(id);
const currentPose = () => state.data.poses[state.selectedPose];
const currentWeapon = () => currentPose().weapons[state.selectedWeapon];
const deepCopy = (value) => JSON.parse(JSON.stringify(value));

function newWeapon() {
  return { image: 0, position: [0, 0], layer: "front", flip_x: false, flip_y: false };
}

function newPose(id) {
  return { id, character_pose: 0, weapons: [newWeapon()] };
}

function showToast(message) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 1900);
}

function setDirty(value = true) {
  state.dirty = value;
  byId("save-button").disabled = false;
  byId("save-state").textContent = value ? "未保存の変更" : "保存済み";
}

function uniquePoseId(base = "attack_pose") {
  const ids = new Set(state.data.poses.map((pose) => pose.id));
  let index = 1;
  while (ids.has(`${base}_${String(index).padStart(2, "0")}`)) index += 1;
  return `${base}_${String(index).padStart(2, "0")}`;
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("画像を読み込めませんでした。"));
    image.src = url;
  });
}

function createSpriteCanvas(source, sx, sy, width, height) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  context.imageSmoothingEnabled = false;
  context.drawImage(source, sx, sy, width, height, 0, 0, width, height);
  return canvas;
}

function renderCharacters() {
  const container = byId("character-list");
  container.replaceChildren();
  state.characters.forEach((character, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `character-card${index === state.selectedCharacter ? " active" : ""}`;
    button.append(createSpriteCanvas(state.characterImage, 0, character.battle_sprite * 32, 16, 32));
    const label = document.createElement("span");
    const name = document.createElement("strong");
    name.textContent = character.name;
    const key = document.createElement("small");
    key.textContent = character.key.toUpperCase();
    label.append(name, key);
    button.append(label);
    const radio = document.createElement("i");
    radio.className = "radio";
    button.append(radio);
    button.setAttribute("aria-pressed", String(index === state.selectedCharacter));
    button.addEventListener("click", () => {
      state.selectedCharacter = index;
      renderCharacters();
      renderPoses();
      drawMain();
    });
    container.append(button);
  });
}

function renderPoses() {
  const container = byId("pose-grid");
  container.replaceChildren();
  const pose = currentPose();
  const character = state.characters[state.selectedCharacter];
  for (let index = 0; index < 8; index += 1) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `pose-button${index === pose.character_pose ? " active" : ""}`;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", String(index === pose.character_pose));
    button.append(createSpriteCanvas(state.characterImage, index * 16, character.battle_sprite * 32, 16, 32));
    const number = document.createElement("span");
    number.textContent = String(index).padStart(2, "0");
    button.append(number);
    button.addEventListener("click", () => {
      pose.character_pose = index;
      setDirty();
      renderPoses();
      renderPresetList();
      drawMain();
    });
    container.append(button);
  }
  byId("pose-readout").textContent = `${pose.character_pose} / 7`;
}

function renderWeaponSlots() {
  const hasSecondWeapon = currentPose().weapons.length === 2;
  document.querySelectorAll("[data-weapon-slot]").forEach((button) => {
    const index = Number(button.dataset.weaponSlot);
    button.disabled = index === 1 && !hasSecondWeapon;
    button.classList.toggle("active", index === state.selectedWeapon);
  });
  const secondTarget = document.querySelector('[data-target="weapon_1"]');
  secondTarget.disabled = !hasSecondWeapon;
  byId("toggle-second-weapon").textContent = hasSecondWeapon ? "武器2を削除" : "武器2を追加";
}

function renderWeapons() {
  const container = byId("weapon-grid");
  container.replaceChildren();
  const selected = currentWeapon().image;
  for (let index = 0; index < 16; index += 1) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `weapon-button${index === selected ? " active" : ""}`;
    button.setAttribute("role", "option");
    button.setAttribute("aria-label", `武器画像 ${index}`);
    button.setAttribute("aria-selected", String(index === selected));
    button.append(createSpriteCanvas(state.weaponImage, index * 16, 0, 16, 16));
    const number = document.createElement("span");
    number.textContent = String(index).padStart(2, "0");
    button.append(number);
    button.addEventListener("click", () => {
      currentWeapon().image = index;
      state.moveTarget = `weapon_${state.selectedWeapon}`;
      setDirty();
      renderAll();
    });
    container.append(button);
  }
  byId("weapon-selected-label").textContent = `WEAPON ${state.selectedWeapon + 1}`;
  byId("weapon-readout").textContent = `IMAGE ${String(selected).padStart(2, "0")}`;
}

function drawChecker(context) {
  for (let y = 0; y < VIEW_SIZE; y += 4) {
    for (let x = 0; x < VIEW_SIZE; x += 4) {
      context.fillStyle = (x / 4 + y / 4) % 2 ? "#151820" : "#1b1e27";
      context.fillRect(x, y, 4, 4);
    }
  }
  context.strokeStyle = "#323743";
  context.lineWidth = 0.2;
  for (let value = 0; value <= VIEW_SIZE; value += 8) {
    context.beginPath(); context.moveTo(value, 0); context.lineTo(value, VIEW_SIZE); context.stroke();
    context.beginPath(); context.moveTo(0, value); context.lineTo(VIEW_SIZE, value); context.stroke();
  }
  context.strokeStyle = "#e1b85b";
  context.lineWidth = 0.35;
  context.beginPath();
  context.moveTo(state.viewOrigin[0] + 0.5, 0); context.lineTo(state.viewOrigin[0] + 0.5, VIEW_SIZE);
  context.moveTo(0, state.viewOrigin[1] + 0.5); context.lineTo(VIEW_SIZE, state.viewOrigin[1] + 0.5);
  context.stroke();
  context.fillStyle = "#f6cf72";
  context.fillRect(state.viewOrigin[0] - 0.75, state.viewOrigin[1] - 0.75, 1.5, 1.5);
}

function drawWeapon(context, weapon) {
  const position = [state.viewOrigin[0] + weapon.position[0], state.viewOrigin[1] + weapon.position[1]];
  context.save();
  context.translate(
    position[0] + (weapon.flip_x ? 16 : 0),
    position[1] + (weapon.flip_y ? 16 : 0),
  );
  context.scale(weapon.flip_x ? -1 : 1, weapon.flip_y ? -1 : 1);
  context.drawImage(state.weaponImage, weapon.image * 16, 0, 16, 16, 0, 0, 16, 16);
  context.restore();
}

function drawMain() {
  const canvas = byId("main-canvas");
  const context = canvas.getContext("2d");
  context.imageSmoothingEnabled = false;
  drawChecker(context);
  const pose = currentPose();
  const character = state.characters[state.selectedCharacter];
  pose.weapons.filter((weapon) => weapon.layer === "back").forEach((weapon) => drawWeapon(context, weapon));
  context.drawImage(
    state.characterImage, pose.character_pose * 16, character.battle_sprite * 32, 16, 32,
    state.viewOrigin[0], state.viewOrigin[1], 16, 32,
  );
  pose.weapons.filter((weapon) => weapon.layer === "front").forEach((weapon) => drawWeapon(context, weapon));

  if (state.moveTarget.startsWith("weapon_")) {
    const weaponIndex = Number(state.moveTarget.slice(-1));
    const weapon = pose.weapons[weaponIndex];
    if (weapon) {
      const position = [state.viewOrigin[0] + weapon.position[0], state.viewOrigin[1] + weapon.position[1]];
      context.strokeStyle = weaponIndex === 0 ? "#e1b85b" : "#71a9d2";
      context.lineWidth = 0.5;
      context.strokeRect(position[0] - 0.25, position[1] - 0.25, WEAPON_SIZE[0] + 0.5, WEAPON_SIZE[1] + 0.5);
    }
  }
}

function renderControls() {
  const weapon = currentWeapon();
  byId("origin-x").value = state.viewOrigin[0];
  byId("origin-y").value = state.viewOrigin[1];
  byId("weapon-x").value = weapon.position[0];
  byId("weapon-y").value = weapon.position[1];
  byId("weapon-coordinate-legend").textContent = `WEAPON ${state.selectedWeapon + 1}`;
  byId("layer-label").textContent = `武器${state.selectedWeapon + 1}の重なり`;
  document.querySelectorAll("[data-target]").forEach((button) => button.classList.toggle("active", button.dataset.target === state.moveTarget));
  document.querySelectorAll("[data-layer]").forEach((button) => button.classList.toggle("active", button.dataset.layer === weapon.layer));
  document.querySelectorAll("[data-flip]").forEach((button) => {
    const active = weapon[button.dataset.flip];
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

function renderPresetList() {
  const container = byId("preset-list");
  container.replaceChildren();
  state.data.poses.forEach((pose, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `preset-item${index === state.selectedPose ? " active" : ""}`;
    const id = document.createElement("strong");
    id.textContent = pose.id;
    const summary = document.createElement("small");
    const weapons = pose.weapons.map((weapon) => `W${String(weapon.image).padStart(2, "0")}`).join(" + ");
    summary.textContent = `P${pose.character_pose} / ${weapons}`;
    button.append(id, summary);
    button.addEventListener("click", () => {
      state.selectedPose = index;
      if (state.selectedWeapon >= currentPose().weapons.length) state.selectedWeapon = 0;
      if (state.moveTarget === "weapon_1" && currentPose().weapons.length < 2) state.moveTarget = "weapon_0";
      renderAll();
    });
    container.append(button);
  });
  byId("pose-id").value = currentPose().id;
  byId("delete-pose").disabled = state.data.poses.length <= 1;
}

function renderAll() {
  renderCharacters();
  renderPoses();
  renderWeaponSlots();
  renderWeapons();
  renderControls();
  renderPresetList();
  drawMain();
}

function positionForTarget(target) {
  if (target === "origin") return state.viewOrigin;
  const weaponIndex = Number(target.slice(-1));
  return currentPose().weapons[weaponIndex]?.position || null;
}

function updatePosition(target, axis, rawValue) {
  const value = Number(rawValue);
  const isOrigin = target === "origin";
  const minimum = isOrigin ? 0 : -128;
  const maximum = isOrigin ? VIEW_SIZE : 128;
  if (!Number.isInteger(value) || value < minimum || value > maximum) return;
  const position = positionForTarget(target);
  if (!position) return;
  position[axis] = value;
  if (!isOrigin) setDirty();
  renderControls();
  drawMain();
}

function moveSelectedTarget(dx, dy) {
  const position = positionForTarget(state.moveTarget);
  if (!position) return;
  const isOrigin = state.moveTarget === "origin";
  const minimum = isOrigin ? 0 : -128;
  const maximum = isOrigin ? VIEW_SIZE : 128;
  position[0] = Math.max(minimum, Math.min(maximum, position[0] + dx));
  position[1] = Math.max(minimum, Math.min(maximum, position[1] + dy));
  if (!isOrigin) setDirty();
  renderControls();
  drawMain();
}

function selectWeapon(index) {
  if (!currentPose().weapons[index]) return;
  state.selectedWeapon = index;
  state.moveTarget = `weapon_${index}`;
  renderAll();
}

function bindControls() {
  [["origin-x", "origin", 0], ["origin-y", "origin", 1]].forEach(([id, target, axis]) => {
    byId(id).addEventListener("change", (event) => updatePosition(target, axis, event.target.value));
  });
  [["weapon-x", 0], ["weapon-y", 1]].forEach(([id, axis]) => {
    byId(id).addEventListener("change", (event) => updatePosition(`weapon_${state.selectedWeapon}`, axis, event.target.value));
  });
  byId("reset-origin").addEventListener("click", () => {
    state.viewOrigin.splice(0, 2, ...DEFAULT_VIEW_ORIGIN);
    state.moveTarget = "origin";
    renderControls();
    drawMain();
  });
  document.querySelectorAll("[data-target]").forEach((button) => button.addEventListener("click", () => {
    if (button.disabled) return;
    state.moveTarget = button.dataset.target;
    if (state.moveTarget.startsWith("weapon_")) state.selectedWeapon = Number(state.moveTarget.slice(-1));
    renderAll();
  }));
  document.querySelectorAll("[data-weapon-slot]").forEach((button) => button.addEventListener("click", () => selectWeapon(Number(button.dataset.weaponSlot))));
  byId("toggle-second-weapon").addEventListener("click", () => {
    if (currentPose().weapons.length === 1) {
      currentPose().weapons.push(newWeapon());
      state.selectedWeapon = 1;
      state.moveTarget = "weapon_1";
    } else {
      currentPose().weapons.splice(1, 1);
      state.selectedWeapon = 0;
      state.moveTarget = "weapon_0";
    }
    setDirty();
    renderAll();
  });
  document.querySelectorAll("[data-layer]").forEach((button) => button.addEventListener("click", () => {
    currentWeapon().layer = button.dataset.layer;
    setDirty();
    renderAll();
  }));
  document.querySelectorAll("[data-flip]").forEach((button) => button.addEventListener("click", () => {
    const field = button.dataset.flip;
    currentWeapon()[field] = !currentWeapon()[field];
    setDirty();
    renderAll();
  }));
  byId("pose-id").addEventListener("input", (event) => {
    currentPose().id = event.target.value;
    setDirty();
    renderPresetList();
  });
  byId("add-pose").addEventListener("click", () => {
    state.data.poses.push(newPose(uniquePoseId()));
    state.selectedPose = state.data.poses.length - 1;
    state.selectedWeapon = 0;
    state.moveTarget = "weapon_0";
    setDirty();
    renderAll();
  });
  byId("duplicate-pose").addEventListener("click", () => {
    const copy = deepCopy(currentPose());
    copy.id = uniquePoseId(currentPose().id.replace(/_\d+$/, "") || "attack_pose");
    state.data.poses.splice(state.selectedPose + 1, 0, copy);
    state.selectedPose += 1;
    setDirty();
    renderAll();
  });
  byId("delete-pose").addEventListener("click", () => {
    if (state.data.poses.length <= 1) return;
    state.data.poses.splice(state.selectedPose, 1);
    state.selectedPose = Math.min(state.selectedPose, state.data.poses.length - 1);
    state.selectedWeapon = Math.min(state.selectedWeapon, currentPose().weapons.length - 1);
    if (state.moveTarget === "weapon_1" && currentPose().weapons.length < 2) state.moveTarget = "weapon_0";
    setDirty();
    renderAll();
  });
  byId("save-button").addEventListener("click", saveDocument);

  const canvas = byId("main-canvas");
  canvas.addEventListener("pointerdown", (event) => {
    const rect = canvas.getBoundingClientRect();
    const point = [Math.floor((event.clientX - rect.left) * VIEW_SIZE / rect.width), Math.floor((event.clientY - rect.top) * VIEW_SIZE / rect.height)];
    const position = positionForTarget(state.moveTarget);
    if (!position) return;
    state.dragging = { start: point, position: [...position], target: state.moveTarget };
    canvas.setPointerCapture(event.pointerId);
    canvas.classList.add("dragging");
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!state.dragging) return;
    const rect = canvas.getBoundingClientRect();
    const point = [Math.floor((event.clientX - rect.left) * VIEW_SIZE / rect.width), Math.floor((event.clientY - rect.top) * VIEW_SIZE / rect.height)];
    const position = positionForTarget(state.dragging.target);
    if (!position) return;
    const isOrigin = state.dragging.target === "origin";
    const minimum = isOrigin ? 0 : -128;
    const maximum = isOrigin ? VIEW_SIZE : 128;
    position[0] = Math.max(minimum, Math.min(maximum, state.dragging.position[0] + point[0] - state.dragging.start[0]));
    position[1] = Math.max(minimum, Math.min(maximum, state.dragging.position[1] + point[1] - state.dragging.start[1]));
    if (!isOrigin) setDirty();
    renderControls();
    drawMain();
  });
  const endDrag = () => { state.dragging = null; canvas.classList.remove("dragging"); };
  canvas.addEventListener("pointerup", endDrag);
  canvas.addEventListener("pointercancel", endDrag);

  window.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      saveDocument();
      return;
    }
    if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return;
    const movement = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[event.key];
    if (movement) {
      event.preventDefault();
      moveSelectedTarget(...movement);
    }
  });
  window.addEventListener("beforeunload", (event) => {
    if (!state.dirty) return;
    event.preventDefault();
    event.returnValue = "";
  });
}

async function saveDocument() {
  const response = await fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Attack-Pose-Token": state.token },
    body: JSON.stringify({ data: state.data }),
  });
  const result = await response.json();
  if (!response.ok) {
    showToast(result.error || "保存できませんでした。");
    return;
  }
  if (!result.saved) {
    const issue = result.diagnostics[0];
    showToast(issue ? `${issue.path}: ${issue.message}` : "入力内容を確認してください。");
    return;
  }
  setDirty(false);
  showToast("attack_poses.json を保存しました");
}

async function initialize() {
  try {
    const response = await fetch(`/api/document?token=${encodeURIComponent(state.token)}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "データを読み込めませんでした。");
    state.data = payload.data;
    state.characters = payload.characters;
    [state.characterImage, state.weaponImage] = await Promise.all([
      loadImage(payload.character_image_url), loadImage(payload.weapon_image_url),
    ]);
    bindControls();
    renderAll();
    setDirty(payload.is_new);
    byId("save-state").textContent = payload.is_new ? "新規データ" : "保存済み";
  } catch (error) {
    byId("save-state").textContent = "読み込み失敗";
    showToast(error.message);
  }
}

initialize();
