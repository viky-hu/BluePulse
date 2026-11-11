// Focused production checks for AIHOT-derived phone chrome; explicit mock data, no collection/model calls.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
const { chromium } = await import(pathToFileURL(process.env.PULSE_PLAYWRIGHT_MODULE ?? 'C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs').href);
const port = Number(process.env.PULSE_MOBILE_PORT ?? 3190), origin = `http://127.0.0.1:${port}`, artifacts = 'test-results/mobile-shell';
const server = spawn(process.execPath, ['node_modules/next/dist/bin/next', 'start', '--hostname', '127.0.0.1', '--port', String(port)], { cwd: process.cwd(), env: { ...process.env, BLUEPULSE_API_URL: 'http://127.0.0.1:1' }, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
let log = '', browser, current;
server.stdout.on('data', data => { log += data; }); server.stderr.on('data', data => { log += data; });
const checks = [], errors = [];
const pass = name => { checks.push(name); console.log(`PASS ${name}`); };
async function ready(page, pathname) {
  await page.waitForFunction(path => location.pathname === path && document.querySelector('[data-entry="stable"] [data-phase="idle"]') && document.querySelector('[data-p0-scroller]')?.getAttribute('aria-busy') === 'false', pathname, { timeout: 30000 });
}
const tab = (page, name) => page.getByRole('navigation', { name: '底部导航' }).getByRole('link', { name: new RegExp(`^${name}`) });
async function geometry(page, width) {
  return page.evaluate(w => {
    const b = selector => { const r = document.querySelector(selector).getBoundingClientRect(); return { x:r.x, y:r.y, width:r.width, height:r.height, bottom:r.bottom, right:r.right }; };
    const paper=b('[data-main-paper]'), frame=b('[data-p0-content]'), green=b('[data-main-green]'), tabs=b('[data-mobile-tabs]'), header=b('[data-mobile-header]');
    const scroller=document.querySelector('[data-p0-scroller]');
    return { paper,frame,green,tabs,header,overflow:scroller.scrollWidth-scroller.clientWidth,windowOverflow:document.documentElement.scrollWidth-w,padding:getComputedStyle(scroller).paddingInlineStart };
  }, width);
}
async function shot(page, name) { await page.screenshot({ path:`${artifacts}/${name}.png` }); }
try {
  await mkdir(artifacts, { recursive:true });
  for(let n=0;n<100;n++){try{if((await fetch(`${origin}/more`)).ok)break;}catch{} if(n===99)throw Error(log); await new Promise(r=>setTimeout(r,100));}
  browser=await chromium.launch({headless:true});
  for(const reduced of [false,true]) {
    const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,reducedMotion:reduced?'reduce':'no-preference'});
    const page=current=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
    await page.addInitScript(()=>{
      window.__entrySamples=[];
      const sample=()=>{const menu=document.querySelector('[data-home-sidebar]');window.__entrySamples.push({entry:document.documentElement.dataset.pulseEntry,menu:menu?getComputedStyle(menu).display:null,intro:!!document.querySelector('[data-intro-panel]')});if(window.__entrySamples.length<180)requestAnimationFrame(sample);};requestAnimationFrame(sample);
    });
    await page.goto(`${origin}/?mock=1`);await ready(page,'/');
    assert.equal(await page.locator('[data-intro-panel]').count(),0);
    assert.equal(await page.getByRole('button',{name:'打开菜单',exact:true}).count(),0);
    assert.equal(await page.locator('[data-home-sidebar]').isVisible(),false);
    assert.equal(await tab(page,'精选').getAttribute('aria-current'),'page');
    assert.equal(await page.locator('[data-mobile-tabs] a').count(),5);
    const b=await geometry(page,390);
    for(const k of ['x','y','width','height'])assert.ok(Math.abs(b.paper[k]-b.frame[k])<.2,k);
    assert.equal(b.paper.x,6);assert.equal(b.paper.width,378);assert.equal(b.paper.y,56);assert.equal(b.paper.bottom,b.tabs.y-8);
    assert.equal(b.green.x,0);assert.equal(b.green.y,0);assert.equal(b.green.width,390);assert.equal(b.green.height,844);assert.equal(b.padding,'14px');
    assert.ok(b.overflow<=1&&b.windowOverflow<=1);
    await shot(page,`390-home${reduced?'-reduced':''}`);
    assert.equal(await page.evaluate(()=>window.__entrySamples.some(s=>s.entry==='intro'||s.intro||s.menu&&s.menu!=='none')),false);
    pass(`${reduced?'reduced':'normal'}: first mobile paint, full green, 6px paper, five tabs, no intro/sidebar`);
    await tab(page,'全部').click();await ready(page,'/all');
    assert.equal(await page.getByRole('navigation',{name:'筛选',exact:true}).isVisible(),false);
    await page.getByRole('button',{name:'筛选',exact:true}).click();
    const sheet=page.getByRole('dialog',{name:'筛选',exact:true});await sheet.waitFor();
    assert.equal(await page.locator('[data-p0-scroller]').evaluate(el=>getComputedStyle(el).overflow),'hidden');
    const option=sheet.getByRole('link',{name:'论文',exact:true});assert.ok(await option.evaluate(el=>el.offsetHeight>=48));
    await option.click();await ready(page,'/all');await sheet.waitFor({state:'hidden'});
    await page.waitForFunction(()=>new URLSearchParams(location.search).get('topic')==='paper');
    assert.equal(await page.getByRole('link',{name:'取消筛选：论文',exact:true}).isVisible(),true);
    await shot(page,`390-filter${reduced?'-reduced':''}`);
    await page.getByRole('button',{name:'筛选（已选）',exact:true}).click();await sheet.waitFor();
    assert.equal(await sheet.getByRole('link',{name:'论文',exact:true}).getAttribute('aria-current'),'true');
    await page.keyboard.press('Escape');await sheet.waitFor({state:'hidden'});
    assert.equal(await page.getByRole('button',{name:'筛选（已选）',exact:true}).evaluate(el=>el===document.activeElement),true);
    await page.getByRole('link',{name:'取消筛选：论文',exact:true}).click();await ready(page,'/all');
    await page.waitForFunction(()=>!new URLSearchParams(location.search).has('topic'));
    pass(`${reduced?'reduced':'normal'}: filter sheet URL, checked choice, clear, scroll lock and focus restoration`);
    await page.locator('[data-p0-scroller]').evaluate(el=>{el.scrollTop=400;});
    await tab(page,'全部').click();await page.waitForFunction(()=>document.querySelector('[data-p0-scroller]').scrollTop===0);
    await page.getByRole('link',{name:'搜索',exact:true}).click();await ready(page,'/search');
    assert.equal(await tab(page,'全部').getAttribute('aria-current'),'page');
    await tab(page,'更多').click();await ready(page,'/more');
    assert.equal(await page.locator('[data-more-page]').isVisible(),true);
    await page.goBack();await ready(page,'/search');assert.equal(await tab(page,'全部').getAttribute('aria-current'),'page');
    await page.reload();await ready(page,'/search');assert.equal(await tab(page,'全部').getAttribute('aria-current'),'page');
    pass(`${reduced?'reduced':'normal'}: repeat tab scrolls p0; search tab survives history and reload`);
    await tab(page,'全部').click();await ready(page,'/all');
    const filterPoint=await page.getByRole('button',{name:'筛选',exact:true}).boundingBox();
    await tab(page,'热点').click();
    await page.mouse.click(filterPoint.x+filterPoint.width/2,filterPoint.y+filterPoint.height/2);
    assert.equal(await page.getByRole('dialog',{name:'筛选',exact:true}).count(),0,'outgoing toolbar cannot open a filter during a tab transition');
    await ready(page,'/hot');
    pass(`${reduced?'reduced':'normal'}: outgoing toolbar cannot reopen filters during tab change`);
    await tab(page,'日报').click();await ready(page,'/daily');
    const kind=page.locator('[data-mobile-header]').getByRole('navigation',{name:'切换日报、周报、月报'});
    assert.equal(await kind.getByRole('tab',{name:'周报',exact:true}).isDisabled(),true);
    assert.equal(await kind.getByRole('tab',{name:'月报',exact:true}).isDisabled(),true);
    assert.equal((await kind.getByRole('link',{name:'日报',exact:true}).boundingBox()).height,44);
    assert.equal(await kind.getByRole('link',{name:'日报',exact:true}).locator('span[aria-hidden]').evaluate(el=>el.getBoundingClientRect().height),32);
    await page.getByRole('button',{name:'本期目录',exact:true}).click();
    const outline=page.getByRole('dialog',{name:'本期目录',exact:true});await outline.waitFor();
    await outline.getByRole('link').first().click();await outline.waitFor({state:'hidden'});assert.ok(await page.evaluate(()=>location.hash.length>1));
    await shot(page,`390-daily${reduced?'-reduced':''}`);
    await page.goto(`${origin}/daily/archive?mock=1`);await ready(page,'/daily/archive');await tab(page,'日报').click();await ready(page,'/daily');
    pass(`${reduced?'reduced':'normal'}: daily compact switch, outline anchor and tab-root navigation`);
    await page.goto(`${origin}/articles/4ed2a8d4-efb7-4ce6-8a43-4ee36f27d001?mock=1`);await ready(page,'/articles/4ed2a8d4-efb7-4ce6-8a43-4ee36f27d001');
    assert.equal(await page.locator('[data-mobile-tabs]').count(),0);assert.equal(await page.locator('[data-mobile-header]').isVisible(),false);
    assert.equal(await page.getByRole('navigation',{name:'阅读工具',exact:true}).isVisible(),true);
    const rb=await page.locator('[data-p0-content]').boundingBox();assert.equal(rb.y,8);assert.equal(rb.y+rb.height,836);
    await shot(page,`390-reader${reduced?'-reduced':''}`);pass(`${reduced?'reduced':'normal'}: reader replaces bottom tabs and releases chrome space`);
    await page.goto(`${origin}/about?mock=1`);await ready(page,'/about');
    await page.getByRole('button',{name:'产品初始页'}).click();
    await page.locator('[data-scroll-cue-shell] button:not(:disabled)').waitFor({timeout:45000});
    assert.equal(new URL(page.url()).searchParams.get('intro'),'1');
    await page.evaluate(()=>{window.__menuFrames=[];const tick=()=>{const el=document.querySelector('[data-home-sidebar]');window.__menuFrames.push(el&&getComputedStyle(el).display);if(document.querySelector('[data-intro-panel]')||document.querySelector('[data-entry="revealing"]'))requestAnimationFrame(tick);};requestAnimationFrame(tick);});
    // The existing cover advances automatically; its ready button enters the main paper.
    await page.locator('[data-scroll-cue-shell] button').click();
    await ready(page,'/');await page.waitForFunction(()=>!new URLSearchParams(location.search).has('intro'));
    assert.equal(await page.evaluate(()=>window.__menuFrames.some(v=>v&&v!=='none')),false);
    await page.reload();await ready(page,'/');assert.equal(await page.locator('[data-intro-panel]').count(),0);
    pass(`${reduced?'reduced':'normal'}: about explicit replay, clean URL, no sidebar frames and stable refresh`);
    await context.close();
  }
  const blocked=await browser.newContext({viewport:{width:390,height:844}});
  await blocked.addInitScript(()=>{Storage.prototype.getItem=()=>{throw new DOMException('blocked','SecurityError');};Storage.prototype.setItem=()=>{throw new DOMException('blocked','SecurityError');};});
  current=await blocked.newPage();current.on('pageerror',e=>errors.push(e.message));await current.goto(`${origin}/?mock=1`);await ready(current,'/');assert.equal(await current.locator('[data-intro-panel]').count(),0);pass('storage unavailable still opens phone home');await blocked.close();
  const responsive=await browser.newContext({viewport:{width:320,height:640}});const page=current=await responsive.newPage();page.on('pageerror',e=>errors.push(e.message));
  for(const width of [320,768,769,1440]){
    await page.setViewportSize({width,height:width===1440?900:640});
    for(const path of ['/all','/daily','/hot','/more','/about']){
      await page.goto(`${origin}${path}?mock=1`);await ready(page,path);
      assert.equal(await page.locator('[data-home-sidebar]').isVisible(),width>768);
      assert.equal(await page.locator('[data-mobile-tabs]').isVisible(),width<=768);
      assert.equal(await page.locator('[data-mobile-header]').isVisible(),width<=768);
      const overflow=await page.locator('[data-p0-scroller]').evaluate(el=>el.scrollWidth-el.clientWidth);assert.ok(overflow<=1,`${width} ${path} overflow ${overflow}`);
      if(width<=768){const visible=await page.locator('[data-mobile-header] [data-phone-bar-content]').count()?page.locator('[data-mobile-header] [data-phone-bar-content]'):page.locator('[data-mobile-header] > div').first();assert.ok(await visible.evaluate(el=>[...el.querySelectorAll('a,button')].filter(n=>n.getClientRects().length).every(n=>{const r=n.getBoundingClientRect();return r.x>=0&&r.right<=innerWidth;})),`${width} ${path} controls fit`);}
      if([320,1440].includes(width))await shot(page,`${width}-${path.slice(1)}`);
    }
    pass(`${width}px: five routes fit and correct desktop/mobile chrome`);
  }
  await responsive.close();
  const short=await browser.newContext({viewport:{width:390,height:460},isMobile:true,hasTouch:true});
  current=await short.newPage();current.on('pageerror',e=>errors.push(e.message));
  const cdp=await short.newCDPSession(current);
  await cdp.send('Emulation.setSafeAreaInsetsOverride',{insets:{top:24,left:8,right:10,bottom:21}});
  await current.goto(`${origin}/search?mock=1`);await ready(current,'/search');
  await current.getByRole('textbox',{name:'搜索关键词'}).focus();
  // Shrink the viewport with the input focused to model the space left by a phone keyboard.
  await current.setViewportSize({width:390,height:340});
  const safe=await geometry(current,390);
  assert.equal(safe.paper.x,14);assert.equal(safe.paper.right,374);assert.equal(safe.paper.y,80);
  assert.equal(safe.tabs.height,71);assert.equal(safe.paper.bottom,safe.tabs.y-8);
  assert.equal(safe.green.height,340);assert.ok(safe.overflow<=1&&safe.windowOverflow<=1);
  assert.equal(await current.getByRole('textbox',{name:'搜索关键词'}).evaluate(el=>el===document.activeElement),true);
  await shot(current,'390-short-safe-area');await short.close();
  pass('short focused search: simulated keyboard and four safe-area insets preserve paper and controls');
  assert.deepEqual(errors,[]);
} catch(error){if(current&&!current.isClosed())await shot(current,'failure').catch(()=>{});throw error;}
finally {await writeFile(`${artifacts}/verification.json`,JSON.stringify({checks,errors},null,2));await browser?.close();server.kill();}
