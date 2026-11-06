export const defaultEncounter = Object.freeze({
  monster_level: 1, danger: "low", polarity: "neutral", allow_demons: false,
  allow_humans: false, allow_giants: false, allow_large_animals: true,
});
export const clone = (value) => JSON.parse(JSON.stringify(value));
export const newId = (prefix) => `${prefix}_${crypto.randomUUID().replaceAll("-", "")}`;

export function addStep(dungeon, type, catalogs, at = dungeon.steps.length) {
  const step = { id: newId(type), type };
  if (type === "random_encounter") {
    const previous = dungeon.steps.slice(0, at).findLast((entry) => entry.type === type);
    step.count = 5;
    step.encounter = clone(previous?.encounter ?? defaultEncounter);
  } else if (type === "treasure") {
    step.contents = { type: "gold", amount: 100 };
  } else if (type === "event_battle") {
    step.battle_id = "debug_battle";
    step.monster_keys = catalogs.monsters.length ? [catalogs.monsters[0].key] : [];
  } else {
    throw new Error("不明なステップ種別です。");
  }
  dungeon.steps.splice(at, 0, step);
  return step;
}

export function moveStep(dungeon, id, distance) {
  const index = dungeon.steps.findIndex((step) => step.id === id);
  const target = index + distance;
  if (index < 0 || target < 0 || target >= dungeon.steps.length) return;
  const [step] = dungeon.steps.splice(index, 1);
  dungeon.steps.splice(target, 0, step);
}

export class History {
  constructor(data) {
    this.value = { data: clone(data), dungeonId: data.dungeons[0]?.id ?? null, stepId: null };
    this.saved = JSON.stringify(data);
    this.past = [];
    this.future = [];
  }
  get dirty() { return JSON.stringify(this.value.data) !== this.saved; }
  change(edit) {
    const before = clone(this.value);
    edit(this.value);
    if (JSON.stringify(before.data) === JSON.stringify(this.value.data)) return;
    this.past.push(before);
    if (this.past.length > 100) this.past.shift();
    this.future = [];
  }
  undo() {
    if (!this.past.length) return;
    this.future.push(clone(this.value));
    this.value = this.past.pop();
  }
  redo() {
    if (!this.future.length) return;
    this.past.push(clone(this.value));
    this.value = this.future.pop();
  }
  markSaved(data) { this.saved = JSON.stringify(data); }
}
