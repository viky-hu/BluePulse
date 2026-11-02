import assert from 'node:assert/strict';
import { test } from 'node:test';
const id = '4ed2a8d4-efb7-4ce6-8a43-4ee36f27d001';
const raw = () => ({ id, title: 'Article', source: {name:'Source'}, url:'https://example.org/report', importance_score:75, language: 'en', source_body: '<script>literal</script>\n\nNext', zh_body: null, topics: [], media: [] });
const reader = (body = { zh: '<h2>标题</h2><p>正文</p>', original: null, zhKind: 'translation', complete: false }) => ({ readingMode: 'full', body, bodyLanguage: 'zh', hasTranslation: true, outline: [], relatedStories: [], tags: [], indexable: true, markdownAvailable: true, group: null, story: null, x: null });
test('legacy body escapes markup, explicit null/malformed never resurrects it', async () => { const { normalizeArticle } = await import('../src/app/articles/_reader/data.ts'); assert.match(normalizeArticle(raw()).bodyHtml, /&lt;script&gt;/); for (const value of [null, {}, false])
    assert.throws(() => normalizeArticle({ ...raw(), reader: value })); assert.equal(normalizeArticle({ ...raw(), reader: reader(null) }).bodyHtml, null); });
test('summary restrictions and selected language are authoritative', async () => { const { normalizeArticle } = await import('../src/app/articles/_reader/data.ts'); let item = normalizeArticle({ ...raw(), reader: { ...reader(), readingMode: 'summary-only', reason: 'hidden', selected: true } }); assert.equal(item.bodyHtml, null); assert.equal(item.reason, null); assert.equal(item.selected, false); item = normalizeArticle({ ...raw(), reader: reader() }); assert.equal(item.complete, false); assert.equal(item.hasTranslation, true); assert.match(normalizeArticle({ ...raw(), reader: reader() }, 'original').bodyHtml, /<p>/); });
test('HTML whitelist removes active content and unsafe URLs; outline is actual body only', async () => { const { normalizeArticle } = await import('../src/app/articles/_reader/data.ts'); const item = normalizeArticle({ ...raw(), reader: reader({ zh: '<h2>Safe</h2><img src="javascript:alert(1)" onerror="x"><a href="jav&#97;script:x">bad</a><script>bad()</script><p style="color:red">ok</p>', original: null, zhKind: 'original', complete: true }) }); assert.doesNotMatch(item.bodyHtml, /javascript|onerror|script|style=/); assert.deepEqual(item.outline, [{ id: 'sec-1', text: 'Safe', level: 2 }]); });
test('route UUID validates exactly and original is distinct', async () => { const { articleRoute } = await import('../src/app/articles/_reader/data.ts'); assert.deepEqual(articleRoute('/articles/' + id + '/original'), { id, language: 'original' }); for (const path of ['/articles/nope', '/articles/' + id + '/bad', '/articles/' + id + '/original/extra'])
    assert.equal(articleRoute(path), null); });
test('HTTP 404 differs from unavailable and no-store stays out of cache', async (t) => { const { loadArticle, getCachedArticle, invalidateArticle } = await import('../src/app/articles/_reader/cache.ts'); const key = '/articles/' + id; t.after(() => invalidateArticle(key, false)); t.mock.method(globalThis, 'fetch', async () => new Response('', { status: 404 })); assert.equal((await loadArticle(key, false)).status, 'not-found'); assert.equal(getCachedArticle(key, false), null); globalThis.fetch = async () => Response.json(raw(), { headers: { 'cache-control': 'no-store' } }); assert.equal((await loadArticle(key, false)).status, 'ready'); assert.equal(getCachedArticle(key, false), null); globalThis.fetch = async () => new Response('', { status: 503 }); assert.equal((await loadArticle(key, false)).status, 'error'); });
test('preview consumes once and keeps mock isolated', async () => { const { rememberArticlePreview, takeArticlePreview } = await import('../src/app/articles/_reader/preview.ts'); rememberArticlePreview(raw(), true); assert.equal(takeArticlePreview(id, false), null); assert.equal(takeArticlePreview(id, true).id, id); assert.equal(takeArticlePreview(id, true), null); });
test('proxy exact tools, conditional downloads and upstream failure status', async (t) => {
    const { GET } = await import('../src/app/api/bluepulse/[...path]/route.ts');
    let calls = 0;
    t.mock.method(globalThis, 'fetch', async (url, init) => { calls++; assert.equal(new Headers(init.headers).get('if-none-match'), '"known"'); assert.equal(new Headers(init.headers).has('cookie'), false); return new Response(null, { status: 304, headers: { etag: '"known"', 'x-robots-tag': 'noindex', 'content-disposition': 'attachment; filename="article.md"' } }); });
    for (const suffix of ['markdown', 'poster.png', 'og.png']) {
        const response = await GET(new Request('http://local/api', { headers: { 'if-none-match': '"known"', cookie: 'admin=yes' } }), { params: Promise.resolve({ path: ['articles', id, suffix] }) });
        assert.equal(response.status, 304);
        assert.equal(response.headers.get('etag'), '"known"');
        assert.equal(response.headers.get('x-robots-tag'), 'noindex');
        assert.match(response.headers.get('content-disposition'), /attachment/);
    }
    for (const path of [['articles', id, 'admin'], ['articles', 'invalid', 'og.png'], ['site', 'stories', '../evil', 'followups'], ['site', 'stories', 'ok', 'followups', 'extra']])
        assert.equal((await GET(new Request('http://local/api'), { params: Promise.resolve({ path }) })).status, 404);
    assert.equal(calls, 3);
    globalThis.fetch = async () => new Response('', { status: 404 });
    assert.equal((await GET(new Request('http://local/api'), { params: Promise.resolve({ path: ['site', 'stories', 'valid-id', 'followups'] }) })).status, 404);
    globalThis.fetch = async () => { throw Error('offline'); };
    assert.equal((await GET(new Request('http://local/api'), { params: Promise.resolve({ path: ['articles', id, 'markdown'] }) })).status, 503);
});
test('freshness uses both responses, canonical query and force cannot overwrite newer result', async (t) => {
    const { loadArticle, getCachedArticle, invalidateArticle } = await import('../src/app/articles/_reader/cache.ts');
    const { articleKey } = await import('../src/app/articles/_reader/data.ts');
    assert.equal(articleKey('/articles/' + id + '?z=2&a=1#sec-2'), '/articles/' + id + '?a=1&z=2');
    const key = '/articles/' + id + '?cache-test=1';
    t.after(() => invalidateArticle(key, false));
    let release;
    let first = true;
    t.mock.method(globalThis, 'fetch', async (url) => { if (String(url).endsWith('/taxonomy'))
        return Response.json({ items: [] }, { headers: { 'cache-control': 'max-age=10' } }); if (first) {
        first = false;
        return new Promise(resolve => { release = resolve; });
    } return Response.json({ ...raw(), title: 'new' }, { headers: { 'cache-control': 'max-age=60' } }); });
    const old = loadArticle(key, false);
    await new Promise(resolve => setTimeout(resolve, 0));
    const fresh = await loadArticle(key, false, { force: true });
    assert.equal(fresh.item.article.title, 'new');
    assert.ok(fresh.expiresAt <= Date.now() + 10000);
    release(Response.json({ ...raw(), title: 'old' }, { headers: { 'cache-control': 'max-age=60' } }));
    await old;
    assert.equal(getCachedArticle(key, false).item.article.title, 'new');
    assert.equal(getCachedArticle(key, true), null);
    invalidateArticle(key, false);
    assert.equal(getCachedArticle(key, false), null);
});
test('malformed nested metadata and hostile post media fail as read errors', async () => {
    const { normalizeArticle } = await import('../src/app/articles/_reader/data.ts');
    for (const patch of [{ group: { factId: '../evil', reportCount: 1, additionalSourceCount: 0 } }, { story: { publicId: '../evil', title: 'x' } }, { relatedStories: [null] }, { x: { authorName: 'x', handle: 'x', avatarUrl: 'javascript:x', media: [], quoted: null } }])
        assert.throws(() => normalizeArticle({ ...raw(), reader: { ...reader(), ...patch } }));
});
test('core fields validate and missing legacy optional fields normalize safely',async()=>{
 const {normalizeArticle}=await import('../src/app/articles/_reader/data.ts');
 for(const patch of [{source:null},{source:{name:42}},{id:'bad'},{title:null},{language:null},{url:null},{importance_score:'75'}])assert.throws(()=>normalizeArticle({...raw(),...patch}));
 const item=normalizeArticle({...raw(),topics:null,entities:null,media:null,summary:undefined,author:3});
 assert.deepEqual(item.article.topics,[]);assert.deepEqual(item.article.entities,[]);assert.deepEqual(item.article.media,[]);assert.equal(item.article.summary,null);assert.equal(item.article.author,null);
});
test('server-selected body language wins on original route and required media URLs reject null',async()=>{
 const {normalizeArticle}=await import('../src/app/articles/_reader/data.ts');
 const item=normalizeArticle({...raw(),reader:reader()},'original');assert.equal(item.bodyLanguage,'zh');assert.match(item.bodyHtml,/<p>/);assert.doesNotMatch(item.bodyHtml,/literal/);
 const post={authorName:'x',handle:'x',avatarUrl:null,media:[],quoted:null};
 for(const x of [{...post,media:[{kind:'image',url:null,poster:null}]},{...post,quoted:{authorName:'x',handle:'x',text:'quote',translation:null,url:null}}])assert.throws(()=>normalizeArticle({...raw(),reader:{...reader(),x}}));
});
test('safe multimedia and deep headings survive but unsafe sources cannot execute',async()=>{
 const {cleanBody}=await import('../src/app/articles/_reader/text.ts');
 const {html}=cleanBody('<h5>Detail</h5><h6>Note</h6><picture><source srcset="https://example.org/a.webp 1x, https://example.org/b.webp 2x"><img src="https://example.org/a.png" srcset="https://example.org/a.png 1x"></picture><video src="https://example.org/v.mp4" poster="https://example.org/p.png" controls><source src="javascript:alert(1)"></video>');
 for(const tag of ['h5','h6','picture','source','video'])assert.match(html,new RegExp('<'+tag));assert.match(html,/srcset=/);assert.doesNotMatch(html,/javascript/);
});
test('taxonomy transport or JSON errors do not discard a successful article',async t=>{
 const {requestArticlePage}=await import('../src/app/articles/_reader/data.ts');
 for(const fail of [async()=>{throw Error('offline')},async()=>new Response('bad json')]){
 t.mock.method(globalThis,'fetch',async url=>String(url).endsWith('/taxonomy')?fail():Response.json(raw()));
 const result=await requestArticlePage('/articles/'+id,false);assert.equal(result.status,'ready');assert.equal(result.item.article.title,'Article');assert.equal(result.expiresAt,0);assert.deepEqual(result.taxonomy,[]);t.mock.restoreAll();}
});
test('serialization projects only public fields and never retains denied reader or legacy bodies',async()=>{
 const {normalizeArticle}=await import('../src/app/articles/_reader/data.ts');
 const denied='PRIVATE_DENIED_SENTINEL';
 const payload={...raw(),source_body:denied,zh_body:denied,secret:denied,source:{name:'Source',secret:denied},entities:[{slug:'agency',name:'Agency',entity_type:'agency',private:denied}],media:[{kind:'image',url:'https://example.org/a.png',private:denied}]};
 for(const r of [{...reader(),readingMode:'summary-only',body:{zh:denied,original:denied,zhKind:'translation',complete:true},reason:denied},{...reader(null),story:{publicId:'s1',title:'Public',secret:denied},group:{factId:'f1',reportCount:1,additionalSourceCount:0,secret:denied},x:{authorName:'Public',handle:'public',avatarUrl:null,media:[],quoted:null,secret:denied}}]){
 const normalized=normalizeArticle({...payload,reader:r});assert.doesNotMatch(JSON.stringify(normalized),new RegExp(denied));assert.equal(Object.hasOwn(normalized.article,'reader'),false);assert.equal(normalized.article.source_body,null);assert.equal(normalized.article.zh_body,null);
 }
 const legacy=normalizeArticle({...payload,source_body:'Public body',zh_body:null});assert.doesNotMatch(JSON.stringify(legacy),new RegExp(denied));
});
test('approved reader bodies can fall back in either direction without raw legacy text',async()=>{
 const {normalizeArticle}=await import('../src/app/articles/_reader/data.ts');
 for(const [declared,supplied] of [['zh','original'],['original','zh']]){
 const value=normalizeArticle({...raw(),source_body:'PRIVATE_DENIED_SENTINEL',reader:{...reader({zh:null,original:null,zhKind:'translation',complete:true}),bodyLanguage:declared,body:{zh:null,original:null,zhKind:'translation',complete:true,[supplied]:'<p>Approved body</p>'}}},'original');assert.equal(value.bodyLanguage,supplied);assert.match(value.bodyHtml,/Approved body/);assert.doesNotMatch(JSON.stringify(value),/PRIVATE_DENIED_SENTINEL/);
 }
});
