// Real production Next UI and exact HTTP proxy, using deterministic local report fixtures only.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { MOCK_REPORT, MOCK_REPORT_INDEX, mockDailyNavigation } from '../src/app/daily/_mock.ts';
const { chromium } = await import(pathToFileURL(process.env.PULSE_PLAYWRIGHT_MODULE ?? 'C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs').href);
const port = Number(process.env.PULSE_DAILY_PORT ?? 3230), origin = `http://127.0.0.1:${port}`, artifacts = 'test-results/daily-report';
let payload = structuredClone(MOCK_REPORT), mode = 'ready', policy = 'public, max-age=60', age = null, delay = 0;
const requests = [], checks = [], errors = [], layouts = [];
const check = name => { checks.push(name); console.log(`PASS ${name}`); };
const reset = () => { payload = structuredClone(MOCK_REPORT); mode = 'ready'; policy = 'public, max-age=60'; age = null; delay = 0; };
const api = createServer(async (req,res) => {
  requests.push(req.url); const path = new URL(req.url,'http://localhost').pathname;
  let status = 200, body;
  if (path === '/api/v1/site/reports/daily/latest-page') body = { index: mockDailyNavigation(payload.key), report: mode === 'empty' ? null : payload };
  else if (path === '/api/v1/site/reports/daily') body = { kind: 'daily', items: MOCK_REPORT_INDEX };
  else if (/\/navigation\/\d{4}-\d{2}-\d{2}$/.test(path)) body = { items: mockDailyNavigation(path.slice(-10)) };
  else if (/\/months\/\d{4}-\d{2}$/.test(path)) body = { items: MOCK_REPORT_INDEX.filter(e => e.key.startsWith(path.slice(-7))) };
  else if (/^\/api\/v1\/site\/reports\/daily\/\d{4}-\d{2}-\d{2}$/.test(path)) {
    const key = path.slice(-10), at = MOCK_REPORT_INDEX.findIndex(e => e.key === key);
    if (at < 0) { status = 404; body = {}; } else body = { ...payload, key, issueNumber: MOCK_REPORT_INDEX[at].issueNumber, generatedAt: `${key}T00:00:00Z`, prev: MOCK_REPORT_INDEX[at+1]?.key ?? null, next: MOCK_REPORT_INDEX[at-1]?.key ?? null };
  } else { status = 404; body = {}; }
  if (mode === 'unavailable') status = 404; if (mode === 'failure') status = 503;
  if (mode === 'malformed') body = { report:null };
  if (delay) await new Promise(resolve => setTimeout(resolve,delay));
  const headers = { 'Content-Type':'application/json', 'Cache-Control': policy }; if (age !== null) headers.Age = String(age);
  res.writeHead(status,headers); res.end(mode === 'bad-json' ? '{invalid' : JSON.stringify(body));
});
await new Promise(resolve => api.listen(port+1,'127.0.0.1',resolve));
const server = spawn(process.execPath,['node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port',String(port)],{cwd:process.cwd(),env:{...process.env,BLUEPULSE_API_URL:`http://127.0.0.1:${port+1}`},windowsHide:true,stdio:['ignore','pipe','pipe']});
let log = '', browser; server.stdout.on('data',d=>{log+=d;});server.stderr.on('data',d=>{log+=d;});
const paper = page => page.locator('[data-p0-scroller]');
const count = path => requests.filter(url=>url===`/api/v1/site/reports/daily${path}`).length;
async function ready(page,path='/daily') { await page.waitForFunction(path => location.pathname===path && document.querySelector('[data-entry="stable"] [data-phase="idle"]') && document.querySelector('[data-p0-scroller]')?.getAttribute('aria-busy')==='false' && (document.querySelector('[data-daily-status]')?.getAttribute('data-daily-status')!=='loading'),path); }
async function goto(page,path='/daily') { await page.goto(`${origin}${path}`);await ready(page,path.split(/[?#]/)[0]); }
async function menu(page,href) { const button=page.getByRole('button',{name:'打开菜单',exact:true});if(await button.isVisible())await button.click();await page.locator(`[data-home-sidebar] a[href="${href}"]`).click();await ready(page,href); }
async function settledCanvas(page) { await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(1050); }
async function sampleIssueHandoff(page, path) {
  const samples = page.evaluate(async path => {
    const frames = [];
    const seed = `daily-${path.slice(-10)}-date`;
    const deadline = performance.now() + 10000;
    let started = null;
    while (performance.now() < deadline) {
      await new Promise(requestAnimationFrame);
      const host = document.querySelector(`[data-halftone-seed="${seed}"]`);
      const canvas = host?.querySelector('[data-halftone-canvas]');
      const text = host?.querySelector('[data-halftone-text]');
      if (!host || !canvas || !text) continue;
      started ??= performance.now();
      if (performance.now() - started >= 1250) break;
      let darkPixels = 0, opaquePixels = 0, minRgb = 765;
      if (canvas.width && canvas.height) {
        const ctx = canvas.getContext('2d');
        const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
        for (let i = 0; i < pixels.length; i += 4) {
          if (pixels[i + 3] > 0) opaquePixels++;
          minRgb = Math.min(minRgb, pixels[i] + pixels[i + 1] + pixels[i + 2]);
          if (pixels[i + 3] > 32 && pixels[i] + pixels[i + 1] + pixels[i + 2] < 390) darkPixels++;
        }
      }
      frames.push({ elapsed: Math.round(performance.now() - started), phase: host.dataset.halftonePhase, ready: host.dataset.halftoneReady === 'true', textOpacity: Number(getComputedStyle(text).opacity), canvasOpacity: Number(getComputedStyle(canvas).opacity), size: [canvas.width, canvas.height], darkPixels, opaquePixels, minRgb });
    }
    return { frames, finalPath: location.pathname, lastSeed: document.querySelector('[data-halftone-seed]')?.dataset.halftoneSeed ?? null };
  }, path);
  await page.locator(`a[href="${path}"]:visible`).first().click();
  return samples;
}
try {
  await mkdir(artifacts,{recursive:true});for(let i=0;i<100;i++){try{if((await fetch(`${origin}/daily`)).ok)break;}catch{}if(i===99)throw Error(log);await new Promise(resolve=>setTimeout(resolve,100));}
  browser=await chromium.launch({headless:true});
  for(const spec of [{name:'desktop',viewport:{width:1440,height:900}},{name:'narrow-desktop',viewport:{width:1180,height:820}},{name:'wide',viewport:{width:1920,height:1080}},{name:'mobile',viewport:{width:390,height:844}},{name:'reduced',viewport:{width:1440,height:900},reducedMotion:'reduce'},{name:'font-delay',viewport:{width:1440,height:900},fontDelay:500}]) {
    if(process.env.PULSE_DAILY_CASE && process.env.PULSE_DAILY_CASE!==spec.name)continue;
    reset();const context=await browser.newContext({viewport:spec.viewport,reducedMotion:spec.reducedMotion??'no-preference'});await context.addInitScript(delay=>{localStorage.setItem('blue-pulse-entry-complete-v1','1');localStorage.setItem('blue-pulse-entry-complete-v1:mock','1');if(delay){const ready=document.fonts.ready;Object.defineProperty(document.fonts,'ready',{configurable:true,get:()=>new Promise(resolve=>setTimeout(()=>ready.then(resolve),delay))});}},spec.fontDelay??0);
    const page=await context.newPage();page.on('pageerror',error=>errors.push(`${spec.name}: ${error.message}`));
    await context.route('**/daily-fixture-*.svg',route=>route.fulfill({status:route.request().url().includes('missing')?404:200,contentType:'image/svg+xml',body:route.request().url().includes('missing')?'invalid image':'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450"><rect width="800" height="450" fill="#a4d7c7"/></svg>'}));
    await goto(page);await settledCanvas(page);
    assert.equal(await page.locator('[data-daily-status]').getAttribute('data-daily-status'),'ready');
    assert.equal(await page.getByRole('heading',{level:1,name:/^AI日报/}).count(),1);
    assert.equal(await page.locator('section[id^="s-"] > header h2').count(),8);
    for(const text of ['头条','今日看点','本期版面','一手','跟进','另有 2 家信源报道','（本期完）'])assert.ok(await page.getByText(text,{exact:true}).count(),text);
    assert.equal(await paper(page).evaluate(el=>el.scrollWidth<=el.clientWidth+1),true);
    if(spec.name==='mobile') assert.ok((await page.locator('#report-start > svg').boundingBox()).height >= 43, 'phone nameplate must keep its readable original 44px scene');
    const isArchiveVisible=await page.getByRole('navigation',{name:'日报历史',exact:true}).isVisible();assert.equal(isArchiveVisible,spec.name!=='mobile');
    const switcher=page.getByRole('navigation',{name:'切换日报、周报、月报'}).filter({visible:true});
    assert.equal(await switcher.getByRole('tab',{name:'周报',exact:true}).isDisabled(),true);assert.equal(await switcher.getByRole('tab',{name:'月报',exact:true}).isDisabled(),true);
    await page.screenshot({path:`${artifacts}/${spec.name}.png`});
    check(`${spec.name}: complete paper, metadata, seven pages/flash, original switch and no overflow`);
    if(['desktop','mobile','reduced','font-delay'].includes(spec.name)) {
      const capture=await sampleIssueHandoff(page,'/daily/2026-10-31'),frames=capture.frames;
      await writeFile(`${artifacts}/${spec.name}-handoff.json`,JSON.stringify(capture,null,2));
      assert.ok(frames.length>20,`record the new issue handoff across multiple display frames; ${JSON.stringify(capture)}`);
      const visibleText=frames.find(frame=>frame.textOpacity>0.01);
      assert.equal(visibleText,undefined,`the DOM numeral must be hidden from the first new-issue frame; frame=${JSON.stringify(visibleText)}`);
      const invisibleCanvas=frames.find(frame=>!frame.ready||frame.canvasOpacity<0.99||frame.darkPixels===0);
      assert.equal(invisibleCanvas,undefined,`the painted Canvas must be visible from the first new-issue frame; frame=${JSON.stringify(invisibleCanvas)}`);
      if(spec.name==='reduced') assert.ok(frames.every(frame=>frame.phase==='complete'),'reduced motion must show the complete static halftone from its first frame');
      else {
        assert.equal(frames[0].phase,'revealing','the first visible dot frame must preserve the entrance animation');
        const complete=frames.findIndex(frame=>frame.phase==='complete');
        assert.ok(complete>0,'the Canvas must reveal and then complete');
        assert.ok(frames.slice(complete).every(frame=>frame.phase==='complete'),'the completed reveal must not restart');
      }
      await ready(page,'/daily/2026-10-31');await settledCanvas(page);
      assert.equal(await page.locator('[data-halftone-seed="daily-2026-10-31-date"]').getAttribute('data-halftone-phase'),'complete');
      check('issue change hands off directly to a painted halftone without a text-only or blank frame');
      if(spec.name==='reduced') {
        const first=await page.locator('[data-halftone-canvas]').evaluate(canvas=>{const ctx=canvas.getContext('2d');return Array.from(ctx.getImageData(0,0,canvas.width,canvas.height).data).reduce((sum,value,index)=>index%4===3?sum+value:sum,0);});
        await page.waitForTimeout(80);
        const second=await page.locator('[data-halftone-canvas]').evaluate(canvas=>{const ctx=canvas.getContext('2d');return Array.from(ctx.getImageData(0,0,canvas.width,canvas.height).data).reduce((sum,value,index)=>index%4===3?sum+value:sum,0);});
        assert.equal(first,second,'reduced motion must hand off to a complete static Canvas');
        check('reduced motion paints the full static halftone without an entrance loop');
      }
      if(spec.name==='desktop') {
        await page.locator('a[href="/daily/2026-10-30"]:visible').first().click();
        await page.waitForFunction(()=>location.pathname==='/daily/2026-10-30');
        await page.locator('a[href="/daily/2026-10-29"]:visible').first().click();
        await ready(page,'/daily/2026-10-29');
        await page.waitForFunction(()=>{const host=document.querySelector('[data-halftone-seed="daily-2026-10-29-date"]');return host?.dataset.halftoneReady==='true';});
        assert.equal(await page.locator('[data-halftone-seed^="daily-"]').getAttribute('data-halftone-seed'),'daily-2026-10-29-date');
        await settledCanvas(page);
        check('rapid consecutive issue changes leave only the final issue drawing');
      }
    }
    if(spec.name!=='mobile') {
      const september=page.getByRole('navigation',{name:'日报历史'}).locator('details').filter({hasText:'2026 年 9 月'});const before=count('/months/2026-09');
      await september.locator('summary').click();await september.getByText(MOCK_REPORT_INDEX.at(-1).title,{exact:true}).waitFor();assert.equal(count('/months/2026-09'),before+1);
      const side=page.getByRole('navigation',{name:'日报历史'}).locator('..');const size=await side.boundingBox(), frame=await page.locator('[data-p0-content]').boundingBox(), content=await page.locator('[data-daily-status] article').first().boundingBox();
      assert.ok(size.width>=175&&size.width<=241);assert.ok(Math.abs(size.x-frame.x)<2,'desktop archive must use the existing blank left gutter');assert.equal(await page.locator('[data-phone-bar]').isVisible(),false);
      const rightGutter=frame.x+frame.width-content.x-content.width;assert.ok(rightGutter>=15&&rightGutter<=33,'report must fill the available right paper with only its own gutter');
      await paper(page).evaluate(el=>{el.scrollTop=450;});await page.waitForTimeout(40);assert.ok(Math.abs((await side.boundingBox()).y-(await paper(page).boundingBox()).y)<2,'archive sticks to p0, not the window');
      const beforeHistory=await page.evaluate(()=>history.length);await page.getByRole('navigation',{name:'本期版面',exact:true}).getByRole('link',{name:/低空警务应用/}).click();assert.equal(await page.evaluate(()=>history.length),beforeHistory);assert.equal(await page.evaluate(()=>location.hash),'#s-7');
      await page.waitForFunction(()=>{const el=document.querySelector('[data-p0-scroller]'),offset=document.querySelector('#s-7').getBoundingClientRect().top-el.getBoundingClientRect().top;return Math.abs(offset-24)<3||(offset>=24&&offset<el.clientHeight&&el.scrollHeight-el.clientHeight-el.scrollTop<2);});
      layouts.push({profile:spec.name,paperWidth:frame.width,archiveWidth:size.width,reportWidth:content.width,rightGutter,headlineSize:await page.locator('section[aria-label="头版"] h2').evaluate(el=>getComputedStyle(el).fontSize)});
      check(`${spec.name}: compact left archive fills the paper, sticks to p0, anchors and month fetch`);
    } else {
      await paper(page).evaluate(el=>{el.scrollTop=450;});const bar=page.locator('[data-phone-bar]');assert.ok(Math.abs((await bar.boundingBox()).y-(await paper(page).boundingBox()).y)<2);
      const before=await page.evaluate(()=>history.length);await page.getByRole('button',{name:'本期目录',exact:true}).click();const sheet=page.getByRole('dialog',{name:'本期目录'});await sheet.waitFor();
      assert.equal(await sheet.evaluate(el=>el.closest('[class*="sheetOverlay"]').parentElement===document.body),true);
      await sheet.getByRole('link',{name:/低空警务应用/}).click();await sheet.waitFor({state:'hidden'});await page.waitForTimeout(spec.reducedMotion?40:700);
      assert.equal(await page.evaluate(()=>history.length),before);assert.equal(await page.evaluate(()=>location.hash),'#s-7');assert.ok(await paper(page).evaluate(el=>el.scrollTop>600));
      check(`${spec.name}: sticky p0 bar, portal outline, anchor replaces history and scrolls paper`);
    }
    await goto(page,'/daily/archive');assert.ok(await page.getByRole('heading',{name:'日报合订本',exact:true}).isVisible());assert.ok(await page.getByText('401',{exact:true}).count());
    await page.locator('a[href="/daily/2026-10-31"]').last().click();await ready(page,'/daily/2026-10-31');assert.ok(await page.getByText('第 400 期',{exact:true}).isVisible());
    check(`${spec.name}: complete archive, date deep link and server issue number`);
    await goto(page,'/daily?mock=1');assert.equal(await page.getByRole('heading',{level:1,name:/^AI日报/}).count(),1);
    await context.close();
  }
  if(!process.env.PULSE_DAILY_CASE || process.env.PULSE_DAILY_CASE==='desktop') {
    const fallbackContext=await browser.newContext({viewport:{width:1440,height:900}});await fallbackContext.addInitScript(()=>{localStorage.setItem('blue-pulse-entry-complete-v1','1');localStorage.setItem('blue-pulse-entry-complete-v1:mock','1');const getContext=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(...args){return this.hasAttribute('data-halftone-canvas')?null:getContext.apply(this,args);};});
    const fallbackPage=await fallbackContext.newPage();await goto(fallbackPage);const fallback= fallbackPage.locator('[data-halftone-seed="daily-2026-11-01-date"]');
    assert.equal(await fallback.getAttribute('data-halftone-ready'),'false');assert.ok(Number(await fallback.locator('[data-halftone-text]').evaluate(el=>getComputedStyle(el).opacity))>0.95);assert.equal(await fallback.locator('[data-halftone-canvas]').evaluate(el=>getComputedStyle(el).opacity), '0');
    check('Canvas unavailable keeps the accessible DOM numeral visible');await fallbackContext.close();
    const context=await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});await context.addInitScript(()=>localStorage.setItem('blue-pulse-entry-complete-v1','1'));
    await context.route('**/daily-fixture-*.svg',route=>route.fulfill({status:route.request().url().includes('missing')?404:200,contentType:'image/svg+xml',body:route.request().url().includes('missing')?'invalid image':'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450"><rect width="800" height="450" fill="#a4d7c7"/></svg>'}));
    const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
    for(const [state,expected] of [['unavailable','unavailable'],['failure','error'],['malformed','error'],['bad-json','error'],['empty','ready']]) { mode=state;await goto(page);assert.equal(await page.locator('[data-daily-status]').getAttribute('data-daily-status'),expected);assert.equal(await page.locator('section[id^="s-"]').count(),0); }
    assert.ok(await page.getByText('还没有发布警务科技日报',{exact:true}).isVisible());reset();await page.reload();await ready(page);
    check('empty issue series, absent service, failure and malformed data remain distinct');
    payload={...structuredClone(MOCK_REPORT),leadItemId:null,lead:{title:'今日安静，无大事发生',leadParagraph:'本刊时段已完成评判，没有新的警务科技大事。'},sections:[],highlights:[],flashes:[],metrics:{totalEvents:0}};await goto(page);assert.ok(await page.getByRole('heading',{name:'今日安静，无大事发生'}).isVisible());assert.equal(await page.getByText('本期版面',{exact:true}).count(),0);
    payload=structuredClone(MOCK_REPORT);payload.sections=[{...payload.sections[0],items:[payload.sections[0].items[0]]}];payload.highlights=[];payload.flashes=[];await goto(page);assert.equal(await page.getByText('头条',{exact:true}).count(),1);assert.equal(await page.locator('section[id^="s-"]').count(),0);
    check('quiet front and sole lead retain separate source branches');
    reset();payload.cover={url:'/daily-fixture-missing.svg',width:800,height:450,caption:null};await goto(page);await page.waitForFunction(()=>!document.querySelector('img[src="/daily-fixture-missing.svg"]'));assert.ok(await page.getByRole('heading',{name:MOCK_REPORT.lead.title,exact:true}).isVisible());
    payload.cover={url:'/daily-fixture-cover.svg',srcSet:'/daily-fixture-cover.svg 800w',width:800,height:450,caption:null};await goto(page);assert.equal(await page.locator('img[fetchpriority="high"]').count(),1);
    check('cover srcSet/high priority and broken-image fallback keep the lead');
    reset();const withdrawn=payload.sections[2].items[0];Object.assign(withdrawn,{available:false,summary:null,sourceName:'',sourceUrl:'',sourceIconUrl:null,firstParty:false,publishedAt:null});await goto(page);const card=page.locator(`#r-${withdrawn.itemId}`);assert.equal(await card.getByRole('link').count(),0);assert.ok(await card.getByText('该内容已按来源方要求下架或调整展示方式。',{exact:false}).isVisible());
    check('withdrawn citations retain marked title without summary or original link');
    reset();await goto(page,'/daily/2026-09-28');assert.equal(await page.locator('[data-daily-status]').getAttribute('data-daily-status'),'not-found');mode='unavailable';await goto(page,'/daily/2026-09-28');assert.equal(await page.locator('[data-daily-status]').getAttribute('data-daily-status'),'unavailable');reset();await page.getByRole('button',{name:'重试',exact:true}).click();await ready(page,'/daily/2026-09-28');assert.equal(await page.locator('[data-daily-status]').getAttribute('data-daily-status'),'not-found');
    check('missing date is not latest, absent detail service is not missing date, retry is real');
    for(const path of ['reports/weekly/latest-page','reports/daily/2026-02-30','reports/daily/months/2026-13','reports/daily/extra/nested'])assert.equal((await page.request.get(`${origin}/api/bluepulse/site/${path}`)).status(),404);
    assert.equal((await page.request.get(`${origin}/api/bluepulse/site/reports/daily/latest-page`)).headers()['cache-control'],policy);
    check('proxy allows only the five daily read shapes and preserves cache policy');
    await goto(page,'/hot?mock=1');const before=count('/latest-page');await page.locator('[data-home-sidebar] a[href="/daily?mock=1"]').hover();await page.waitForTimeout(200);assert.equal(count('/latest-page'),before);
    await goto(page,'/hot');await page.locator('[data-home-sidebar] a[href="/daily"]').hover();await page.waitForTimeout(300);const prefetched=count('/latest-page');await menu(page,'/daily');assert.equal(count('/latest-page'),prefetched);
    // The previous ready DOM can remain until the refresh effect starts; wait for the actual read.
    const refreshed=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/bluepulse/site/reports/daily/latest-page');
    await menu(page,'/daily');await refreshed;await ready(page);assert.equal(count('/latest-page'),prefetched+1);
    check('mock prefetch stays isolated, live intent/enter share cache, active menu refreshes');
    policy='no-store';await goto(page);const noStore=count('/latest-page');await menu(page,'/hot');await page.goBack();await ready(page);assert.ok(count('/latest-page')>noStore);
    policy='public, max-age=60';age=59;await goto(page);await menu(page,'/hot');await page.waitForTimeout(1300);const expired=count('/latest-page');await page.goBack();await ready(page);assert.ok(count('/latest-page')>expired);
    check('no-store and consumed age cannot be extended by navigation restoration');
    await goto(page,'/all?mock=1');
    const product=page.locator('a[data-filter="product"]');assert.equal(Math.round((await product.boundingBox()).height),36);await product.click();await ready(page,'/all');assert.equal(new URL(page.url()).searchParams.get('topic'),'product');assert.equal(await page.locator('a[data-filter="product"]').getAttribute('aria-current'),'page');
    check('shared md category switch keeps its original size and URL selection');
    await goto(page,'/daily?mock=1');const row=page.locator('article[data-card-key]').last();await row.scrollIntoViewIfNeeded();const saved=await paper(page).evaluate(el=>el.scrollTop), id=await row.getAttribute('data-card-key');await row.getByRole('link').first().click();await ready(page,`/articles/${id}`);await page.goBack();await ready(page);assert.ok(Math.abs(await paper(page).evaluate(el=>el.scrollTop)-saved)<3);
    check('original citation opens the existing reader and back restores its paper position');
    await context.close();
  }
  assert.deepEqual(errors,[]);await writeFile(`${artifacts}/results.json`,JSON.stringify({checks,errors,layouts},null,2));console.log(`${checks.length} focused checks passed`);
} finally { await browser?.close();server.kill();await new Promise(resolve=>api.close(resolve)); }
