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
  'field', 'options', 'noteSummary', 'flagOptions', 'renderCommand', 'renderDropZone',
  'renderCommandList', 'addCommand', 'defaultCondition', 'defaultCommand',
  'addDefaultCommand',
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
    history: [], future: [], dirty: false,
  };
  let focused = 0;
  const context = vm.createContext({
    state, LIST_TABS: ['flag', 'event', 'mission', 'message'],
    document: { querySelector: () => ({ focus: () => { focused += 1; } }) },
    CSS: { escape: (value) => value },
    render() {}, schedule() {}, renderMessagePreview: () => '', esc: (value) => String(value ?? ''),
  });
  vm.runInContext(`${source.slice(optionStart, optionEnd)}\n${declarations}`, context);
  return { state, context, focused: () => focused };
}

test('add button creates a message command with its fields and permits changing its type', () => {
  const { state, context, focused } = editor();

  context.addDefaultCommand('');

  assert.equal(focused(), 1);
  assert.equal(state.data.events[0].commands[0].command, 'message');
  assert.equal(state.dirty, true);
  assert.equal(state.history.length, 1);
  assert.match(context.renderCommandList(state.data.events[0].commands, '', 'なし'), /data-command-field="message_id"/);
  assert.doesNotMatch(context.renderCommandList(state.data.events[0].commands, '', 'なし'), /data-command-field="battle_id"/);

  context.changeCommandType('0', 'start_battle');

  assert.equal(state.data.events[0].commands[0].command, 'start_battle');
  assert.equal(state.data.events[0].commands[0].monster_keys[0], 'Giant Spider');
  assert.equal(state.dirty, true);
  assert.equal(state.history.length, 2);
  const html = context.renderCommandList(state.data.events[0].commands, '', 'なし');
  assert.match(html, /data-command-type="0"/);
  assert.match(html, /data-command-field="battle_id"/);
  assert.match(html, /data-battle-monster-index="0"/);
  assert.doesNotMatch(html, /data-draft-command/);
});

test('undo removes the added default message and redo restores it', () => {
  const { state, context } = editor();
  context.addDefaultCommand('');
  context.undo();

  assert.equal(state.data.events[0].commands.length, 0);
  assert.equal(state.history.length, 0);
  context.redo();
  assert.equal(state.data.events[0].commands[0].command, 'message');
});

test('flash command starts with the supported color', () => {
  const { state, context } = editor();
  context.addDefaultCommand('');
  context.changeCommandType('0', 'flash_screen');

  assert.deepEqual(JSON.parse(context.requestBody()).data.events[0].commands[0], {
    command: 'flash_screen', color: 'white',
  });
  assert.match(context.renderCommand(state.data.events[0].commands[0], '0', '', 0), /data-command-field="color"/);
});

test('changing an existing command replaces its fields and undo restores them', () => {
  const { state, context } = editor();
  context.addDefaultCommand('');
  context.changeCommandType('0', 'start_battle');

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

test('branch commands also default to message and can change type', () => {
  const { state, context } = editor();
  state.data.events[0].commands.push({
    command: 'branch', condition: { type: 'flag_set', flag_id: 'story.done' },
    then: [], else: [],
  });

  context.addDefaultCommand('0/then');
  assert.equal(state.data.events[0].commands[0].then[0].command, 'message');
  context.changeCommandType('0/then/0', 'end_event');

  assert.equal(state.data.events[0].commands[0].then[0].command, 'end_event');
  assert.equal(state.data.events[0].commands[0].else.length, 0);
});
