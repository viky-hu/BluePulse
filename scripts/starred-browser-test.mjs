// Production components against a controlled local HTTP boundary; no external collection or model calls.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { MOCK_HOME_DATA } from '../src/app/_lib/home-mock.ts';

const runtime = process.env.PULSE_PLAYWRIGHT_MODULE ?? 'C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs';
const { chromium } = await import(pathToFileURL(runtime).href);
const origin='http://127.0.0.1:3160', artifacts='test-results/starred';
const key='blue-pulse-starred-items-v1', readKey='blue-pulse-read-items-v1';
const id=n=>`c3300000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const saved=n=>({id:id(n),title:`警务科技公开材料 ${n}：辅助分析系统的适用条件与人工复核`,summary:'这是一段用于测试真实收藏组件的中文摘要，检查窄白纸中的长文本换行与操作区域。所有样本仅用于本地自动化验证。',sourceName:'收藏时的来源名称',publishedAt:'2026-10-28T16:30:00Z',savedAt:'2026-10-29T00:00:00Z',score:85});
const file=n=>({name:'pulse-test.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({version:1,starred:Array.from({length:n},(_,i)=>saved(i+1)),read:[id(1)],theme:'dark'}))});
const checks=[], errors=[], requests=[]; let partial=true, held=false, release, log='', browser;
const api=createServer(async(req,res)=>{
  const url=new URL(req.url,origin); res.setHeader('Content-Type','application/json'); res.setHeader('Cache-Control','no-store');
  if(url.pathname==='/api/v1/articles/availability'){
    const ids=url.searchParams.get('ids').split(','); requests.push(ids);
    if(held) await new Promise(done=>{release=done;});
    if(partial&&ids.includes(id(101))){res.statusCode=503;res.end('{}');return;}
    res.end(JSON.stringify({items:ids.map(value=>({id:value,available:value!==id(3),...(value===id(4)?{status:'summary-only'}:{}),source_name:'当前公开来源'}))})); return;
  }
  if(url.pathname==='/api/v1/taxonomy'){res.end('{"items":[]}');return;}
  if(url.pathname==='/api/v1/articles'){
    res.end(JSON.stringify({items:[{...MOCK_HOME_DATA.articles[0],id:id(300),title:saved(300).title,topics:[]}],next_cursor:null,limit:40}));return;
  }
  if(url.pathname.startsWith('/api/v1/articles/')){
    const value=url.pathname.split('/').at(-1), n=Number(value.slice(-12));
    res.end(JSON.stringify({...MOCK_HOME_DATA.articles[0],id:value,title:saved(n).title,source_body:null,zh_body:null,author:null,quality_status:'test',body_status:'summary_only',translation_status:'source_unavailable',media:[],entities:[],topics:[]}));return;
  }
  res.statusCode=404;res.end('{}');
});
await new Promise(done=>api.listen(3161,'127.0.0.1',done));
const server=spawn(process.execPath,['node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port','3160'],{cwd:process.cwd(),env:{...process.env,BLUEPULSE_API_URL:'http://127.0.0.1:3161'},stdio:['ignore','pipe','pipe'],windowsHide:true});
server.stdout.on('data',d=>{log+=d;});server.stderr.on('data',d=>{log+=d;});
const check=name=>{checks.push(name);console.log(`PASS ${name}`);};
const ready=async(page,path='/starred')=>{
  await page.waitForFunction(path=>location.pathname===path&&document.querySelector('[data-entry="stable"] [data-phase="idle"]')&&document.querySelector('[data-navigation-progress]')?.getAttribute('data-active')==='false',path);
};
const cards=page=>page.locator('[data-p0-scroller] [data-card-key]');
const paper=page=>page.locator('[data-p0-scroller]');
async function importFile(page,payload){await page.locator('input[type=file]').setInputFiles(payload);await page.getByRole('status').filter({hasText:'导入完成'}).waitFor();}
async function menu(page,path){const toggle=page.getByRole('button',{name:'打开菜单',exact:true});if(await toggle.isVisible())await toggle.click();await page.locator(`aside a[href="${path}"]`).click();await ready(page,path);}
try{
  await mkdir(artifacts,{recursive:true});
  for(let i=0;i<100;i++){try{if((await fetch(`${origin}/starred`)).ok)break;}catch{}if(i===99)throw Error(log);await new Promise(done=>setTimeout(done,100));}
  browser=await chromium.launch({headless:true});
  for(const mode of ['desktop','mobile','reduced']){
    const context=await browser.newContext({viewport:mode==='mobile'?{width:390,height:844}:{width:1360,height:760},reducedMotion:mode==='reduced'?'reduce':'no-preference',acceptDownloads:true});
    const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
    await page.goto(`${origin}/starred`);await ready(page);
    assert.equal(await cards(page).count(),0);assert.equal(await page.getByRole('button',{name:'导出',exact:true}).count(),0);
    assert.match(await page.locator('meta[name=robots]').getAttribute('content'),/noindex/);
    assert.match(await page.title(),/收藏/);
    assert.equal(await page.locator('aside a[href="/starred"]').getAttribute('aria-current'),'page');
    await page.screenshot({path:`${artifacts}/${mode}-empty.png`});check(`${mode}: direct stable page, selected menu, private metadata and empty state`);
    const count=mode==='desktop'?205:12;
    await importFile(page,file(count));assert.equal(await cards(page).count(),count);
    await page.getByText('这条内容已不再公开，收藏会保留直到你手动移除。',{exact:true}).waitFor();
    assert.equal(await page.locator(`[data-card-key="${id(3)}"] a`).count(),0);
    assert.equal(await page.locator(`[data-card-key="${id(4)}"]`).getByText('应来源方要求，这条内容现在只提供摘要。',{exact:true}).count(),1);
    await page.getByText('当前公开来源',{exact:true}).first().waitFor();
    assert.equal(await paper(page).evaluate(el=>el.scrollWidth<=el.clientWidth+1),true);
    assert.equal(await page.locator(`[data-card-key="${id(1)}"] h2`).evaluate(el=>getComputedStyle(el).fontSize),'16px');
    const savedTime=page.locator(`[data-card-key="${id(1)}"]`).getByText(/收藏于/);
    assert.equal(await savedTime.isVisible(),mode!=='mobile');
    assert.match(await cards(page).first().innerText(),/2026-10-29 00:30/);
    await page.screenshot({path:`${artifacts}/${mode}-list.png`});
    if(mode==='desktop'){
      await page.getByText('暂时无法核对文章状态，已保留收藏；可稍后重新打开此页。',{exact:true}).waitFor();
      assert.equal(await page.locator(`[data-card-key="${id(101)}"] a`).count(),1);
      assert.equal(await page.locator(`[data-card-key="${id(205)}"] a`).count(),1);
      assert.ok(requests.every(batch=>batch.length<=100));
      partial=false;const before=requests.length;await menu(page,'/starred');await page.waitForFunction(()=>!document.querySelector('[data-p0-scroller]').textContent.includes('暂时无法核对文章状态'));
      assert.ok(requests.length>before);check('independent 100-ID batches preserve success and unknown links; active-menu refresh rechecks');
    }
    check(`${mode}: import, explicit unavailable/summary-only states, current source, Beijing time and no overflow`);
    await importFile(page,file(count));assert.equal(await cards(page).count(),count);
    assert.match(await page.getByRole('status').filter({hasText:'导入完成'}).innerText(),/新增收藏 0 条/);
    const downloadEvent=page.waitForEvent('download');await page.getByRole('button',{name:'导出',exact:true}).click();const download=await downloadEvent;
    assert.match(download.suggestedFilename(),/^pulse-local-data-/);
    const data=JSON.parse(await readFile(await download.path(),'utf8'));assert.equal(data.starred.length,count);assert.deepEqual(data.read,[id(1)]);assert.equal(data.theme,'auto');
    check(`${mode}: repeated same-file import deduplicates and JSON download round trip includes read IDs`);
    const second=await context.newPage();await second.goto(`${origin}/starred`);await ready(second);
    await cards(page).first().getByRole('button',{name:'取消收藏',exact:true}).click();
    await second.waitForFunction(n=>document.querySelectorAll('[data-card-key]').length===n,count-1);
    assert.equal(new URL(page.url()).pathname,'/starred');check(`${mode}: remove button does not navigate and other tabs synchronize`);
    await second.close();
    const target=page.locator(`[data-card-key="${id(10)}"]`);await target.scrollIntoViewIfNeeded();await page.evaluate(()=>new Promise(requestAnimationFrame));
    const offset=await target.evaluate(el=>el.getBoundingClientRect().top-el.closest('[data-p0-scroller]').getBoundingClientRect().top);
    await target.locator('h2 a').click();await ready(page,`/articles/${id(10)}`);await page.goBack();await ready(page);
    const restoredOffset=await page.locator(`[data-card-key="${id(10)}"]`).evaluate(el=>el.getBoundingClientRect().top-el.closest('[data-p0-scroller]').getBoundingClientRect().top);
    assert.ok(Math.abs(restoredOffset-offset)<6,`anchor offset ${offset} -> ${restoredOffset}`);
    const persisted=await page.evaluate(key=>JSON.parse(localStorage.getItem(key)),readKey);assert.ok(persisted.includes(id(10)));
    check(`${mode}: article read persists independently and browser back restores p0 anchor`);
    await context.close();
  }
  const flow=await browser.newContext({reducedMotion:'reduce'});const reading=await flow.newPage();reading.on('pageerror',e=>errors.push(e.message));
  await reading.goto(`${origin}/articles/${id(300)}`);await ready(reading,`/articles/${id(300)}`);
  const action=reading.locator(`[data-star-id="${id(300)}"]`);assert.equal(await action.getAttribute('aria-pressed'),'false');await action.click();assert.equal(await action.getAttribute('aria-pressed'),'true');
  await menu(reading,'/starred');assert.equal(await cards(reading).count(),1);assert.equal(await cards(reading).first().getAttribute('data-card-key'),id(300));
  await reading.reload();await ready(reading);assert.equal(await cards(reading).count(),1);
  await reading.goto(`${origin}/history`);await ready(reading,'/history');await reading.getByRole('button',{name:'清空历史',exact:true}).click();
  await menu(reading,'/all');await reading.waitForSelector(`article[data-item-id="${id(300)}"][data-read="true"]`);
  assert.equal(await reading.evaluate(()=>JSON.parse(localStorage.getItem('blue-pulse-reading-history-v1')).length),0);
  check('clearing thirty-entry history retains independent read marks in all-feed cards');
  await reading.goto(`${origin}/starred?mock=1`);await ready(reading);assert.equal(await cards(reading).count(),0);
  check('detail bookmark persists through menu/reload and explicit mock namespace remains isolated');await flow.close();
  const limited=await browser.newContext({reducedMotion:'reduce'});const partialPage=await limited.newPage();partialPage.on('pageerror',e=>errors.push(e.message));
  await partialPage.addInitScript(readKey=>{localStorage.setItem(readKey,'[]');const set=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(k===readKey)throw new DOMException('quota','QuotaExceededError');return set.call(this,k,v);};},readKey);
  await partialPage.goto(`${origin}/starred`);await ready(partialPage);await importFile(partialPage,file(1));
  assert.equal(await cards(partialPage).count(),1);await partialPage.getByRole('status').filter({hasText:'已读记录没能保存'}).waitFor();
  await partialPage.getByRole('status').filter({hasText:'导入完成'}).getByRole('button',{name:'关闭',exact:true}).click();await partialPage.getByRole('status').filter({hasText:'导入完成'}).waitFor({state:'detached'});
  check('read-only write failure reports partial success and import notice can close');await limited.close();
  const context=await browser.newContext({reducedMotion:'reduce'});const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(({key})=>{const set=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(k===key)throw new DOMException('quota','QuotaExceededError');return set.call(this,k,v);};},{key});
  await page.goto(`${origin}/starred`);await ready(page);await page.locator('input[type=file]').setInputFiles(file(1));
  await page.getByRole('status').filter({hasText:'这次没有导入任何内容'}).waitFor();assert.equal(await cards(page).count(),0);check('failed durable star write never reports import success or inserts memory records');await context.close();
  const damaged=await browser.newContext({reducedMotion:'reduce'});const corrupt=await damaged.newPage();await corrupt.addInitScript(key=>localStorage.setItem(key,'{broken'),key);
  await corrupt.goto(`${origin}/starred`);await ready(corrupt);await corrupt.locator('input[type=file]').setInputFiles(file(1));await corrupt.getByRole('status').filter({hasText:'为避免覆盖'}).waitFor();
  assert.equal(await corrupt.evaluate(key=>localStorage.getItem(key),key),'{broken');check('corrupt saved data remains recoverable after rejected import');await damaged.close();
  const slow=await browser.newContext({reducedMotion:'reduce'});const pending=await slow.newPage();held=true;
  await pending.addInitScript(({key,item})=>localStorage.setItem(key,JSON.stringify([item])),{key,item:saved(1)});
  await pending.goto(`${origin}/starred`);await ready(pending);assert.equal(await cards(pending).count(),1);await menu(pending,'/hot');held=false;release?.();await pending.waitForTimeout(100);assert.equal(new URL(pending.url()).pathname,'/hot');check('local list becomes ready before remote check and leaving cancels stale work');await slow.close();
  assert.deepEqual(errors,[]);
}finally{
  held=false;release?.();await writeFile(`${artifacts}/verification.json`,JSON.stringify({checks,errors,requests},null,2));await browser?.close();server.kill();api.closeAllConnections();await new Promise(done=>api.close(done));
}
