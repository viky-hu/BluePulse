import assert from 'node:assert/strict';
import { test } from 'node:test';
const load = async path => { const m = await import(`../src/app/daily/${path}.ts`).catch(() => null); assert.ok(m, `daily ${path} implementation must exist`); return m; };
const id = n => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const citation = (n, extra = {}) => ({ itemId: id(n), title: `资讯${n}`, summary: '公开资料摘要', sourceName: '公开来源', sourceUrl: 'https://example.com/news', sourceIconUrl: null, firstParty: true, publishedAt: '2026-11-01T00:00:00Z', available: true, ...extra });
const report = () => ({ kind: 'daily', key: '2026-11-01', issueNumber: 401, title: 'AI日报', generatedAt: '2026-11-01T00:00:00Z', lead: { title: '资讯1', leadParagraph: '公开资料摘要' }, leadItemId: id(1), overview: null, highlights: [citation(2)], sections: [{ label: '产品发布与更新', summary: null, items: [citation(1)] }, { label: '警务实战应用', summary: null, items: [citation(2)] }], flashes: [], cover: null, metrics: { totalEvents: 2, sourcesCount: 3, firstPartyEvents: 1 }, readingMinutes: 1, prev: '2026-10-31', next: null });
test('lead-only sections and cross-section duplicates do not create empty numbered pages', async () => {
  const { pagesOf, leadStoryOf, reportOutline } = await load('_paper'); const r = report();
  r.sections.push({ label: '空版', summary: null, items: [] }, { label: '重复版', summary: null, items: [citation(2)] }, { label: '论文研究进展', summary: null, items: [citation(3)] }); r.flashes = [citation(4)];
  const pages = pagesOf(r, leadStoryOf(r)); assert.deepEqual(pages.map(p => [p.id,p.label,p.items.map(c => c.itemId)]), [['s-2','警务实战应用',[id(2)]],['s-5','论文研究进展',[id(3)]]]);
  assert.deepEqual(reportOutline(r).map(o => [o.id,o.mark]), [['report-start',''],['s-2','01'],['s-5','02'],['s-flash','03']]);
});
test('a sole public lead is not a quiet issue and a withdrawn lead stays marked in its original section', async () => {
  const { pagesOf, leadStoryOf, reportOutline } = await load('_paper'); const r = report(); r.sections = [r.sections[0]]; r.highlights = [];
  assert.equal(leadStoryOf(r).itemId, id(1)); assert.equal(pagesOf(r, leadStoryOf(r)).length, 0); assert.deepEqual(reportOutline(r), []);
  r.sections[0].items[0].available = false; assert.equal(leadStoryOf(r), null); assert.equal(pagesOf(r, null)[0].items[0].available, false);
});
test('report parsing preserves every optional citation field, current issue number, and media shape', async () => {
  const { parseReportDetail, parseReportNavigation } = await load('_data'); const r = report();
  r.sections[1].items[0] = citation(2, { otherSources: 8, followUp: '2026-10-29', related: [citation(3, { summary: null })], sourceIconSrcSet: '/media/icon 1x' });
  r.cover = { url: '/media/cover', srcSet: '/media/cover 800w', width: null, height: null, caption: null };
  assert.deepEqual(parseReportDetail(r), r);
  const navigation = { items: [{ key: '2026-11-01', issueNumber: 401, title: null }, { key: '2026-10-01', issueNumber: 370 }] };
  const parsed = parseReportNavigation(navigation); assert.equal(parsed.items[0].title, null); assert.equal(Object.hasOwn(parsed.items[1], 'title'), false);
});
test('malformed reports, unsafe active links and invalid calendar dates cannot become empty issues', async () => {
  const { parseReportDetail, parseReportLatest } = await load('_data');
  for (const patch of [{ readingMinutes: NaN }, { key: '2026-02-30' }, { sections: undefined }, { cover: undefined }, { metrics: { totalEvents: -1 } }]) assert.throws(() => parseReportDetail({ ...report(), ...patch }));
  for (const patch of [{ sourceUrl: 'javascript:alert(1)' }, { sourceIconUrl: '//example.com/icon' }, { otherSources: -1 }, { followUp: '2026-02-30' }, { itemId: '../admin' }]) { const r = report(); r.sections[1].items = [citation(2, patch)]; assert.throws(() => parseReportDetail(r)); }
  assert.deepEqual(parseReportLatest({ index: [], report: null }), { index: [], report: null }); assert.throws(() => parseReportLatest({ index: [] }));
});
test('daily descendants participate in shared navigation while weeklies and malformed dates remain excluded', async () => {
  const { dailyRoute } = await load('_route');
  assert.deepEqual(dailyRoute('/daily'), { kind: 'latest' }); assert.deepEqual(dailyRoute('/daily/archive'), { kind: 'archive' }); assert.deepEqual(dailyRoute('/daily/2026-11-01'), { kind: 'detail', key: '2026-11-01' });
  for (const path of ['/daily/2026-02-30', '/daily/extra/nested', '/weekly']) assert.equal(dailyRoute(path), null);
  const { parseHomeRoute } = await import('../src/app/_components/home/home-routes.ts'); assert.equal(parseHomeRoute('/daily/archive','').valid, true); assert.equal(parseHomeRoute('/daily/2026-11-01','').valid,true);
});
test('detail may reuse for 120 seconds but consumed age, navigation and upstream deadlines win', async () => {
  const { dailyDeadline } = await load('_cache'); const now = Date.parse('2026-11-01T03:00:00Z');
  assert.equal(dailyDeadline(new Headers({ 'Cache-Control': 'max-age=120' }),120000,now), now + 120000);
  assert.equal(dailyDeadline(new Headers({ 'Cache-Control': 'max-age=120', Age: '115' }),120000,now), now + 5000);
  assert.equal(dailyDeadline(new Headers({ 'X-Accel-Expires': `@${(now+2000)/1000}` }),120000,now), now+2000);
  assert.equal(dailyDeadline(new Headers({ 'Cache-Control': 'no-store' }),120000,now), 0);
});
test('latest prefetch and enter share a request; refresh failure removes cached data without demo fallback', async t => {
  const { loadDailyPage, getCachedDailyPage } = await load('_cache'); let calls = 0, status = 200;
  t.mock.method(globalThis,'fetch',async url => { calls++; assert.equal(String(url),'/api/bluepulse/site/reports/daily/latest-page'); return Response.json(status===200?{ index:[], report:null }:{}, { status, headers: { 'Cache-Control':'max-age=60' } }); });
  assert.equal((await loadDailyPage('/daily?case=prefetch',false)).status,'ready'); await loadDailyPage('/daily?case=prefetch',false); assert.equal(calls,1);
  status=404; assert.equal((await loadDailyPage('/daily?case=prefetch',false,true)).status,'unavailable'); assert.equal(getCachedDailyPage('/daily?case=prefetch',false),null);
  const demo=await loadDailyPage('/daily?mock=1',true); assert.equal(demo.status,'ready'); assert.ok(demo.report); assert.equal(calls,2);
});
test('detail and navigation are one atomic page, use the earliest deadline and never substitute another day', async t => {
  const { loadDailyPage, getCachedDailyPage } = await load('_cache'); let fail=false;
  t.mock.method(globalThis,'fetch',async url => { const detail=String(url).endsWith('/2026-11-01')&&!String(url).includes('/navigation/'); return Response.json(fail && detail?{}:detail?report():{items:[]}, { status:fail&&detail?404:200, headers:{'Cache-Control':detail?'max-age=120':'no-store'} }); });
  const data=await loadDailyPage('/daily/2026-11-01?case=atomic',false); assert.equal(data.status,'ready'); assert.equal(data.expiresAt,0); assert.equal(getCachedDailyPage(data.key,false),null);
  fail=true; const gone=await loadDailyPage('/daily/2026-11-01?case=missing',false); assert.equal(gone.status,'not-found'); assert.equal(gone.report,null);
});
test('unsafe malformed month navigation is not reused as an empty month', async t => {
  const { loadDailyMonth } = await load('_cache'); t.mock.method(globalThis,'fetch',async () => Response.json({items:[{key:'2026-99-99',issueNumber:1}]}, {headers:{'Cache-Control':'max-age=60'}}));
  await assert.rejects(() => loadDailyMonth('2026-10',false));
});
test('an absent report service is never misreported as a missing edition when detail 404 arrives first', async t => {
  const { loadDailyPage } = await load('_cache');
  t.mock.method(globalThis,'fetch',async url => { if (String(url).includes('/navigation/')) await new Promise(resolve => setTimeout(resolve,15)); return Response.json({}, { status:404 }); });
  const data=await loadDailyPage('/daily/2026-11-01?case=service-404-race',false);
  assert.equal(data.status,'unavailable'); assert.equal(data.report,null);
});
