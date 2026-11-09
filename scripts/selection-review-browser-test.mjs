import {readFileSync,writeFileSync,mkdtempSync,rmSync,mkdirSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
import {chromium} from 'file:///C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs';
const root=resolve('backend/bluepulse_backend/review_assets');
const fixture={schema_version:1,packet_id:'test-packet',cases:[{case_id:'c1',material_id:'m1',revision:1,content_hash:'abc',title:'<img src=x onerror="globalThis.hacked=true">',source_name:'测试来源',source_url:'javascript:alert(1)',body:'原文全文',analysis_text:'原文分析输入',input_truncated:true,assist:null}],coverage:{}};
mkdirSync(resolve('test-results'),{recursive:true});
const dir=mkdtempSync(join(resolve('test-results'),'pulse-review-test-'));
const html=readFileSync(join(root,'review.html'),'utf8').replace('%%STYLE%%',readFileSync(join(root,'review.css'),'utf8')).replace('%%SCRIPT%%',readFileSync(join(root,'review.js'),'utf8')).replace('%%FONT%%','').replace('%%PACKET%%',JSON.stringify(fixture).replaceAll('<','\\u003c'));
writeFileSync(join(dir,'review.html'),html);
const browser=await chromium.launch({headless:true,downloadsPath:dir,executablePath:process.env.PULSE_REVIEW_BROWSER || 'C:/Users/Admin/AppData/Local/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-win64/chrome-headless-shell.exe'});
try {
const page=await browser.newPage({acceptDownloads:true,viewport:{width:1440,height:950}});await page.goto(pathToFileURL(join(dir,'review.html')).href);
await page.locator('#reviewer').fill('甲');await page.locator('[name=relevance]').selectOption('direct');await page.locator('[name=select]').selectOption('select');await page.locator('[name=primary_topic]').selectOption('product');await page.locator('[name=evidence_level]').selectOption('unknown');await page.locator('[name=reason]').fill('有明确警务产品信息');await page.reload();assert.equal(await page.locator('[name=reason]').inputValue(),'有明确警务产品信息');
await page.locator('#confirm').click();assert.equal(await page.evaluate(()=>PulseReview.state.records.length),1);
await page.evaluate(()=>{const a=PulseReview.state.records[0];const b={...a,record_id:crypto.randomUUID(),reviewer:'乙',gold:{...a.gold,select:'reject'}};PulseReview.importBundle({...PulseReview.exportBundle(),records:[b]});});
assert.equal(await page.evaluate(()=>PulseReview.caseStatus('c1').status),'conflict');
await page.locator('#resolution-reason').fill('核对原文后采用甲的判断');await page.locator('#resolve').click();assert.equal(await page.evaluate(()=>PulseReview.caseStatus('c1').status),'resolved');
await page.evaluate(()=>{const a=PulseReview.state.records[0];PulseReview.importBundle({...PulseReview.exportBundle(),records:[...PulseReview.state.records,{...a,record_id:crypto.randomUUID(),updated_at:'2099-01-01T00:00:00.000Z'}]});});assert.equal(await page.evaluate(()=>PulseReview.caseStatus('c1').status),'conflict');
const downloadPromise=page.waitForEvent('download');await page.locator('#export').click();const download=await downloadPromise;assert.match(download.suggestedFilename(),/test-packet.*json$/);
assert.equal(await page.evaluate(()=>{const current=PulseReview.exportBundle();for(const mutate of [b=>b.records[0].updated_at='2026-02-30T12:00:00Z',b=>b.records[0].gold.primary_topic='',b=>b.records[0].gold.select='invalid',b=>b.records[0].content_hash='wrong',b=>b.records[0].gold.reason='rewritten']){const candidate=structuredClone(current);mutate(candidate);const before=JSON.stringify(PulseReview.state);let rejected=false;try{PulseReview.importBundle(candidate);}catch{rejected=true;}if(!rejected||before!==JSON.stringify(PulseReview.state))return false;}return true;}),true);
await page.evaluate(()=>{const b=PulseReview.exportBundle();PulseReview.importBundle(b);});
assert.equal(await page.evaluate(()=>!!globalThis.hacked),false);assert.equal(await page.locator('#source-link').getAttribute('href'),null);
assert.equal(await page.evaluate(()=>{const before=JSON.stringify(PulseReview.state);try{PulseReview.importBundle({schema_version:1,packet_id:'wrong',records:[],drafts:[],resolutions:[]});}catch{}return before===JSON.stringify(PulseReview.state);}),true);
for(const viewport of [{width:1440,height:950},{width:390,height:844}]){await page.setViewportSize(viewport);await page.emulateMedia({reducedMotion:'reduce'});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);}
await page.locator('[name=reason]').fill('</script><script>globalThis.htmlReturnHacked=true</script> 交回草稿');
await page.locator('[name=reason]').blur();const snapshot=await page.evaluate(()=>({bundle:PulseReview.exportBundle(),reviewer:document.getElementById('reviewer').value}));
const htmlDownloadPromise=page.waitForEvent('download');await page.locator('#export-html').click();const htmlDownload=await htmlDownloadPromise;const returned=join(dir,'returned.html');await htmlDownload.saveAs(returned);
const clean=await browser.newContext({offline:true});const portable=await clean.newPage();await portable.goto(pathToFileURL(returned).href);
assert.deepEqual(await portable.evaluate(()=>PulseReview.exportBundle()),snapshot.bundle);assert.equal(await portable.locator('#reviewer').inputValue(),snapshot.reviewer);assert.equal(await portable.locator('[name=reason]').inputValue(),'</script><script>globalThis.htmlReturnHacked=true</script> 交回草稿');assert.equal(await portable.evaluate(()=>!!globalThis.htmlReturnHacked),false);assert.equal(await portable.evaluate(()=>PulseReview.caseStatus('c1').status),'conflict');
await portable.locator('#import').setInputFiles(returned);assert.match(await portable.locator('#message').textContent(),/导入完成/);const prior=await portable.evaluate(()=>JSON.stringify(PulseReview.state));await portable.locator('#import').setInputFiles(join(dir,'review.html'));assert.match(await portable.locator('#message').textContent(),/不含已标注/);assert.equal(await portable.evaluate(()=>JSON.stringify(PulseReview.state)),prior);await clean.close();
const blocked=await browser.newPage();await blocked.addInitScript(()=>Object.defineProperty(window,'localStorage',{get(){throw new Error('disabled');}}));await blocked.goto(pathToFileURL(join(dir,'review.html')).href);assert.match(await blocked.locator('#storage-status').textContent(),/导出/);await blocked.close();
console.log('Offline review browser checks passed');
}finally{await browser.close();rmSync(dir,{recursive:true,force:true});}
