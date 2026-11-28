import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../tools/event_editor/static/app.js', import.meta.url), 'utf8');
const optionStart = source.indexOf('const COMMAND_OPTIONS = [');
const optionEnd = source.indexOf('];', optionStart) + 2;
const changeHandlerStart = source.indexOf('$("event-editor").addEventListener("change",');
const changeHandlerEnd = source.indexOf('\nfunction clearCommandDrag(', changeHandlerStart + 1);
assert.notEqual(changeHandlerStart, -1);
assert.notEqual(changeHandlerEnd, -1);
const names = [
  'snapshot', 'begin', 'commit', 'restore', 'undo', 'redo', 'normalize',
  'battleIds', 'currentBattle', 'currentEvent', 'commandAt', 'conditionAt', 'listAt', 'commandPath', 'fullFlags', 'messageIds',
  'field', 'options', 'noteSummary', 'flagOptions', 'renderCommand', 'renderDropZone',
  'renderCommandList', 'addCommand', 'defaultCondition', 'defaultCommand',
  'addDefaultCommand', 'renderCondition',
  'changeCommandType', 'requestBody', 'renderBattleEditor',
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
    data: { format_version: 1, events: [{ id: 'sample.run', commands: [] }] },
    flags: [{ flag_id: 'story.done' }], reservedFlags: [], messages: [], missions: [],
    selectedEvent: 0, selectedFlag: 0, selectedMessage: 0, selectedMission: 0, selectedBattle: 0,
    mode: 'event', battles: [{battle_id:'guard',monster_keys:['Giant Spider']}], catalogs: { monster_keys: ['Giant Spider'] },
    history: [], future: [], dirty: false,
  };
  let focused = 0;
  const handlers = new Map();
  const editorNode = { addEventListener: (event, handler) => handlers.set(event, handler) };
  const context = vm.createContext({
    state, LIST_TABS: ['flag', 'event', 'mission', 'message'],
    document: { querySelector: () => ({ focus: () => { focused += 1; } }) },
    $: () => editorNode,
    CSS: { escape: (value) => value },
    render() {}, schedule() {}, renderMessagePreview: () => '', esc: (value) => String(value ?? ''),
  });
  vm.runInContext(`${source.slice(optionStart, optionEnd)}\n${declarations}`, context);
  vm.runInContext(source.slice(changeHandlerStart, changeHandlerEnd), context);
  return { state, context, handlers, editorNode, focused: () => focused };
}

test('reserved flags can be selected for set_flag and conditions', () => {
  const { state, context } = editor();
  const flagId = 'progress.teleport_unsealed';
  state.reservedFlags = [{ flag_id: flagId, note: 'テレポートを解放' }];
  assert.equal(context.defaultCommand('set_flag').flag_id, 'story.done');
  assert.match(
    context.renderCommand({command: 'set_flag', flag_id: flagId}, '0'),
    /value="progress.teleport_unsealed" selected>.*予約済み/,
  );
  assert.match(
    context.renderCondition({type: 'flag_set', flag_id: flagId}, '0', ''),
    /value="progress.teleport_unsealed" selected>.*予約済み/,
  );
});

test('event battle defeat event selects field events, clears the reference and supports undo', () => {
  const { state, context, handlers, editorNode } = editor();
  state.data.events.push({ id: 'sample.opening', battle_start_id: 'guard', commands: [] });
  context.renderBattleEditor();
  assert.match(editorNode.innerHTML, /data-battle-field="defeat_event_id"/);
  assert.match(editorNode.innerHTML, /value="sample.run"/);
  assert.doesNotMatch(editorNode.innerHTML, /value="sample.opening"/);

  const select = (value) => handlers.get('change')({ target: { dataset: { battleField: 'defeat_event_id' }, value } });
  const savedBattle = () => JSON.parse(context.requestBody()).battles[0];
  select('sample.run');
  assert.equal(savedBattle().defeat_event_id, 'sample.run');
  context.renderBattleEditor();
  assert.match(editorNode.innerHTML, /value="sample.run" selected/);
  select('');
  assert.equal('defeat_event_id' in savedBattle(), false);
  context.undo();
  assert.equal(savedBattle().defeat_event_id, 'sample.run');
  context.redo();
  assert.equal('defeat_event_id' in savedBattle(), false);
});

test('add button creates a message command with its fields and permits changing its type', () => {
  const { state, context, focused } = editor();

  context.addDefaultCommand('');

  assert.equal(focused(), 1);
  assert.equal(state.data.events[0].commands[0].command, 'message');
  assert.equal(state.dirty, true);
  assert.equal(state.history.length, 1);
  const initialHtml = context.renderCommandList(state.data.events[0].commands, '', 'なし');
  assert.match(initialHtml, /data-command-field="message_id"/);
  assert.match(initialHtml, /<option value="message" selected>メッセージを表示<\/option>/);
  assert.match(initialHtml, /<code>1\. メッセージを表示<\/code>/);
  assert.match(initialHtml, /<option value="stop_bgm"\s*>BGM停止<\/option>/);
  assert.match(initialHtml, /<option value="face_actor"\s*>アクターの向きを変更<\/option>/);
  assert.doesNotMatch(context.renderCommandList(state.data.events[0].commands, '', 'なし'), /data-command-field="battle_id"/);

  context.changeCommandType('0', 'start_battle');

  assert.equal(state.data.events[0].commands[0].command, 'start_battle');
  assert.equal(state.data.events[0].commands[0].battle_id, 'guard');
  assert.equal('monster_keys' in state.data.events[0].commands[0], false);
  assert.equal(state.dirty, true);
  assert.equal(state.history.length, 2);
  const html = context.renderCommandList(state.data.events[0].commands, '', 'なし');
  assert.match(html, /data-command-type="0"/);
  assert.match(html, /data-command-field="battle_id"/);
  assert.doesNotMatch(html, /data-battle-monster-index/);
  assert.match(html, /<select[^>]*data-command-field="battle_id"/);
  assert.doesNotMatch(html, /data-draft-command/);
});

test('NPC equipment picks compatible gear and restores the selection with undo', () => {
  const { state, context, handlers } = editor();
  Object.assign(state.catalogs, {
    character_keys: ['Fiora', 'Alvan'],
    npc_keys: ['Alvan'],
    equipment_item_keys_by_slot: { RIGHT: ['SWORD', 'AXE'], LEFT: ['SHIELD', 'SWORD'] },
  });
  context.addDefaultCommand('');
  context.changeCommandType('0', 'replace_npc_equipment');
  const saved = () => JSON.parse(context.requestBody()).data.events[0].commands[0];
  const html = () => context.renderCommand(saved(), '0', '', 0);
  const select = (commandField, value) => handlers.get('change')({
    target: { dataset: { commandPath: '0', commandField }, value },
  });
  assert.deepEqual(saved(), {
    command: 'replace_npc_equipment', character_key: 'Alvan', slot: 'RIGHT', item_key: '',
  });
  assert.match(html(), /NPCの装備を交換する/);
  assert.match(html(), /value="AXE"/);
  assert.doesNotMatch(html(), /value="Fiora"|value="SHIELD"/);
  select('item_key', 'AXE');
  select('slot', 'LEFT');
  assert.equal(saved().item_key, '');
  assert.match(html(), /value="SHIELD"/);
  assert.doesNotMatch(html(), /value="AXE"/);
  context.undo();
  assert.equal(saved().slot, 'RIGHT');
  assert.equal(saved().item_key, 'AXE');
  context.redo();
  assert.equal(saved().slot, 'LEFT');
  assert.equal(saved().item_key, '');
});

test('branch death condition saves no attributes and switching types supports undo and redo', () => {
  const { state, context, handlers } = editor();
  context.addDefaultCommand('');
  context.changeCommandType('0', 'branch');
  const original = JSON.parse(context.requestBody()).data.events[0].commands[0].condition;
  handlers.get('change')({ target: {
    dataset: { condCommand: '0', condPath: 'condition', condField: 'type' }, value: 'any_member_dead',
  } });
  const condition = JSON.parse(context.requestBody()).data.events[0].commands[0].condition;
  assert.deepEqual(condition, { type: 'any_member_dead' });
  const html = context.renderCondition(condition, '0', 'condition');
  assert.match(html, /value="any_member_dead" selected>誰かが死亡状態のとき<\/option>/);
  assert.doesNotMatch(html, /data-cond-field="(?:flag_id|character_key|quantity)"|子条件を追加/);
  context.undo();
  assert.deepEqual(JSON.parse(context.requestBody()).data.events[0].commands[0].condition, original);
  context.redo();
  assert.deepEqual(JSON.parse(context.requestBody()).data.events[0].commands[0].condition, condition);
  handlers.get('change')({ target: {
    dataset: { condCommand: '0', condPath: 'condition', condField: 'type' }, value: 'item_at_least',
  } });
  assert.equal(state.data.events[0].commands[0].condition.type, 'item_at_least');
  assert.equal(state.data.events[0].commands[0].condition.quantity, 1);
});

test('launch mode condition edits all four modes and supports undo and redo', () => {
  const { context, handlers } = editor();
  context.addDefaultCommand('');
  context.changeCommandType('0', 'branch');
  handlers.get('change')({ target: {
    dataset: { condCommand: '0', condPath: 'condition', condField: 'type' }, value: 'launch_mode',
  } });
  const condition = () => JSON.parse(context.requestBody()).data.events[0].commands[0].condition;
  assert.deepEqual(condition(), { type: 'launch_mode', mode: 'normal' });
  const html = context.renderCondition(condition(), '0', 'condition');
  for (const [mode, label] of [['normal', '通常モード'], ['exhibition', '試遊版モード'], ['demo', '体験版モード'], ['beta', 'βテスト版モード']]) {
    assert.match(html, new RegExp(`value="${mode}"[^>]*>${label}</option>`));
    handlers.get('change')({ target: {
      dataset: { condCommand: '0', condPath: 'condition', condField: 'mode' }, value: mode,
    } });
    assert.deepEqual(condition(), { type: 'launch_mode', mode });
  }
  context.undo();
  assert.equal(condition().mode, 'demo');
  context.redo();
  assert.equal(condition().mode, 'beta');
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

test('party recovery offers two commands and saves each without attributes', () => {
  const { state, context } = editor();
  context.addDefaultCommand('');
  for (const [command, label] of [
    ['recover_party', 'パーティ全快（復活含む）'],
    ['recover_party_without_revive', 'パーティ全快（復活除く）'],
  ]) {
    context.changeCommandType('0', command);
    assert.deepEqual(JSON.parse(context.requestBody()).data.events[0].commands[0], { command });
    const html = context.renderCommand(state.data.events[0].commands[0], '0', '', 0);
    assert.match(html, new RegExp(`value="${command}" selected>${label}</option>`));
    assert.doesNotMatch(html, /data-command-field=/);
  }
});

test('BGM stop replaces track selection, saves without attributes and permits undo', () => {
  const {state, context} = editor();
  state.catalogs.bgm_ids = ['da3-field'];
  context.addDefaultCommand('');
  context.changeCommandType('0', 'change_bgm');
  context.changeCommandType('0', 'stop_bgm');
  assert.deepEqual(JSON.parse(context.requestBody()).data.events[0].commands[0], {command:'stop_bgm'});
  const html = context.renderCommand(state.data.events[0].commands[0], '0', '', 0);
  assert.match(html, /フェードアウトして停止/);
  assert.doesNotMatch(html, /data-command-field="bgm_id"/);
  context.undo();
  assert.equal(state.data.events[0].commands[0].command, 'change_bgm');
  assert.equal(state.data.events[0].commands[0].bgm_id, 'da3-field');
  context.redo();
  assert.equal(state.data.events[0].commands[0].command, 'stop_bgm');
});

test('game reset is named in Japanese, saves without attributes and supports undo/redo', () => {
  const {state, context} = editor();
  state.catalogs.bgm_ids = ['da3-field'];
  context.addDefaultCommand('');
  context.changeCommandType('0', 'change_bgm');
  context.changeCommandType('0', 'reset_game');
  assert.deepEqual(JSON.parse(context.requestBody()).data.events[0].commands[0], {command: 'reset_game'});
  const html = context.renderCommand(state.data.events[0].commands[0], '0', '', 0);
  assert.match(html, /ゲームをリセット/);
  assert.match(html, /タイトル画面に戻ります/);
  assert.doesNotMatch(html, /data-command-field=/);
  context.undo();
  assert.equal(state.data.events[0].commands[0].command, 'change_bgm');
  assert.equal(state.data.events[0].commands[0].bgm_id, 'da3-field');
  context.redo();
  assert.equal(state.data.events[0].commands[0].command, 'reset_game');
});

test('give item message toggle saves boolean ON/OFF and supports undo without a take-item option', () => {
  const { state, context, handlers } = editor();
  state.catalogs.item_keys = ['POTION'];
  context.addDefaultCommand('');
  context.changeCommandType('0', 'give_item');
  assert.deepEqual(JSON.parse(context.requestBody()).data.events[0].commands[0], {
    command: 'give_item', item_key: 'POTION', quantity: 1, show_message: false,
  });
  handlers.get('change')({target: {dataset: {commandField: 'show_message', commandPath: '0'}, value: 'on', checked: true}});
  assert.equal(JSON.parse(context.requestBody()).data.events[0].commands[0].show_message, true);
  assert.match(context.renderCommand(state.data.events[0].commands[0], '0', '', 0), /type="checkbox"[^>]*data-command-field="show_message"[^>]*checked/);
  context.undo();
  assert.equal(state.data.events[0].commands[0].show_message, false);
  context.redo();
  handlers.get('change')({target: {dataset: {commandField: 'show_message', commandPath: '0'}, value: 'on', checked: false}});
  assert.equal(JSON.parse(context.requestBody()).data.events[0].commands[0].show_message, false);
  context.changeCommandType('0', 'take_item');
  assert.doesNotMatch(context.renderCommand(state.data.events[0].commands[0], '0', '', 0), /data-command-field="show_message"/);
  assert.equal('show_message' in state.data.events[0].commands[0], false);
});

test('wait uses a six-frame input and saves edited duration as an integer with undo', () => {
  const { state, context, handlers } = editor();
  context.addDefaultCommand('');
  context.changeCommandType('0', 'wait');
  assert.deepEqual(JSON.parse(context.requestBody()).data.events[0].commands[0], {
    command: 'wait', frames: 6,
  });
  const html = context.renderCommand(state.data.events[0].commands[0], '0', '', 0);
  assert.match(html, /type="number" min="6" step="6"/);
  assert.match(html, /data-command-field="frames"/);
  assert.doesNotMatch(html, /data-command-field="(?:steps|direction)"/);
  handlers.get('change')({ target: { dataset: { commandField: 'frames', commandPath: '0' }, value: '18' } });
  assert.equal(JSON.parse(context.requestBody()).data.events[0].commands[0].frames, 18);
  context.undo();
  assert.equal(state.data.events[0].commands[0].frames, 6);
  context.redo();
  assert.equal(state.data.events[0].commands[0].frames, 18);
});

test('screen commands save numeric brightness and six-frame shake duration with undo', () => {
  const { state, context, handlers } = editor();
  context.addDefaultCommand('');
  context.changeCommandType('0', 'change_brightness');
  assert.deepEqual(JSON.parse(context.requestBody()).data.events[0].commands[0], {command: 'change_brightness', percent: 100});
  let html = context.renderCommand(state.data.events[0].commands[0], '0', '', 0);
  for (const percent of [0, 25, 50, 75, 100]) assert.match(html, new RegExp(`value="${percent}"[^>]*>${percent}%`));
  handlers.get('change')({target: {dataset: {commandField: 'percent', commandPath: '0'}, value: '0'}});
  assert.equal(JSON.parse(context.requestBody()).data.events[0].commands[0].percent, 0);
  assert.match(context.renderCommand(state.data.events[0].commands[0], '0', '', 0), /value="0" selected>0%/);
  context.undo();
  assert.equal(state.data.events[0].commands[0].percent, 100);
  context.redo();
  assert.equal(state.data.events[0].commands[0].percent, 0);
  context.changeCommandType('0', 'shake_screen');
  assert.deepEqual(JSON.parse(context.requestBody()).data.events[0].commands[0], {command: 'shake_screen', frames: 6});
  html = context.renderCommand(state.data.events[0].commands[0], '0', '', 0);
  assert.match(html, /振動時間/);
  assert.match(html, /type="number" min="6" step="6"/);
  assert.doesNotMatch(html, /data-command-field="percent"/);
  handlers.get('change')({target: {dataset: {commandField: 'frames', commandPath: '0'}, value: '18'}});
  assert.equal(JSON.parse(context.requestBody()).data.events[0].commands[0].frames, 18);
  context.undo();
  assert.equal(state.data.events[0].commands[0].frames, 6);
});

test('facing commands select direction and actor without steps, with undo and redo', () => {
  const { state, context } = editor();
  state.catalogs.actor_ids = ['elder'];
  context.addDefaultCommand('');
  context.changeCommandType('0', 'face_party');
  assert.deepEqual(JSON.parse(context.requestBody()).data.events[0].commands[0], {
    command: 'face_party', direction: 'down',
  });
  let html = context.renderCommand(state.data.events[0].commands[0], '0', '', 0);
  assert.match(html, /data-command-field="direction"/);
  assert.doesNotMatch(html, /data-command-field="(?:actor_id|steps)"/);
  context.changeCommandType('0', 'face_actor');
  assert.deepEqual(JSON.parse(context.requestBody()).data.events[0].commands[0], {
    command: 'face_actor', actor_id: 'elder', direction: 'down',
  });
  html = context.renderCommand(state.data.events[0].commands[0], '0', '', 0);
  assert.match(html, /data-command-field="actor_id"/);
  assert.match(html, /data-command-field="direction"/);
  assert.doesNotMatch(html, /data-command-field="steps"/);
  context.undo();
  assert.equal(state.data.events[0].commands[0].command, 'face_party');
  context.redo();
  assert.equal(state.data.events[0].commands[0].command, 'face_actor');
  context.changeCommandType('0', 'move_actor');
  assert.match(context.renderCommand(state.data.events[0].commands[0], '0', '', 0), /data-command-field="steps"/);
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
  assert.equal(state.data.events[0].commands[0].battle_id, 'guard');
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
