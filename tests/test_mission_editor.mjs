import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../tools/event_editor/static/app.js', import.meta.url), 'utf8');
const names = ['snapshot', 'begin', 'commit', 'restore', 'undo', 'redo', 'normalize', 'currentFlag', 'currentMission', 'currentEvent', 'currentMessage', 'listForKind', 'moveListItem', 'commandAt', 'conditionAt', 'defaultCondition', 'newMissionMessage', 'uniqueId', 'requestBody', 'renderMissionEditor', 'renderCondition', 'field', 'options', 'fullFlags', 'messageIds', 'renderMessagePreview'];
const declarations = names.map((name) => {
  const start = source.indexOf(`function ${name}(`);
  assert.notEqual(start, -1);
  const next = source.slice(start + 1).search(/\n(?:async )?function /);
  assert.notEqual(next, -1);
  return source.slice(start, start + next + 1);
}).join('\n');

function editor() {
  const state = {
    data: { namespace: 'common', events: [] }, flags: [{ flag_id: 'quest.started' }],
    missions: [{ id: 'z_first', message_id: 'mission.first' }, { id: 'a_second', message_id: 'mission.second' }],
    messages: [{ message_id: 'mission.first', text_ja: ['最初'] }, { message_id: 'mission.second', text_ja: ['次'] }],
    selectedFlag: 0, selectedMission: 0, selectedEvent: 0, selectedMessage: 0, mode: 'mission',
    history: [], future: [], dirty: false, catalogs: {},
  };
  const node = {};
  const context = vm.createContext({ state, LIST_TABS: ['event', 'flag', 'mission', 'message'],
    render() {}, schedule() {}, $: () => node, esc: (value) => String(value ?? ''),
  });
  vm.runInContext(declarations, context);
  return { state, context, node };
}

test('mission order, selection and message edits survive undo and redo and enter the save payload', () => {
  const { state, context } = editor();
  assert.equal(context.moveListItem('mission', 0, 2), true);
  assert.deepEqual(state.missions.map((mission) => mission.id), ['a_second', 'z_first']);
  assert.equal(state.selectedMission, 1);
  context.commit(() => { context.currentMessage().text_ja = ['変更']; });
  let payload = JSON.parse(context.requestBody());
  assert.deepEqual(payload.missions.map((mission) => mission.id), ['a_second', 'z_first']);
  assert.deepEqual(payload.messages[0].text_ja, ['変更']);
  assert.equal(payload.selectedMission, undefined);
  context.undo();
  assert.equal(context.currentMessage().text_ja[0], '最初');
  context.undo();
  assert.equal(context.currentMission().id, 'z_first');
  assert.equal(state.selectedMission, 0);
  context.redo();
  assert.equal(state.selectedMission, 1);
  context.redo();
  assert.equal(context.currentMessage().text_ja[0], '変更');
});

test('nested mission conditions use the same editor helpers without touching event commands', () => {
  const { state, context } = editor();
  const mission = context.commandAt('mission');
  mission.condition = context.defaultCondition('all');
  context.conditionAt(mission, 'condition').conditions.push(context.defaultCondition('not'));
  context.conditionAt(mission, 'condition/conditions/1/condition').flag_id = 'quest.done';
  assert.equal(mission.condition.conditions[1].condition.flag_id, 'quest.done');
  assert.equal(mission.condition.conditions[0].flag_id, 'quest.started');
  assert.deepEqual(state.data.events, []);
  const html = context.renderCondition(mission.condition, 'mission', 'condition');
  assert.match(html, /data-cond-command="mission"/);
  assert.match(html, /data-cond-path="condition\/conditions\/1\/condition"/);
});

test('mission messages are created separately and inline editing targets the referenced shared message', () => {
  const { state, context, node } = editor();
  const mission = context.currentMission();
  context.newMissionMessage(mission);
  const firstId = mission.message_id;
  context.newMissionMessage(mission);
  assert.notEqual(mission.message_id, firstId);
  context.renderMissionEditor();
  assert.match(node.innerHTML, /data-message-field="text_ja"/);
  assert.match(node.innerHTML, /data-message-field="text_en"/);
  assert.match(node.innerHTML, /data-message-field="text_zhcn"/);
  mission.message_id = 'mission.second';
  context.currentMessage().text_ja = ['共有本文'];
  assert.equal(state.messages[1].text_ja[0], '共有本文');
  state.missions.splice(0, 1);
  assert.equal(state.messages[1].message_id, 'mission.second');
});
