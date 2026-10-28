import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createBrowserState, browserKeys } from '../src/app/_lib/browser-state.ts';
import { saveSessionSnapshot, readSessionSnapshot, invalidateSessionSnapshot } from '../src/app/_lib/session-restore.ts';
class StorageMock {
  data = new Map(); fail = false;
  get length() { return this.data.size; }
  key(i) { return [...this.data.keys()][i] ?? null; }
  getItem(k) { return this.data.get(k) ?? null; }
  setItem(k,v) { if(this.fail) throw Error('quota'); this.data.set(k,v); }
  removeItem(k) { this.data.delete(k); }
}
const id = n => `00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const star = n => ({id:id(n),title:`Title ${n}`,summary:null,sourceName:'Source',publishedAt:null,score:3});
const article = n => ({ id:id(n),title:`Title ${n}`,source_title:'Original',published_at:null,language:'en',region:null,country_code:null,url:'https://example.com',source:{id:'s',name:'Source',slug:'s',region:null,country_code:null,language:'en',source_type:'rss',topics:[]},importance_score:3,processing_status:'ready',parse_status:'ready' });
const setup = mock => { const storage = new StorageMock(); const events = new EventTarget(); const store = createBrowserState(mock,{storage:()=>storage,eventTarget:events,now:()=>new Date('2026-10-11T00:00:00Z')}); return {storage,events,store}; };
test('stable snapshots, hydrate, immediate notifications and exact entry marker',()=>{
 const {store,storage}=setup(); assert.equal(store.getSnapshot(),store.getSnapshot()); let count=0; const stop=store.subscribe(()=>count++); store.hydrate(); store.markEntered(); store.toggleStar(star(1)); assert.equal(count,3); assert.equal(storage.getItem(browserKeys().entry),'1'); assert.equal(store.getSnapshot().starred[0].id,id(1)); store.toggleStar(star(1)); assert.equal(store.getSnapshot().starred.length,0); stop();
});
test('corrupt data is preserved while restricted writes retain memory edits',()=>{
 const {store,storage}=setup(); storage.setItem(browserKeys().starred,'broken'); store.hydrate(); store.toggleStar(star(1)); assert.equal(storage.getItem(browserKeys().starred),'broken'); assert.equal(store.getSnapshot().starred.length,1); assert.match(store.getSnapshot().notice,/本次访问/); storage.fail=true; store.toggleStar(star(2)); assert.equal(store.getSnapshot().starred.length,2);
});
test('cross tab changes, fresh read before writes, namespace isolation and unsubscribe',()=>{
 const {store,storage,events}=setup(); const stop=store.subscribe(()=>{}); store.hydrate(); const saved={...star(1),savedAt:'2026-10-11T00:00:00Z'}; storage.setItem(browserKeys().starred,JSON.stringify([saved])); store.toggleStar(star(2)); assert.equal(store.getSnapshot().starred.length,2);
 const event=k=>{const e=new Event('storage'); Object.defineProperty(e,'key',{value:k}); events.dispatchEvent(e);}; storage.setItem(browserKeys().entry,'1'); event(browserKeys(true).entry); assert.equal(store.getSnapshot().entered,false); event(browserKeys().entry); assert.equal(store.getSnapshot().entered,true); stop(); storage.removeItem(browserKeys().entry); event(browserKeys().entry); assert.equal(store.getSnapshot().entered,true);
});
test('history compatibility, deduplication, limits and UUID validation',()=>{
 const {store,storage}=setup(); storage.setItem(browserKeys().history,JSON.stringify([{article:article(1),viewedAt:'2026-10-10T00:00:00Z'}])); store.hydrate(); store.recordRead(article(1)); assert.equal(store.getSnapshot().history.length,1); for(let n=2;n<35;n++)store.recordRead(article(n)); assert.equal(store.getSnapshot().history.length,30);
 storage.setItem(browserKeys().starred,JSON.stringify(Array.from({length:500},(_,i)=>({...star(i),savedAt:'2026-10-11T00:00:00Z'})))); store.toggleStar(star(501)); assert.equal(store.getSnapshot().starred.length,500); assert.equal(store.getSnapshot().starred[0].id,id(501)); store.toggleStar({...star(1),id:'bad'}); assert.equal(store.getSnapshot().starred.length,500); store.removeStar(id(501)); assert.equal(store.getSnapshot().starred.length,499);
});
test('blocked storage getter permits in memory entry and reading',()=>{const store=createBrowserState(false,{storage:()=>{throw Error('blocked');}}); store.hydrate(); store.markEntered(); store.recordRead(article(1)); assert.equal(store.getSnapshot().entered,true); assert.equal(store.getSnapshot().history.length,1);});

test('invalidating feed data preserves its independent return position and recoverable damaged data',()=>{
 const storage=new StorageMock(); globalThis.window={sessionStorage:storage};
 try {
  saveSessionSnapshot('feed:/invalidate',{revision:1}); saveSessionSnapshot('position:/invalidate',{top:450});
  invalidateSessionSnapshot('feed:/invalidate');
  assert.equal(readSessionSnapshot('feed:/invalidate'),null);
  assert.deepEqual(readSessionSnapshot('position:/invalidate'),{top:450});
  const key='blue-pulse-session-v1:live:damaged-invalidation'; storage.setItem(key,'{broken');
  invalidateSessionSnapshot('damaged-invalidation'); assert.equal(storage.getItem(key),'{broken');
 } finally { delete globalThis.window; }
});
test('star snapshots exclude full text and invalid dates; failed writes survive subsequent edits',()=>{
 const {store,storage}=setup(); store.hydrate(); store.toggleStar({...star(1),source_body:'private full text'}); assert.equal('source_body' in store.getSnapshot().starred[0],false); store.toggleStar({...star(2),publishedAt:'invalid'}); assert.equal(store.getSnapshot().starred.length,1); storage.fail=true; store.toggleStar(star(2)); store.removeStar(id(1)); assert.deepEqual(store.getSnapshot().starred.map(v=>v.id),[id(2)]); assert.match(store.getSnapshot().notice,/本次访问/);
 const mocked=createBrowserState(true,{storage:()=>storage}); mocked.hydrate(); assert.equal(mocked.getSnapshot().starred.length,0); mocked.toggleStar({...star(1),id:'mock-card'}); assert.equal(mocked.getSnapshot().starred[0].id,'mock-card');
});
test('session validates version, timestamps and JSON and works with denied storage getter',()=>{
 const storage=new StorageMock(); globalThis.window={sessionStorage:storage};
 try { for(const value of ['broken',JSON.stringify({version:2,savedAt:Date.now(),value:1}),JSON.stringify({version:1,savedAt:Date.now()+60000,value:1})]) { storage.setItem('blue-pulse-session-v1:live:invalid',value); assert.equal(readSessionSnapshot('invalid'),null); }
 Object.defineProperty(globalThis.window,'sessionStorage',{get(){throw Error('denied');}}); saveSessionSnapshot('denied',{value:2}); assert.deepEqual(readSessionSnapshot('denied'),{value:2}); } finally {delete globalThis.window;}
});
test('session expiry does not renew on read, separates namespaces and caps entries',()=>{
 const storage=new StorageMock(); globalThis.window={sessionStorage:storage}; const original=Date.now; let time=1800000000000; Date.now=()=>time;
 try { saveSessionSnapshot('/home?cursor=one',{value:1}); assert.deepEqual(readSessionSnapshot('/home?cursor=one'),{value:1}); assert.equal(readSessionSnapshot('/home?cursor=one',true),null); time+=29*60000; assert.ok(readSessionSnapshot('/home?cursor=one')); time+=60001; assert.equal(readSessionSnapshot('/home?cursor=one'),null); for(let i=0;i<21;i++)saveSessionSnapshot(`page-${i}`,{i}); assert.equal(readSessionSnapshot('page-0'),null); assert.equal(storage.length,20); storage.fail=true; saveSessionSnapshot('memory',{ok:true}); assert.deepEqual(readSessionSnapshot('memory'),{ok:true}); } finally { Date.now=original; delete globalThis.window; }
});
test('damaged session values survive reads, other saves, same-key saves and memory eviction',()=>{
 const storage=new StorageMock(); globalThis.window={sessionStorage:storage};
 const values=['{broken',JSON.stringify({version:99,savedAt:Date.now(),value:1}),JSON.stringify({version:1,savedAt:'bad',value:1}),JSON.stringify({version:1,savedAt:Date.now()+60000,value:1})];
 try {
  values.forEach((raw,i)=>{ const key=`preserve-${i}`; const full=`blue-pulse-session-v1:mock:${key}`; storage.setItem(full,raw); assert.equal(readSessionSnapshot(key,true),null); assert.equal(storage.getItem(full),raw); });
  storage.setItem('blue-pulse-session-v1:mock:unread-corrupt','{unread');
  saveSessionSnapshot('other',{ok:true},true);
  assert.equal(storage.getItem('blue-pulse-session-v1:mock:unread-corrupt'),'{unread');
  values.forEach((raw,i)=>{const key=`preserve-${i}`; saveSessionSnapshot(key,{recovered:i},true); assert.deepEqual(readSessionSnapshot(key,true),{recovered:i}); assert.equal(storage.getItem(`blue-pulse-session-v1:mock:${key}`),raw);});
  const direct='blue-pulse-session-v1:mock:direct-corrupt'; storage.setItem(direct,'unknown'); saveSessionSnapshot('direct-corrupt',{ok:true},true); assert.equal(storage.getItem(direct),'unknown');
  for(let i=0;i<22;i++) saveSessionSnapshot(`evict-${i}`,{i},true);
  values.forEach((raw,i)=>assert.equal(storage.getItem(`blue-pulse-session-v1:mock:preserve-${i}`),raw)); assert.equal(storage.getItem(direct),'unknown');
  storage.setItem('blue-pulse-session-v1:mock:valid-expired',JSON.stringify({version:1,savedAt:Date.now()-1800001,value:1})); assert.equal(readSessionSnapshot('valid-expired',true),null); assert.equal(storage.getItem('blue-pulse-session-v1:mock:valid-expired'),null);
 } finally {delete globalThis.window;}
});
