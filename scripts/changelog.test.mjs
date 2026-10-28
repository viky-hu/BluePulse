import assert from 'node:assert/strict';
import { test } from 'node:test';
const data = await import('../src/app/changelog/_data.ts').catch(() => null);
const state = await import('../src/app/_lib/site-state.ts').catch(() => null);
const http = await import('../src/app/_lib/site-json.ts').catch(() => null);
const release = (date, time, kind) => ({ date, time, kind, title: '真实变化', body: ['正文'] });
test('changelog rejects impossible dates, unsorted releases and mismatched version', () => {
  assert.ok(data, 'changelog parser is implemented');
  const valid = { latestVersion: '2026-10-28T12:00', releases: [release('2026-10-28','12:00','更新')] };
  assert.deepEqual(data.parseChangelog(valid), valid);
  for (const patch of [ { releases: [release('2026-02-30','12:00','更新')] }, { latestVersion: '2026-10-27T12:00' }, { releases: [release('2026-10-27','12:00','更新'), release('2026-10-28','12:00','更新')] } ]) assert.throws(() => data.parseChangelog({...valid,...patch}));
});
test('type filtering changes month counts and jump targets together', () => {
  assert.ok(data);
  const rows = [release('2026-10-28','12:00','更新'),release('2026-10-27','12:00','优化'),release('2026-09-23','12:00','优化'),release('2026-09-21','12:00','更新')];
  assert.deepEqual(data.monthIndex(data.groupReleases(rows,'优化')), [{month:'2026-10', first:'2026-10-27',count:1},{month:'2026-09',first:'2026-09-23',count:1}]);
  assert.equal(data.groupReleases(rows,'公告').size,0);
  assert.deepEqual(data.dateHeading('2026-10-28'), {label:'2026 年 10 月 28 日',weekday:'周三'});
});
test('seen versions synchronize, never regress and survive storage denial', () => {
  assert.ok(state, 'site state store is implemented');
  const values = new Map(), events = new EventTarget(); let denied = false;
  const storage = {getItem:k=>values.get(k)??null,setItem:(k,v)=>{if(denied)throw Error();values.set(k,v);}};
  const store=state.createSiteStateStore(false,{storage:()=>storage,eventTarget:events});
  let calls=0; const stop=store.subscribe(()=>calls++); store.hydrate();
  store.markSeen('2026-10-28T12:00');store.markSeen('2026-09-21T12:00');
  assert.equal(store.getSnapshot().seen,'2026-10-28T12:00');
  denied=true;store.markSeen('2026-10-29T12:00');assert.equal(store.getSnapshot().seen,'2026-10-29T12:00');
  assert.ok(calls>=2);stop();
  const other=state.createSiteStateStore(true,{storage:()=>storage,eventTarget:events});other.hydrate();assert.equal(other.getSnapshot().seen,null);
});
test('conditional site JSON returns cache validators and an empty 304 body', async () => {
  assert.ok(http, 'site JSON responder is implemented');
  const first=http.siteJson(new Request('http://local/api'),{value:1},300);
  assert.match(first.headers.get('cache-control'),/max-age=300/);
  const tag=first.headers.get('etag');assert.ok(tag);
  const next=http.siteJson(new Request('http://local/api',{headers:{'if-none-match':`W/${tag}, "other"`}}),{value:1},300);
  assert.equal(next.status,304);assert.equal(await next.text(),'');
  assert.equal(http.siteJson(new Request('http://local/api',{headers:{'if-none-match':tag}}),{value:2},300).status,200);
});
