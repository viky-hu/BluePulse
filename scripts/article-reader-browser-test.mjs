// Production reader UI against deterministic local HTTP fixtures. No real collection or models.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { existsSync, readFileSync } from 'node:fs';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { registerHooks } from 'node:module';
import ts from 'typescript';
// The application fixtures use bundler resolution; resolve them without altering their source.
registerHooks({ resolve(specifier, context, next) {
  if (specifier.startsWith('.') && context.parentURL?.startsWith('file:')) {
    const url = new URL(specifier, context.parentURL);
    for (const suffix of ['', '.ts', '.tsx']) if (existsSync(fileURLToPath(url) + suffix) && /\.[cm]?[jt]sx?$/.test(fileURLToPath(url) + suffix)) return next(pathToFileURL(fileURLToPath(url) + suffix).href, context);
  }
  return next(specifier, context);
}, load(url, context, next) {
  if (/\.tsx?$/.test(url)) return { format: 'module', shortCircuit: true, source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText };
  return next(url, context);
} });
const { mockReaderArticle, mockReaderTaxonomy, READER_DEMO_ID: id, READER_SUMMARY_ID: summaryId } = await import('../src/app/articles/_reader/mock.ts');
const { makeAllMockItems } = await import('../src/app/all/_mock.ts');
const { MOCK_SOURCES } = await import('../src/app/_lib/home-mock.ts');
const feedItems=makeAllMockItems();feedItems[4]={...feedItems[4],...mockReaderArticle(id),reader:undefined};
const { chromium } = await import(pathToFileURL(process.env.PULSE_PLAYWRIGHT_MODULE ?? 'C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs').href);
const port = Number(process.env.PULSE_READER_PORT ?? 3180), origin = `http://127.0.0.1:${port}`, artifacts = 'test-results/article-reader';
let mode = 'ready', policy = 'public, max-age=60', age = null, posterFail = false, delay = 0, browser, serverLog = '';
const checks = [], observations = [], failures = [], errors = [], requests = [], screenshots = [];
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64');
const reset = () => { mode = 'ready'; policy = 'public, max-age=60'; age = null; delay = 0; posterFail = false; };
const api = createServer(async (req, res) => {
  requests.push({ url: req.url, mode, time: Date.now() });
  const url = new URL(req.url, 'http://localhost'); let status = 200, body;
  const match = /^\/api\/v1\/articles\/([^/]+)(?:\/(markdown|poster\.png|og\.png))?$/.exec(url.pathname);
  if (match?.[2]) {
    if (match[2] === 'markdown') { res.writeHead(200, { 'Content-Type': 'text/markdown', 'Content-Disposition': 'attachment; filename="fixture.md"' }); return res.end('# Deterministic reader export'); }
    res.writeHead(posterFail ? 503 : 200, { 'Content-Type': posterFail ? 'application/json' : 'image/png' }); return res.end(posterFail ? '{}' : png);
  }
  if (match) {
    if (delay) await new Promise(resolve => setTimeout(resolve, delay));
    status = mode === '404' ? 404 : mode === 'failure' ? 503 : 200;
    body = mockReaderArticle(match[1], url.searchParams.get('body_language') === 'original' ? 'original' : 'zh');
    if (!body) status = 404;
    if (body && mode === 'legacy') { delete body.reader; body.source_body = 'Literal <img src=x onerror="window.__unsafe=1">\n\nLegacy evidence'; body.zh_body = null; body.language = 'en'; }
    if (body && ['nullbody','sentinel-null','sentinel-summary'].includes(mode)) {body.source_body='READER_DENIED_LEGACY_ORIGINAL_SENTINEL';body.zh_body='READER_DENIED_LEGACY_ZH_SENTINEL';body.reader.body=null;if(mode==='sentinel-summary'){body.reader.readingMode='summary-only';body.reader.body={zh:'<p>READER_DENIED_RICH_ZH_SENTINEL</p>',original:'<p>READER_DENIED_RICH_ORIGINAL_SENTINEL</p>',zhKind:'translation',complete:true};}}
    if (body && mode === 'partial') body.reader.body.complete = false;
    if (body && mode === 'fewheadings') body.reader.body.zh = '<h2>Only one heading</h2><p>Short body</p>';
    if (body && ['x','xvideo'].includes(mode)) { body.reader.channel = 'x'; body.reader.x = { authorName: 'Fixture analyst', handle: 'fixture', avatarUrl: null, media: Array.from({length: 9}, (_, i) => ({ kind: mode === 'xvideo' && i === 0 ? 'video' : 'image', url: `/reader-fixture-${i}.svg`, fullUrl: `/reader-fixture-${i}.svg`, poster: null })), quoted: { text: 'Quoted original evidence', translation: '引用译文证据', authorName: 'Quoted analyst', handle: 'quoted', url: 'https://example.com/quoted' } }; }
  } else if (url.pathname === '/api/v1/taxonomy') body = { items: mockReaderTaxonomy };
  else if (/\/groups\/[^/]+\/reports$/.test(url.pathname)) body = { items: [] };
  else if (/\/followups$/.test(url.pathname)) body = { items: [] };
  else if (url.pathname === '/api/v1/articles') body = { items: feedItems, limit:40, next_cursor:null };
  else if(url.pathname==='/api/v1/sources')body=MOCK_SOURCES;
  else { status = 404; body = {}; }
  const headers = { 'Content-Type': 'application/json', 'Cache-Control': policy }; if (age !== null) headers.Age = String(age);
  res.writeHead(status, headers); res.end(JSON.stringify(body ?? {}));
});
await mkdir(artifacts, { recursive: true });
await new Promise(resolve => api.listen(port + 1, '127.0.0.1', resolve));
const server = spawn(process.execPath, ['node_modules/next/dist/bin/next', 'start', '--hostname', '127.0.0.1', '--port', String(port)], { cwd: process.cwd(), env: { ...process.env, BLUEPULSE_API_URL: `http://127.0.0.1:${port + 1}` }, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
server.stdout.on('data', data => { serverLog += data; }); server.stderr.on('data', data => { serverLog += data; });
const paper = page => page.locator('[data-p0-scroller]');
async function ready(page) { await page.waitForFunction(() => document.querySelector('[data-entry="stable"] [data-phase="idle"]') && document.querySelector('[data-p0-scroller]')?.getAttribute('aria-busy') === 'false' && document.querySelector('[data-article-status]')?.getAttribute('data-article-status') !== 'loading'); }
async function goto(page, path = `/articles/${id}`) { await page.goto(origin + path); await ready(page); }
async function test(page, name, work) { try { await work(); checks.push(name); console.log('PASS ' + name); } catch (error) { failures.push({ name, error: error.stack, url: page.url() }); console.log('FAIL ' + name + ': ' + error.message); await page.screenshot({ path: `${artifacts}/failure-${failures.length}.png` }).catch(() => {}); } }
async function shot(page, name) { const path = `${artifacts}/${name}.png`; await page.screenshot({ path }); screenshots.push(path); }
async function more(page) { const button = page.getByRole('button', { name: '更多操作', exact: true }); for (const entry of await button.all()) if (await entry.isVisible()) { await entry.click(); return; } throw Error('No visible more action'); }
try {
  for (let i = 0; i < 100; i++) { try { const response = await fetch(`${origin}/articles/${id}`); if (response.ok) break; } catch {} if (i === 99) throw Error(serverLog); await new Promise(resolve => setTimeout(resolve, 100)); }
  browser = await chromium.launch({ headless: true });
  for (const spec of [{name:'desktop', viewport:{width:1440,height:900}}, {name:'mobile',viewport:{width:390,height:844}}, {name:'reduced',viewport:{width:1440,height:900},reducedMotion:'reduce'}]) {
    reset(); const context = await browser.newContext({ viewport: spec.viewport, reducedMotion: spec.reducedMotion ?? 'no-preference', permissions: ['clipboard-read', 'clipboard-write'] });
    await context.addInitScript(() => localStorage.setItem('blue-pulse-entry-complete-v1', '1'));
    await context.route('**/reader-fixture-*.svg', route => route.fulfill({ contentType:'image/svg+xml', body:'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="500"><rect width="800" height="500" fill="#1b5772"/></svg>' }));
    const page = await context.newPage(); page.on('pageerror', error => errors.push(`${spec.name}: ${error.message}`)); await goto(page); await shot(page,spec.name);
    await test(page, `${spec.name}: real service contract, body and contained paper`, async () => { assert.equal(await page.locator('[data-article-status]').getAttribute('data-article-status'), 'ready'); assert.ok(await page.getByRole('heading',{level:1}).isVisible()); assert.equal(await paper(page).evaluate(el=>el.scrollWidth<=el.clientWidth+1),true); assert.ok(await page.locator('h2[id^="sec-"]').count() >= 3); assert.ok(await page.getByText('演示：关注公开证据、应用边界与人工复核。',{exact:true}).first().count()); });
    await test(page, `${spec.name}: directory targets p0, hash replacement and progress`, async () => { const before = await page.evaluate(()=>history.length); const link=page.locator('nav[aria-label="本文目录"] a').last(); if(await link.isVisible()) await link.click(); else { await page.getByRole('button',{name:'目录',exact:true}).click(); await page.getByRole('dialog').locator('a[href^="#sec-"]').last().click(); } await page.waitForTimeout(700); assert.match(new URL(page.url()).hash,/^#sec-/); assert.ok(await paper(page).evaluate(el=>el.scrollTop)>100); assert.equal(await page.evaluate(()=>window.scrollY),0); assert.equal(await page.evaluate(()=>history.length),before); assert.notEqual(await page.locator('[data-reading-progress]').evaluate(el=>el.style.transform),'scaleX(0)'); await shot(page,`${spec.name}-body`); });
    await test(page, `${spec.name}: code copy and lazy highlight`, async () => { const copy=page.getByRole('button',{name:'复制代码'}); await copy.scrollIntoViewIfNeeded(); await copy.click(); assert.match(await page.evaluate(()=>navigator.clipboard.readText()),/reviewRequired/); await page.locator('code.hljs').waitFor(); assert.equal(await paper(page).evaluate(el=>el.scrollWidth<=el.clientWidth+1),true); });
    await test(page, `${spec.name}: image keyboard zoom and Escape`, async () => { const image=page.getByRole('button',{name:'查看大图：青朗先锋标识演示图'}); await image.scrollIntoViewIfNeeded(); await image.focus(); await page.keyboard.press('Enter'); await page.getByRole('dialog').waitFor(); await page.keyboard.press('Escape'); await page.getByRole('dialog').waitFor({state:'hidden'}); });
    if(spec.name==='mobile') {
      await test(page,'mobile: toolbar down/up/end, sticky title and outline focus/Escape',async()=>{
        await paper(page).evaluate(el=>{el.scrollTop=0}); await page.waitForTimeout(100); await paper(page).evaluate(el=>{el.scrollTop=400}); await page.waitForTimeout(100); assert.equal(await page.locator('nav[aria-label="阅读工具"]').getAttribute('data-hidden'),'true');
        await paper(page).evaluate(el=>{el.scrollTop=300}); await page.waitForTimeout(100); assert.equal(await page.locator('nav[aria-label="阅读工具"]').getAttribute('data-hidden'),'false');
        await paper(page).evaluate(el=>{el.scrollTop=el.scrollHeight}); await page.waitForTimeout(100); assert.equal(await page.locator('nav[aria-label="阅读工具"]').getAttribute('data-hidden'),'false');
        assert.equal(await page.locator('[data-reader-bar] span[data-shown]').getAttribute('data-shown'),'true');
        const trigger=page.getByRole('button',{name:'目录',exact:true});await trigger.click(); const dialog=page.getByRole('dialog');await dialog.waitFor();assert.ok(await dialog.evaluate(el=>el.contains(document.activeElement)));await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'}); assert.equal(await trigger.evaluate(el=>el===document.activeElement),true);
      });
    }
    await test(page, `${spec.name}: summary-only removes reading extras`, async () => { await goto(page,`/articles/${summaryId}`); assert.ok(await page.getByText('应来源方要求，这里只提供摘要与原文入口。完整内容请阅读原文。').isVisible()); assert.equal(await page.locator('[data-reading-progress],h2[id^="sec-"],.code-block').count(),0); assert.equal(await page.getByText('推荐理由',{exact:true}).count(),0); });
    await context.close();
  }
  reset(); const context=await browser.newContext({viewport:{width:1920,height:1080},permissions:['clipboard-read','clipboard-write']}); await context.addInitScript(()=>{localStorage.setItem('blue-pulse-entry-complete-v1','1');localStorage.setItem('blue-pulse-entry-complete-v1:mock','1');}); const page=await context.newPage(); await goto(page); await shot(page,'three-column');
  await test(page,'wide: both original source rails visible',async()=>{ const rails=page.locator('[data-reading-page] > div > aside'); assert.equal(await rails.count(),2); for(const rail of await rails.all()) assert.ok(await rail.isVisible()); });
  await test(page,'original language uses exact route and active pill',async()=>{ const link=page.locator('a[href$="/original"]').first(); await link.click(); await ready(page); assert.equal(new URL(page.url()).pathname,`/articles/${id}/original`); await page.getByRole('heading',{name:'Public evaluation',exact:true}).waitFor(); assert.equal(await page.locator('[aria-label="正文语言"] a[aria-current="page"]').getAttribute('data-filter'),'original'); assert.equal(await page.locator('nav[aria-label="本文目录"]').count(),0); });
  for(const branch of ['legacy','nullbody','partial','fewheadings','failure']) { mode=branch; await test(page,`${branch}: authoritative rendering branch`,async()=>{ await goto(page); if(branch==='failure'){assert.equal(await page.locator('[data-article-status]').getAttribute('data-article-status'),'error'); reset(); await page.getByRole('button',{name:'重试',exact:true}).click(); await ready(page); assert.equal(await page.locator('[data-article-status]').getAttribute('data-article-status'),'ready');} if(branch==='legacy'){assert.ok(await page.getByRole('article').getByText(/Literal <img src=x/).isVisible());assert.equal(await page.evaluate(()=>window.__unsafe),undefined);} if(branch==='nullbody')assert.equal(await page.locator('h2[id^="sec-"],.code-block').count(),0); if(branch==='partial')assert.ok(await page.getByRole('article').getByText('译文尚不完整，完整内容请切换到原文。').isVisible()); if(branch==='fewheadings')assert.equal(await page.locator('nav[aria-label="本文目录"]').count(),0); }); }
  mode='404'; await test(page,'direct missing article: noindex and gone UI',async()=>{const response=await page.goto(`${origin}/articles/${id}`); await page.getByText('这里没有内容',{exact:true}).waitFor(); const robots=await page.locator('meta[name="robots"]').evaluateAll(els=>els.map(el=>el.content));assert.ok(robots.some(value=>value.includes('noindex'))); observations.push(`404 response observed: ${response.status()}`);});
  for(const branch of ['sentinel-null','sentinel-summary']){mode=branch;await test(page,`${branch}: SSR HTML and Flight omit denied raw bodies`,async()=>{const response=await fetch(`${origin}/articles/${id}`);const html=await response.text();assert.equal(/READER_DENIED_[A-Z_]+_SENTINEL/.test(html),false);});}
  reset(); await goto(page);
  await test(page,'more menu copy and markdown download contract',async()=>{await more(page);await page.getByRole('menuitem',{name:'复制链接',exact:true}).click();assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),`${origin}/articles/${id}`);await more(page);const download=page.waitForEvent('download');await page.getByRole('menuitem',{name:'导出 Markdown'}).click();assert.ok((await download).suggestedFilename().endsWith('.md'));});
  await test(page,'poster success uses real PNG and download',async()=>{await more(page);await page.getByRole('menuitem',{name:'生成分享海报'}).click(); const dialog=page.getByRole('dialog'); await dialog.locator('img[data-loaded="true"]').waitFor();assert.equal(await dialog.getByRole('link',{name:'保存图片'}).getAttribute('aria-disabled'),'false');await page.keyboard.press('Escape');});
  posterFail=true;await goto(page);await test(page,'poster service failure is shown without fabricated image',async()=>{await more(page);await page.getByRole('menuitem',{name:'生成分享海报'}).click();await page.getByText('海报生成失败，请稍后再试。').waitFor();assert.equal(await page.getByRole('dialog').getByRole('link',{name:'保存图片'}).getAttribute('aria-disabled'),'true');await page.keyboard.press('Escape');});
  for(const branch of ['x','xvideo']) { mode=branch; await test(page,`${branch}: nine media tiles, quoted original and source-only video`,async()=>{await goto(page);assert.equal(await page.locator('[data-count="9"] img').count(),9);assert.ok(await page.getByText('引用译文证据',{exact:true}).isVisible());if(branch==='x'){await page.locator('figure details summary').click();assert.ok(await page.getByText('Quoted original evidence',{exact:true}).isVisible());}else{const video=page.getByRole('link',{name:'打开原推播放视频'});assert.equal(await video.getAttribute('target'),'_blank');assert.match(await video.getAttribute('rel'),/noopener/);} }); }
  reset();
  await test(page,'filtered feed -> article -> original -> back restores source route and p0 scroll',async()=>{
    await page.goto(`${origin}/all?tag=${encodeURIComponent('人工复核')}&sort=importance`);const link=page.locator(`a[href="/articles/${id}"]`).first();await link.waitFor();await link.scrollIntoViewIfNeeded();await page.waitForTimeout(100);const top=await paper(page).evaluate(el=>el.scrollTop);await link.click();await page.waitForURL(`${origin}/articles/${id}`);await page.getByRole('heading',{name:'公开试点与应用边界',exact:true}).waitFor();await page.locator('a[href$="/original"]').first().click();await page.getByRole('heading',{name:'Public evaluation',exact:true}).waitFor();await page.goBack();await page.waitForURL(/\/all\?/);assert.equal(new URL(page.url()).searchParams.get('tag'),'人工复核');assert.equal(new URL(page.url()).searchParams.get('sort'),'importance');await page.waitForTimeout(200);assert.ok(Math.abs(await paper(page).evaluate(el=>el.scrollTop)-top)<4);
  });
  for(const cache of [{name:'no-store',policy:'no-store',age:null},{name:'expired-age',policy:'public, max-age=1',age:1}]){
    reset();policy=cache.policy;age=cache.age;
    await test(page,`${cache.name}: return revalidates article`,async()=>{await goto(page);const count=()=>requests.filter(row=>row.url.startsWith(`/api/v1/articles/${id}?`)).length;const before=count();await page.locator('aside a[href="/all"]').first().click();await page.waitForURL(/\/all$/);await page.goBack();await page.waitForURL(`${origin}/articles/${id}`);await ready(page);assert.ok(count()>before);});
  }
  reset();await goto(page);await test(page,'slow language request cannot overwrite a route left behind',async()=>{delay=900;await page.locator('a[href$="/original"]').first().click();await page.waitForURL(`${origin}/articles/${id}/original`);await page.locator('aside a[href="/all"]').first().click();await page.waitForURL(/\/all$/);await page.waitForTimeout(1200);assert.equal(new URL(page.url()).pathname,'/all');assert.equal(await page.locator('[data-reading-page]').count(),0);});
  reset(); await goto(page,`/articles/${id}?mock=1`); await test(page,'explicit mock: poster fails honestly and export does not download',async()=>{await more(page);await page.getByRole('menuitem',{name:'生成分享海报'}).click();await page.getByText('海报生成失败，请稍后再试。').waitFor();assert.equal(await page.getByRole('dialog').locator('a[download]').getAttribute('href'),null);await page.keyboard.press('Escape');});
  reset();const compact=await browser.newContext({viewport:{width:820,height:900}});await compact.addInitScript(()=>localStorage.setItem('blue-pulse-entry-complete-v1','1'));const compactPage=await compact.newPage();
  await test(compactPage,'820px: compact p0 shows card preview during slow article load',async()=>{await compactPage.goto(`${origin}/all?tag=${encodeURIComponent('人工复核')}`);const link=compactPage.locator(`a[href="/articles/${id}"]`).first();await link.waitFor();await link.scrollIntoViewIfNeeded();delay=1200;await link.click();await compactPage.locator('[data-article-status="preview"]').waitFor({timeout:10000});assert.equal(await paper(compactPage).evaluate(el=>el.scrollWidth<=el.clientWidth+1),true);await shot(compactPage,'compact-preview-820');await compactPage.locator('[data-article-status="ready"]').waitFor();});await compact.close();
  await context.close();
} catch(error) { failures.push({name:'harness',error:error.stack}); console.error(error); }
finally { await browser?.close(); server.kill(); await new Promise(resolve=>api.close(resolve)); await writeFile(`${artifacts}/results.json`,JSON.stringify({checks,observations,failures,errors,screenshots,requests},null,2)); await writeFile(`${artifacts}/server.log`,serverLog); }
console.log(JSON.stringify({passed:checks.length,failures:failures.length,errors})); if(failures.length||errors.length)process.exitCode=1;
