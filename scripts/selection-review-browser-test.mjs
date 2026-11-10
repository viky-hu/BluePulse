import {readFileSync,writeFileSync,mkdtempSync,rmSync,mkdirSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
import {chromium} from 'file:///C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs';
const root=resolve('backend/bluepulse_backend/review_assets');
const fixture={schema_version:1,packet_id:'test-packet',cases:[{case_id:'c1',material_id:'m1',revision:1,content_hash:'abc',title:'<img src=x onerror="globalThis.hacked=true">',source_name:'测试来源',source_url:'javascript:alert(1)',body:'原文全文',analysis_text:'原文分析输入',input_truncated:true,assist:null}],coverage:{}};
const scenarios=[
 {title:'普通警务走访',body:'民警开展社区走访，没有科技内容。',relevance:'irrelevant',select:'reject',primary_topic:null,evidence_level:'unknown'},
 {title:'例行科技维护',body:'现有警务视频系统例行维护，没有新技术或新做法。',relevance:'direct',select:'reject',primary_topic:'practice',evidence_level:'unknown'},
 {title:'无人机创新试点',body:'无人机事故勘查开展小范围试点，说明了流程和观察结果。',relevance:'direct',select:'select',primary_topic:'practice',evidence_level:'pilot_observation'},
 {title:'科技相关法规',body:'新发布电子证据保存规则，尚未给出实际实施效果。',relevance:'direct',select:'select',primary_topic:'law',evidence_level:'announcement'},
 {title:'新闻信息不足',body:'文章没有交代具体技术和用途，无法判断。',relevance:'uncertain',select:'uncertain',primary_topic:null,evidence_level:'unknown'},
 {title:'日常警务中的技术线索',body:'主体是日常警务行动，顺带提到值得继续了解的技术做法。',relevance:'potential',select:'reject',primary_topic:'practice',evidence_level:'unknown'},
 {title:'其他领域技术的警务用途',body:'其他领域的技术有具体进展，能说明对警务科技的用途。',relevance:'potential',select:'uncertain',primary_topic:'product',evidence_level:'announcement'},
 {title:'暂时不好分类的技术线索',body:'有值得继续了解的技术线索，但现有分类都不贴切。',relevance:'potential',select:'reject',primary_topic:'other',evidence_level:'unknown'},
];
fixture.cases.push(...scenarios.map((s,i)=>({...fixture.cases[0],case_id:'scenario-'+i,material_id:'scenario-'+i,title:s.title,body:s.body,analysis_text:s.body,input_truncated:false})));
mkdirSync(resolve('test-results'),{recursive:true});
const dir=mkdtempSync(join(resolve('test-results'),'pulse-review-test-'));
const html=readFileSync(join(root,'review.html'),'utf8').replace('%%STYLE%%',readFileSync(join(root,'review.css'),'utf8')).replace('%%SCRIPT%%',readFileSync(join(root,'review.js'),'utf8')).replace('%%FONT%%','').replace('%%PACKET%%',JSON.stringify(fixture).replaceAll('<','\\u003c'));
writeFileSync(join(dir,'review.html'),html);
const browser=await chromium.launch({headless:true,downloadsPath:dir,executablePath:process.env.PULSE_REVIEW_BROWSER || 'C:/Users/Admin/AppData/Local/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-win64/chrome-headless-shell.exe'});
try {
const page=await browser.newPage({acceptDownloads:true,viewport:{width:1440,height:950}});await page.goto(pathToFileURL(join(dir,'review.html')).href);
assert.equal(await page.locator('h1').textContent(),'请帮我们挑选值得关注的警务科技新闻');
assert.equal(await page.locator('#review-form h3').textContent(),'读完新闻，请回答下面的问题');
for(const [name,question,count]of [['relevance','这条新闻和警务科技有关吗？',4],['select','这条新闻值得重点推荐吗？',3],['primary_topic','这条新闻主要讲什么？',8],['evidence_level','报道具体说到哪一步了？',6]]){
 const section=page.locator(`[data-question="${name}"]`);assert.match(await section.textContent(),new RegExp(question));assert.equal(await section.locator('.choice-guide dt').count(),count);assert.equal(await section.locator('.choice-guide').isVisible(),true);
}
assert.match(await page.locator('[data-question=relevance]').textContent(),/例行维护/);
const potentialHelp=page.locator('[data-question=relevance] .choice-guide div').filter({has:page.locator('dt',{hasText:'有潜在用途'})});
assert.match(await potentialHelp.textContent(),/主要讲日常警务/);
assert.match(await potentialHelp.textContent(),/没有重点介绍新技术、新方法/);
assert.doesNotMatch(await page.locator('[data-question=relevance]').textContent(),/新闻没有直接讲警务/);
assert.match(await page.locator('[data-question=relevance]').textContent(),/不涉及科技的一般制度改革/);
assert.doesNotMatch(await page.locator('body').innerText(),/校准|迁移价值|技术主张|不可变记录|内容哈希/);
assert.doesNotMatch(await page.locator('#coverage').textContent(),/source_slug|available_unique|material_kinds|sources[：:]/);
assert.doesNotMatch(await page.locator('#review-form').textContent(),/直接相关：明确涉及警务任务；/);
await page.locator('#reviewer').fill('甲');
await page.locator('[name=relevance]').selectOption('irrelevant');
assert.equal(await page.locator('[name=select]').inputValue(),'reject');
assert.equal(await page.locator('[name=primary_topic]').isDisabled(),true);
assert.equal(await page.locator('[name=evidence_level]').isDisabled(),true);
await page.locator('[name=reason]').fill('普通社区走访报道，没有科技应用或技术进展。');
await page.locator('#confirm').click();
assert.deepEqual(await page.evaluate(()=>PulseReview.state.records[0].gold),{relevance:'irrelevant',select:'reject',primary_topic:null,evidence_level:'unknown',reason:'普通社区走访报道，没有科技应用或技术进展。'});
assert.match(await page.locator('#votes').textContent(),/主要内容：不用填写（无关）/);
await page.reload();assert.equal(await page.locator('[name=evidence_level]').isDisabled(),true);
await page.locator('[name=relevance]').selectOption('direct');
assert.equal(await page.locator('[name=evidence_level]').isDisabled(),false);
assert.equal(await page.locator('[name=evidence_level]').inputValue(),'');
await page.locator('#reviewer').fill('甲');await page.locator('[name=relevance]').selectOption('direct');await page.locator('[name=select]').selectOption('select');await page.locator('[name=primary_topic]').selectOption('product');await page.locator('[name=evidence_level]').selectOption('unknown');await page.locator('[name=reason]').fill('有明确警务产品信息');await page.reload();assert.equal(await page.locator('[name=reason]').inputValue(),'有明确警务产品信息');
await page.locator('#confirm').click();assert.equal(await page.evaluate(()=>PulseReview.state.records.length),2);
assert.match(await page.locator('#votes').textContent(),/主要内容：产品、装备或功能/);
assert.match(await page.locator('#votes').textContent(),/报道情况：文章没说清楚/);
await page.evaluate(()=>{const a=PulseReview.state.records.at(-1);const b={...a,record_id:crypto.randomUUID(),reviewer:'乙',gold:{...a.gold,select:'reject'}};PulseReview.importBundle({...PulseReview.exportBundle(),records:[b]});});
assert.equal(await page.evaluate(()=>PulseReview.caseStatus('c1').status),'conflict');
await page.locator('#resolution-reason').fill('核对原文后采用甲的判断');await page.locator('#resolve').click();assert.equal(await page.evaluate(()=>PulseReview.caseStatus('c1').status),'resolved');
await page.evaluate(()=>{const a=PulseReview.state.records.at(-2);PulseReview.importBundle({...PulseReview.exportBundle(),records:[...PulseReview.state.records,{...a,record_id:crypto.randomUUID(),updated_at:'2099-01-01T00:00:00.000Z'}]});});assert.equal(await page.evaluate(()=>PulseReview.caseStatus('c1').status),'conflict');
const downloadPromise=page.waitForEvent('download');await page.locator('#export').click();const download=await downloadPromise;assert.match(download.suggestedFilename(),/test-packet.*json$/);
assert.equal(await page.evaluate(()=>{const current=PulseReview.exportBundle();for(const mutate of [b=>b.records[0].updated_at='2026-02-30T12:00:00Z',b=>b.records[0].gold.primary_topic='',b=>b.records[0].gold.select='invalid',b=>b.records[0].content_hash='wrong',b=>b.records[0].gold.reason='rewritten']){const candidate=structuredClone(current);mutate(candidate);const before=JSON.stringify(PulseReview.state);let rejected=false;try{PulseReview.importBundle(candidate);}catch{rejected=true;}if(!rejected||before!==JSON.stringify(PulseReview.state))return false;}return true;}),true);
await page.evaluate(()=>{const b=PulseReview.exportBundle();PulseReview.importBundle(b);});
assert.equal(await page.evaluate(()=>!!globalThis.hacked),false);assert.equal(await page.locator('#source-link').getAttribute('href'),null);
assert.equal(await page.evaluate(()=>{const before=JSON.stringify(PulseReview.state);try{PulseReview.importBundle({schema_version:1,packet_id:'wrong',records:[],drafts:[],resolutions:[]});}catch{}return before===JSON.stringify(PulseReview.state);}),true);
for(const [i,s]of scenarios.entries()){
 await page.locator('#case-list button').filter({hasText:s.title}).click();await page.locator('#reviewer').fill('场景验收');
 await page.locator('[name=relevance]').selectOption(s.relevance);
 if(s.relevance!=='irrelevant'){await page.locator('[name=select]').selectOption(s.select);await page.locator('[name=primary_topic]').selectOption(s.primary_topic||'');await page.locator('[name=evidence_level]').selectOption(s.evidence_level);}
 await page.locator('[name=reason]').fill(s.body);await page.locator('#confirm').click();
 const saved=await page.evaluate(id=>PulseReview.state.records.filter(r=>r.case_id===id).at(-1)?.gold,'scenario-'+i);
 assert.deepEqual(saved,{relevance:s.relevance,select:s.select,primary_topic:s.primary_topic,evidence_level:s.evidence_level,reason:s.body});
}
await page.locator('#case-list button').first().click();
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
