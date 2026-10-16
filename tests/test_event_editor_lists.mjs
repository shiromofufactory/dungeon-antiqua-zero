import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../tools/event_editor/static/app.js', import.meta.url), 'utf8');
const names = ['filteredList', 'listEnd', 'setIdFilter', 'listForKind', 'insertListItem', 'moveListItem',
  'renderLists', 'renderListDropZone', 'currentFlag', 'currentEvent', 'currentMission', 'currentMessage',
  'snapshot', 'begin', 'commit', 'restore', 'normalize', 'undo', 'redo', 'uniqueId', 'addEvent',
  'eventIdPrefix', 'requestBody', 'savePendingActorEventLink'];
const declarations = names.map((name) => {
  const start = source.search(new RegExp(`(?:async )?function ${name}\\(`));
  assert.notEqual(start, -1);
  const next = source.slice(start + 1).search(/\n(?:async )?function /);
  assert.notEqual(next, -1);
  return source.slice(start, start + next + 1);
}).join('\n');

function editor() {
  const ids = ['common.first', 'forest.other', 'common.last', 'village.hidden'];
  const state = {
    data: { format_version: 1, events: ids.map((id) => ({ id, commands: [], note: 'common note' })) },
    flags: ids.map((id) => ({ flag_id: id, note: 'common note' })),
    missions: ids.map((id) => ({ id: id.replace('.', '_'), message_id: id })),
    messages: ids.map((id) => ({ message_id: id, text_ja: ['common body'] })),
    selectedFlag: 2, selectedEvent: 2, selectedMission: 2, selectedMessage: 2,
    filterText: '', mode: 'event', dirty: false, history: [], future: [],
  };
  const nodes = new Map();
  const node = (id) => {
    if (!nodes.has(id)) nodes.set(id, { innerHTML: '', className: '' });
    return nodes.get(id);
  };
  const context = vm.createContext({ state, LIST_TABS: ['flag', 'event', 'mission', 'message'],
    document: { querySelectorAll: () => [] }, $: node, render() {}, schedule() {}, clearListItemDrag() {},
    esc: (value) => String(value ?? ''), noteSummary: (value) => value,
    pendingActorEventDraft: null, pendingActorEventDraftId: null, actorEventReturnMapId: null,
    sessionStorage: { removeItem() {} },
  });
  vm.runInContext(declarations, context);
  return { state, context, node };
}

for (const [kind, idField, listNode] of [
  ['flag', 'flag_id', 'flags'], ['event', 'id', 'events'],
  ['mission', 'id', 'missions'], ['message', 'message_id', 'messages'],
]) {
  test(`${kind}: ID substring filtering preserves original indices, selection and full save payload`, () => {
    const { state, context, node } = editor();
    state.mode = kind;
    const before = context.requestBody();
    context.setIdFilter('  CoMmOn  ');
    const rows = context.filteredList(kind);
    assert.deepEqual(Array.from(rows, (row) => row.index), [0, 2]);
    const html = node(listNode).innerHTML;
    assert.match(html, /data-index="2"/);
    assert.doesNotMatch(html, /data-index="1"/);
    assert.match(html, /data-list-drop-index="3"/);
    assert.doesNotMatch(html, /data-list-drop-index="4"/);
    assert.equal(state[`selected${kind[0].toUpperCase()}${kind.slice(1)}`], 2);
    assert.equal(context.requestBody(), before);
    assert.equal(state.dirty, false);
    assert.equal(state.history.length, 0);
    context.setIdFilter('no_match');
    assert.equal(context.filteredList(kind).length, 0);
    assert.match(node(listNode).innerHTML, /一致するIDはありません/);
    context.setIdFilter('');
    assert.equal(context.filteredList(kind).length, 4);
    assert.equal(context.requestBody(), before);
  });

  test(`${kind}: reordering filtered rows uses source indices and supports undo/redo`, () => {
    const { state, context } = editor();
    context.setIdFilter('common');
    const records = context.listForKind(kind);
    const original = records.map((item) => item[idField]);
    assert.equal(context.moveListItem(kind, 2, 0), true);
    assert.deepEqual(records.map((item) => item[idField]), [original[2], original[0], original[1], original[3]]);
    assert.equal(state[`selected${kind[0].toUpperCase()}${kind.slice(1)}`], 0);
    context.undo();
    assert.deepEqual(Array.from(context.listForKind(kind), (item) => item[idField]), original);
    context.redo();
    assert.equal(context.listForKind(kind)[0][idField], original[2]);
  });
}

test('adding a hidden item clears the filter and selects its original index', () => {
  const { state, context } = editor();
  context.setIdFilter('common');
  context.insertListItem('flag', { flag_id: 'new_flag' });
  assert.equal(state.filterText, '');
  assert.equal(context.currentFlag().flag_id, 'new_flag');
});

test('new events store complete IDs and avoid collisions across prefixes', () => {
  const { state, context } = editor();
  const created = context.addEvent();
  assert.equal(created.id, 'common.event_1');
  assert.equal(context.addEvent().id, 'common.event_2');
  context.pendingActorEventDraft = { data: { map_id: 'cave_b2', area_parent_id: 'cave' } };
  assert.equal(context.addEvent(true).id, 'cave.event_1');
  assert.equal(state.pendingActorEventId, 'cave.event_1');
  assert.equal(JSON.parse(context.requestBody()).namespace, undefined);
});

test('actor event links save the complete ID without adding the prefix twice', async () => {
  const { state, context } = editor();
  context.pendingActorEventDraftId = 'draft';
  context.pendingActorEventDraft = { actor_id: 'guide', data: {
    map_id: 'cave_b2', area_parent_id: 'cave', actors: [{ id: 'guide' }],
    event_triggers: [{ anchor: { kind: 'actor', actor_id: 'guide' }, event_id: '' }],
  } };
  const created = context.addEvent(true);
  let saved;
  context.mapApi = async (_path, options) => { saved = JSON.parse(options.body); return { saved: true }; };
  await context.savePendingActorEventLink();
  assert.equal(saved.data.event_triggers[0].event_id, created.id);
  assert.equal(created.id, 'cave.event_1');
  assert.equal(state.pendingActorEventId, null);
});
