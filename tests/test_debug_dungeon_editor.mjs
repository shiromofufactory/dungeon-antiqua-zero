import test from "node:test";
import assert from "node:assert/strict";
import { History, addStep, moveListItem, defaultEncounter, stepRanges, stepLabel, setBattleFlag } from "../tools/debug_dungeon_editor/static/model.js";

const catalogs = { battle_ids: ["shared_guard"], monsters: [{key:"Giant Spider"}], items: [{key:"POTION"}] };
const dungeon = () => ({id:"trial",name:"調整用",bgm_id:"da3-dungeon1",steps:[]});

test("dungeon order is saved and undoable while retaining the selected dungeon and step", () => {
  const first = dungeon();
  const chest = addStep(first, "treasure", catalogs);
  const second = { ...dungeon(), id: "second" };
  const third = { ...dungeon(), id: "third" };
  const h = new History({ format_version: 1, dungeons: [first, second, third] });
  h.value.stepId = chest.id;
  const move = (id, dropIndex) => h.change((state) => moveListItem(state.data.dungeons, id, dropIndex));

  move(first.id, -1);
  move(first.id, 4);
  move(second.id, 1);
  move(second.id, 2);
  move("missing", 0);
  assert.equal(h.past.length, 0);
  assert.equal(h.dirty, false);

  move(third.id, 0);
  assert.deepEqual(h.value.data.dungeons, [third, first, second]);
  assert.equal(h.value.dungeonId, first.id);
  assert.equal(h.value.stepId, chest.id);
  assert.equal(h.dirty, true);
  h.undo();
  assert.deepEqual(h.value.data.dungeons, [first, second, third]);
  assert.equal(h.dirty, false);
  h.redo();
  const submitted = JSON.parse(JSON.stringify(h.value.data));
  assert.deepEqual(submitted.dungeons, [third, first, second]);
  h.markSaved(submitted);
  assert.equal(h.dirty, false);

  move(third.id, 3);
  assert.deepEqual(h.value.data.dungeons, [first, second, third]);
  assert.equal(h.dirty, true);
});

test("step numbering counts every random battle and follows count changes and reordering", () => {
  const d = dungeon();
  const random = addStep(d, "random_encounter", catalogs);
  const chest = addStep(d, "treasure", catalogs);
  assert.deepEqual(stepRanges(d).map(stepLabel), ["1〜5", "6"]);
  random.count = 2;
  assert.deepEqual(stepRanges(d).map(stepLabel), ["1〜2", "3"]);
  moveListItem(d.steps, chest.id, 0);
  assert.deepEqual(stepRanges(d).map(stepLabel), ["1", "2〜3"]);
});

test("healing springs insert, reorder and undo as single steps without editable event data", () => {
  const d = dungeon();
  addStep(d, "random_encounter", catalogs);
  addStep(d, "treasure", catalogs);
  const h = new History({format_version:1,dungeons:[d]});
  h.change((state) => addStep(state.data.dungeons[0], "healing_spring", catalogs, 1));
  const spring = h.value.data.dungeons[0].steps[1];
  assert.deepEqual(Object.keys(spring).sort(), ["id", "type"]);
  assert.deepEqual(stepRanges(h.value.data.dungeons[0]).map(stepLabel), ["1〜5", "6", "7"]);
  h.undo();
  assert.equal(h.value.data.dungeons[0].steps.length, 2);
  h.redo();
  assert.deepEqual(h.value.data.dungeons[0].steps[1], spring);
  moveListItem(h.value.data.dungeons[0].steps, spring.id, 0);
  assert.deepEqual(stepRanges(h.value.data.dungeons[0]).map(stepLabel), ["1", "2〜6", "7"]);
});

test("event battles select a shared ID and never copy a lineup into a dungeon", () => {
  const entry = addStep(dungeon(), "event_battle", catalogs);
  assert.equal(entry.battle_id, "shared_guard");
  assert.equal("monster_keys" in entry, false);
  assert.equal("flag_id" in entry, false);
});

test("optional battle flag can be selected, cleared and restored through history and reordering", () => {
  const d = dungeon();
  const battle = addStep(d, "event_battle", catalogs);
  addStep(d, "treasure", catalogs);
  const h = new History({format_version:1,dungeons:[d]});
  const steps = () => h.value.data.dungeons[0].steps;
  h.change(() => setBattleFlag(steps()[0], "trial.guard"));
  assert.equal(steps()[0].flag_id, "trial.guard");
  h.change(() => moveListItem(steps(), battle.id, steps().length));
  assert.equal(steps()[1].flag_id, "trial.guard");
  h.change(() => setBattleFlag(steps()[1], ""));
  assert.equal("flag_id" in steps()[1], false);
  h.undo();
  assert.equal(steps()[1].flag_id, "trial.guard");
  h.redo();
  assert.equal("flag_id" in steps()[1], false);
});

test("random settings inherit the preceding encounter at the insertion position as an independent copy", () => {
  const d = dungeon();
  const first = addStep(d,"random_encounter",catalogs);
  assert.deepEqual(first.encounter,defaultEncounter);
  first.encounter.monster_level = 2;
  first.encounter.danger = "high";
  addStep(d,"treasure",catalogs);
  const last = addStep(d,"random_encounter",catalogs);
  last.encounter.monster_level = 9;
  const inserted = addStep(d,"random_encounter",catalogs,2);
  assert.equal(inserted.encounter.monster_level,2);
  assert.equal(inserted.encounter.danger,"high");
  inserted.encounter.allow_demons = true;
  assert.equal(first.encounter.allow_demons,false);
  const beforeFirst = addStep(d,"random_encounter",catalogs,0);
  assert.deepEqual(beforeFirst.encounter,defaultEncounter);
});

test("treasure identity survives reordering, deletion and undo/redo", () => {
  const d = dungeon();
  const chest = addStep(d,"treasure",catalogs);
  addStep(d,"event_battle",catalogs);
  const h = new History({format_version:1,dungeons:[d]});
  h.value.dungeonId = d.id;
  h.value.stepId = chest.id;
  h.change((state) => moveListItem(state.data.dungeons[0].steps, chest.id, 2));
  assert.equal(h.value.data.dungeons[0].steps[1].id,chest.id);
  assert.equal(h.dirty,true);
  h.undo();
  assert.equal(h.value.data.dungeons[0].steps[0].id,chest.id);
  assert.equal(h.dirty,false);
  h.redo();
  h.change((state) => state.data.dungeons[0].steps.pop());
  h.undo();
  assert.equal(h.value.data.dungeons[0].steps[1].id,chest.id);
  const next = addStep(h.value.data.dungeons[0],"treasure",catalogs);
  assert.notEqual(next.id,chest.id);
});

test("new edits after undo clear redo and an in-flight save never marks newer edits saved", () => {
  const h = new History({format_version:1,dungeons:[dungeon()]});
  h.change((state) => { state.data.dungeons[0].name = "保存対象"; });
  const submitted = structuredClone(h.value.data);
  h.change((state) => { state.data.dungeons[0].name = "追加編集"; });
  h.markSaved(submitted);
  assert.equal(h.dirty,true);
  h.undo();
  assert.equal(h.dirty,false);
  h.change((state) => { state.data.dungeons[0].name = "別の編集"; });
  assert.equal(h.future.length,0);
});
