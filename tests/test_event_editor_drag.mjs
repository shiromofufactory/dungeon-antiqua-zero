import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../tools/event_editor/static/app.js', import.meta.url), 'utf8');
const names = ['snapshot', 'begin', 'commit', 'restore', 'undo', 'redo', 'normalize',
  'currentFlag', 'currentEvent', 'currentMission', 'currentMessage', 'listForKind', 'moveListItem',
  'commandAt', 'listAt', 'commandPath', 'isDescendantList', 'moveCommand'];
const declarations = names.map((name) => {
  const start = source.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, name);
  const next = source.slice(start + 1).search(/\n(?:async )?function /);
  assert.notEqual(next, -1, name);
  return source.slice(start, start + next + 1);
}).join('\n');
const dragStart = source.indexOf('function clearCommandDrag(');
const dragEnd = source.indexOf('$("undo").addEventListener', dragStart);
assert.notEqual(dragStart, -1);
assert.notEqual(dragEnd, -1);

function editor() {
  const nodes = [];
  function node(classes = '', dataset = {}, parent = null) {
    const tokens = new Set(classes.split(' ').filter(Boolean));
    const handlers = new Map();
    const result = {
      dataset, parent,
      classList: {
        add: (...values) => values.forEach((value) => tokens.add(value)),
        remove: (...values) => values.forEach((value) => tokens.delete(value)),
        contains: (value) => tokens.has(value),
        toggle: (value, enabled) => enabled ? tokens.add(value) : tokens.delete(value),
      },
      matches: (selector) => selector.split(',').some((part) => {
        if (part.includes(':not(.invalid)') && tokens.has('invalid')) return false;
        const positive = part.replaceAll(':not(.invalid)', '');
        return [...positive.matchAll(/\.([\w-]+)/g)].every(([, value]) => tokens.has(value))
          && [...positive.matchAll(/\[data-([\w-]+)(?:="([^"]*)")?\]/g)].every(([, key, value]) => {
            const actual = dataset[key.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())];
            return value === undefined ? actual !== undefined : actual === value;
          });
      }),
      closest: (selector) => result.matches(selector) ? result : parent?.closest(selector) || null,
      addEventListener: (type, handler) => {
        if (!handlers.has(type)) handlers.set(type, []);
        handlers.get(type).push(handler);
      },
      dispatch(type, event) {
        for (const handler of handlers.get(type) || []) handler(event);
        parent?.dispatch(type, event);
      },
    };
    nodes.push(result);
    return result;
  }
  const document = node();
  document.body = node('', {}, document);
  document.querySelectorAll = (selector) => nodes.filter((item) => item.matches(selector));
  document.querySelector = (selector) => document.querySelectorAll(selector)[0] || null;
  const sidebar = node('sidebar', {}, document.body);
  const commands = node('', {}, document.body);
  const outside = node('', {}, document.body);
  const state = {
    data: { format_version: 1, events: ['first', 'second', 'third'].map((id) => ({
      id, commands: [{ command: 'wait', frames: 1 }, { command: 'wait', frames: 2 },
        { command: 'branch', condition: { type: 'any_member_dead' }, then: [], else: [] }],
    })) },
    flags: ['first', 'second', 'third'].map((flag_id) => ({ flag_id })),
    missions: ['first', 'second', 'third'].map((id) => ({ id })),
    messages: ['first', 'second', 'third'].map((message_id) => ({ message_id })),
    selectedFlag: 0, selectedEvent: 0, selectedMission: 0, selectedMessage: 0,
    mode: 'event', history: [], future: [], dirty: false,
  };
  const context = vm.createContext({ state, document, $: () => commands,
    LIST_TABS: ['flag', 'event', 'mission', 'message'], render() {}, schedule() {} });
  vm.runInContext(`let draggedCommand = null; let draggedListItem = null;\n${declarations}\n${source.slice(dragStart, dragEnd)}`, context);
  function fire(type, target) {
    const event = { target, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; },
      dataTransfer: { setData() {}, dropEffect: 'none' } };
    target.dispatch(type, event);
    return event;
  }
  function commandDrag(index = 0, listPath = '') {
    const card = node('command', {}, commands);
    const handle = node('', { commandDrag: '', index: String(index), listPath }, card);
    fire('dragstart', handle);
    return handle;
  }
  const commandZone = (index, listPath = '') => node('command-drop-zone', {
    dropListPath: listPath, dropIndex: String(index),
  }, commands);
  const listZone = (kind, index) => node('list-drop-zone', {
    listDropKind: kind, listDropIndex: String(index),
  }, sidebar);
  return { state, context, node, fire, sidebar, commands, outside, commandDrag, commandZone, listZone };
}

test('command drops outside the highlighted frame use it and remain one undo step', () => {
  const { state, context, fire, outside, commandDrag, commandZone } = editor();
  const zone = commandZone(3);
  commandDrag();
  fire('dragover', zone);
  assert.equal(zone.classList.contains('active'), true);
  assert.equal(fire('dragover', outside).defaultPrevented, true);
  assert.equal(fire('drop', outside).defaultPrevented, true);
  assert.deepEqual(state.data.events[0].commands.map((command) => command.frames), [2, undefined, 1]);
  assert.equal(zone.classList.contains('active'), false);
  assert.equal(state.history.length, 1);
  context.undo();
  assert.deepEqual(Array.from(state.data.events[0].commands, (command) => command.frames), [1, 2, undefined]);
  context.redo();
  assert.equal(state.data.events[0].commands[2].frames, 1);
  assert.equal(fire('drop', outside).defaultPrevented, false);
  assert.equal(state.history.length, 1);
});

test('moving onto another command frame replaces the highlighted destination', () => {
  const { state, fire, outside, commandDrag, commandZone } = editor();
  const first = commandZone(3);
  const next = commandZone(2);
  commandDrag();
  fire('dragover', first);
  fire('dragover', next);
  assert.equal(first.classList.contains('active'), false);
  assert.equal(next.classList.contains('active'), true);
  fire('drop', outside);
  assert.deepEqual(state.data.events[0].commands.map((command) => command.frames), [2, 1, undefined]);
});

test('a drop follows the displayed command frame even when its event target is another frame', () => {
  const { state, fire, commandDrag, commandZone } = editor();
  const highlighted = commandZone(3);
  const other = commandZone(1);
  commandDrag();
  fire('dragover', highlighted);
  fire('drop', other);
  assert.deepEqual(state.data.events[0].commands.map((command) => command.frames), [2, undefined, 1]);
});

test('highlighted branch lists accept an outside drop while descendants remain invalid', () => {
  const { state, fire, outside, commandDrag, commandZone } = editor();
  const nested = commandZone(0, '2/then');
  commandDrag();
  fire('dragover', nested);
  fire('drop', outside);
  assert.equal(state.data.events[0].commands[1].then[0].frames, 1);

  const invalid = commandZone(0, '1/then');
  commandDrag(1);
  assert.equal(invalid.classList.contains('invalid'), true);
  assert.equal(fire('dragover', invalid).defaultPrevented, false);
  assert.equal(invalid.classList.contains('active'), false);
  assert.equal(fire('drop', invalid).defaultPrevented, false);
  assert.equal(state.history.length, 1);
});

for (const kind of ['flag', 'event', 'mission', 'message']) {
  test(`${kind}: highlighted list frame accepts drops outside the sidebar and preserves selection and undo`, () => {
    const { state, context, node, fire, sidebar, outside, listZone } = editor();
    const zone = listZone(kind, 3);
    const item = node('reorderable-list-item', {}, sidebar);
    const handle = node('', { listItemDrag: '', listKind: kind, index: '0' }, item);
    fire('dragstart', handle);
    fire('dragover', zone);
    assert.equal(zone.classList.contains('active'), true);
    assert.equal(fire('dragover', outside).defaultPrevented, true);
    assert.equal(fire('drop', outside).defaultPrevented, true);
    const id = (record) => record.flag_id || record.message_id || record.id;
    assert.deepEqual(Array.from(context.listForKind(kind), id), ['second', 'third', 'first']);
    assert.equal(state[`selected${kind[0].toUpperCase()}${kind.slice(1)}`], 2);
    assert.equal(zone.classList.contains('active'), false);
    assert.equal(state.history.length, 1);
    context.undo();
    assert.deepEqual(Array.from(context.listForKind(kind), id), ['first', 'second', 'third']);
    context.redo();
    assert.deepEqual(Array.from(context.listForKind(kind), id), ['second', 'third', 'first']);
  });
}

test('ending a drag clears its highlight, and external drags cannot reorder commands', () => {
  const { state, fire, outside, commandDrag, commandZone } = editor();
  const zone = commandZone(3);
  assert.equal(fire('dragover', zone).defaultPrevented, false);
  assert.equal(fire('drop', zone).defaultPrevented, false);
  const handle = commandDrag();
  fire('dragover', zone);
  fire('dragend', handle);
  assert.equal(zone.classList.contains('active'), false);
  assert.equal(fire('dragover', outside).defaultPrevented, false);
  assert.equal(fire('drop', outside).defaultPrevented, false);
  assert.equal(state.history.length, 0);
});
