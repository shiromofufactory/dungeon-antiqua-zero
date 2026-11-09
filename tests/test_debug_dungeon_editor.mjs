import test from "node:test";
import assert from "node:assert/strict";
import { History, addStep, moveStep, defaultEncounter } from "../tools/debug_dungeon_editor/static/model.js";

const catalogs = { battle_ids: ["shared_guard"], monsters: [{key:"Giant Spider"}], items: [{key:"POTION"}] };
const dungeon = () => ({id:"trial",name:"調整用",bgm_id:"da3-dungeon1",steps:[]});

test("event battles select a shared ID and never copy a lineup into a dungeon", () => {
  const entry = addStep(dungeon(), "event_battle", catalogs);
  assert.equal(entry.battle_id, "shared_guard");
  assert.equal("monster_keys" in entry, false);
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
  h.change((state) => moveStep(state.data.dungeons[0],chest.id,1));
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
