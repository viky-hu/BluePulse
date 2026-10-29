import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createBrowserState, browserKeys } from '../src/app/_lib/browser-state.ts';

class Storage {
  data = new Map(); reject = new Set();
  getItem(key) { return this.data.get(key) ?? null; }
  setItem(key, value) { if (this.reject.has(key)) throw Error('quota'); this.data.set(key, value); }
}
const id = n => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const star = (n, savedAt = '2026-10-20T00:00:00Z') => ({ id:id(n), title:`新闻 ${n}`, summary:null, sourceName:'公开来源', publishedAt:null, score:null, savedAt });
const article = n => ({ id:id(n), title:`新闻 ${n}`, url:'https://example.com', source:{ name:'公开来源' } });
function setup(mock = false) {
  const storage = new Storage(), target = new EventTarget();
  const store = createBrowserState(mock, { storage:()=>storage, eventTarget:target, now:()=>new Date('2026-10-29T00:00:00Z') });
  return { storage, store, target, keys:browserKeys(mock) };
}
const bundle = (starred = [], read = []) => JSON.stringify({ version:1, starred, read, theme:'dark' });

test('migrates old history once and keeps read marks independent of thirty-entry history', () => {
  const { storage, store, keys } = setup();
  storage.setItem(keys.history, JSON.stringify([{ article:article(1), viewedAt:'2026-10-20T00:00:00Z' }]));
  store.hydrate(); assert.deepEqual(store.getSnapshot().readIds, [id(1)]);
  for(let i=2;i<=33;i++) store.recordRead(article(i));
  assert.equal(store.getSnapshot().history.length, 30); assert.equal(store.getSnapshot().readIds.length, 33);
  store.clearHistory(); store.hydrate();
  assert.deepEqual(store.getSnapshot().history, []); assert.equal(store.getSnapshot().readIds.length, 33);
  assert.equal(JSON.parse(storage.getItem(keys.read)).length,33);
});
test('version one merges without overwriting existing stars; export round trip omits arbitrary text', () => {
  const { storage, store, keys } = setup(); store.hydrate(); store.toggleStar(star(1));
  const report = store.importBundle(bundle([{...star(1), title:'覆盖'}, {...star(2,'2026-10-30T00:00:00Z'), source_body:'private'}, star(2)], [id(3),id(3)]));
  assert.deepEqual([report.starredAdded,report.readAdded,report.starredSkipped,report.readSkipped,report.readFailed],[1,1,0,0,false]);
  assert.deepEqual(store.getSnapshot().starred.map(s=>s.id),[id(2),id(1)]);
  assert.equal(store.getSnapshot().starred[1].title,'新闻 1');
  assert.equal(store.getSnapshot().history.length,0);
  const exported = store.exportBundle();
  assert.deepEqual(Object.keys(exported).sort(), ['read','starred','theme','version']);
  assert.equal(exported.theme,'auto'); assert.equal('source_body' in exported.starred[0],false);
  const other = setup(); other.store.hydrate(); other.store.importBundle(JSON.stringify(exported));
  assert.deepEqual(other.store.exportBundle(),exported);
  assert.equal(storage.getItem(keys.starred).includes('private'),false);
  assert.equal(store.importBundle(JSON.stringify(exported)).starredAdded,0);
});
test('invalid rows and overflow are counted; existing records keep their slots', () => {
  const { store } = setup(); store.hydrate(); store.toggleStar(star(1));
  const report = store.importBundle(bundle([...Array.from({length:501},(_,i)=>star(i+2)), {id:'aihot-id',title:'other site'}, null], [...Array.from({length:5001},(_,i)=>id(i+1)),'bad',null]));
  assert.equal(report.starredAdded,499); assert.equal(report.starredSkipped,4);
  assert.equal(report.readAdded,5000); assert.equal(report.readSkipped,3);
  assert.equal(store.getSnapshot().starred.some(s=>s.id===id(1)),true);
  store.recordRead(article(7000)); assert.equal(store.getSnapshot().readIds.length,5000); assert.equal(store.getSnapshot().readIds[0],id(7000));
});
test('bad files and corrupt persisted stars never overwrite recoverable data', () => {
  const { storage, store, keys } = setup();
  storage.setItem(keys.starred,'{broken'); store.hydrate();
  for (const file of ['{broken','null','{"version":2}', ' '.repeat(2_000_001)]) assert.throws(()=>store.importBundle(file));
  assert.throws(()=>store.importBundle(bundle([star(1)])),/无法读取/);
  assert.equal(storage.getItem(keys.starred),'{broken'); assert.equal(store.getSnapshot().starred.length,0);
});
test('failed star persistence reports failure without importing reads or memory records', () => {
  const { storage, store, keys } = setup(); store.hydrate();
  storage.reject.add(keys.starred);
  assert.throws(()=>store.importBundle(bundle([star(1)],[id(2)])),/存储/);
  assert.equal(store.getSnapshot().starred.length,0); assert.equal(store.getSnapshot().readIds.length,0);
  store.toggleStar(star(3)); assert.equal(store.getSnapshot().starred.length,1);
});
test('read persistence failure reports partial success and preserves prior read data', () => {
  const { storage, store, keys } = setup(); store.hydrate(); store.recordRead(article(3));
  storage.reject.add(keys.read);
  const result = store.importBundle(bundle([star(1)],[id(2)]));
  assert.equal(result.starredAdded,1); assert.equal(result.readAdded,0); assert.equal(result.readFailed,true);
  assert.deepEqual(store.getSnapshot().readIds,[id(3)]); assert.equal(store.getSnapshot().history.length,1);
});
test('fresh storage reads, same-tab subscription, cross-tab sync and mock namespace stay coherent', () => {
  const { storage, store, target, keys } = setup(); let notifications=0; const stop=store.subscribe(()=>notifications++); store.hydrate();
  storage.setItem(keys.starred,JSON.stringify([star(1)]));
  store.importBundle(bundle([star(2)],[id(3)])); assert.equal(store.getSnapshot().starred.length,2);
  const before=notifications; storage.setItem(keys.read,JSON.stringify([id(4)]));
  const event=new Event('storage'); Object.defineProperty(event,'key',{value:keys.read}); target.dispatchEvent(event);
  assert.deepEqual(store.getSnapshot().readIds,[id(4)]); assert.ok(notifications>before); stop();
  const mock=createBrowserState(true,{storage:()=>storage}); mock.hydrate(); assert.equal(mock.getSnapshot().starred.length,0); assert.equal(mock.getSnapshot().readIds.length,0);
});
