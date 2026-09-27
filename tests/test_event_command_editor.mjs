import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../tools/event_editor/static/app.js', import.meta.url), 'utf8');
const optionStart = source.indexOf('const COMMAND_OPTIONS = [');
const optionEnd = source.indexOf('];', optionStart) + 2;
const names = [
  'snapshot', 'begin', 'commit', 'restore', 'undo', 'redo', 'normalize',
  'currentEvent', 'commandAt', 'listAt', 'commandPath', 'fullFlags', 'messageIds',
  'field', 'options', 'renderCommand', 'renderCommandDraft', 'renderDropZone',
  'renderCommandList', 'addCommand', 'defaultCondition', 'defaultCommand',
  'openCommandDraft', 'cancelCommandDraft', 'selectDraftCommand',
  'changeCommandType', 'requestBody',
];
const declarations = names.map((name) => {
  const start = source.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, name);
  const next = source.slice(start + 1).search(/\n(?:async )?function /);
  assert.notEqual(next, -1, name);
  return source.slice(start, start + next + 1);
}).join('\n');

function editor() {
  const state = {
    data: { namespace: 'sample', events: [{ id: 'run', commands: [] }] },
    flags: [{ flag_id: 'story.done' }], messages: [], missions: [],
    selectedEvent: 0, selectedFlag: 0, selectedMessage: 0, selectedMission: 0,
    mode: 'event', catalogs: { monster_keys: ['Giant Spider'] },
    history: [], future: [], dirty: false, commandDraft: null,
  };
  let focused = 0;
  const context = vm.createContext({
    state, LIST_TABS: ['flag', 'event', 'mission', 'message'],
    document: { querySelector: () => ({ focus: () => { focused += 1; } }) },
    CSS: { escape: (value) => value },
    render() {}, schedule() {}, esc: (value) => String(value ?? ''),
  });
  vm.runInContext(`${source.slice(optionStart, optionEnd)}\n${declarations}`, context);
  return { state, context, focused: () => focused };
}

test('add button opens an unsaved command picker and selecting a type reveals its fields', () => {
  const { state, context, focused } = editor();

  context.openCommandDraft('');

  assert.equal(focused(), 1);
  assert.equal(state.data.events[0].commands.length, 0);
  assert.equal(state.dirty, false);
  assert.equal(state.history.length, 0);
  assert.match(context.renderCommandList(state.data.events[0].commands, '', 'なし'), /data-draft-command=""/);
  assert.doesNotMatch(context.renderCommandList(state.data.events[0].commands, '', 'なし'), /data-command-field="battle_id"/);

  context.selectDraftCommand('', 'start_battle');

  assert.equal(state.data.events[0].commands[0].command, 'start_battle');
  assert.equal(state.data.events[0].commands[0].monster_keys[0], 'Giant Spider');
  assert.equal(state.dirty, true);
  assert.equal(state.history.length, 1);
  assert.equal(state.commandDraft, null);
  const html = context.renderCommandList(state.data.events[0].commands, '', 'なし');
  assert.match(html, /data-command-type="0"/);
  assert.match(html, /data-command-field="battle_id"/);
  assert.match(html, /data-battle-monster-index="0"/);
  assert.doesNotMatch(html, /data-draft-command/);
});

test('canceling a draft leaves the source and undo history untouched', () => {
  const { state, context } = editor();
  context.openCommandDraft('');
  context.cancelCommandDraft();

  assert.equal(state.commandDraft, null);
  assert.equal(state.data.events[0].commands.length, 0);
  assert.equal(state.history.length, 0);
  assert.equal(state.dirty, false);
});

test('flash command starts with the supported color', () => {
  const { state, context } = editor();
  context.openCommandDraft('');
  context.selectDraftCommand('', 'flash_screen');

  assert.deepEqual(JSON.parse(context.requestBody()).data.events[0].commands[0], {
    command: 'flash_screen', color: 'white',
  });
  assert.match(context.renderCommand(state.data.events[0].commands[0], '0', '', 0), /data-command-field="color"/);
});

test('changing an existing command replaces its fields and undo restores them', () => {
  const { state, context } = editor();
  context.openCommandDraft('');
  context.selectDraftCommand('', 'start_battle');

  context.changeCommandType('0', 'set_flag');

  assert.deepEqual(JSON.parse(context.requestBody()).data.events[0].commands[0], {
    command: 'set_flag', flag_id: 'story.done',
  });
  const html = context.renderCommandList(state.data.events[0].commands, '', 'なし');
  assert.match(html, /data-command-field="flag_id"/);
  assert.doesNotMatch(html, /data-command-field="battle_id"/);

  context.undo();
  assert.equal(state.data.events[0].commands[0].command, 'start_battle');
  assert.equal(state.data.events[0].commands[0].battle_id, 'battle_1');
});

test('the same picker adds a command inside a branch', () => {
  const { state, context } = editor();
  state.data.events[0].commands.push({
    command: 'branch', condition: { type: 'flag_set', flag_id: 'story.done' },
    then: [], else: [],
  });

  context.openCommandDraft('0/then');
  assert.match(context.renderCommandList(state.data.events[0].commands[0].then, '0/then', 'なし'), /data-draft-command="0\/then"/);
  context.selectDraftCommand('0/then', 'end_event');

  assert.equal(state.data.events[0].commands[0].then[0].command, 'end_event');
  assert.equal(state.data.events[0].commands[0].else.length, 0);
});
