// Production UI + controlled HTTP boundary. No collection or paid model calls.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import { MOCK_HOME_DATA } from "../src/app/_lib/home-mock.ts";

const playwright = process.env.PULSE_PLAYWRIGHT_MODULE ?? "C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs";
const { chromium } = await import(pathToFileURL(playwright).href);
const origin = "http://127.0.0.1:3150", artifacts = "test-results/all-feed";
const categories = ["product", "practice", "paper", "embodied", "public-opinion", "low-altitude"];
const taxonomy = categories.map(slug => ({ id: slug, slug, name_zh: { product: "产品", practice: "实战", paper: "论文", embodied: "具身", "public-opinion": "舆情", "low-altitude": "低空" }[slug], name_en: slug, parent_id: null }));
const rows = Array.from({ length: 48 }, (_, i) => ({ ...MOCK_HOME_DATA.articles[i % 8], id: `b2200000-0000-4000-8000-${String(i + 1).padStart(12, "0")}`, title: `警务科技公开材料 ${i + 1}：智能辅助系统的适用条件与人工复核`, summary: "这是一段受控测试摘要，用来检查真实组件在多行中文、来源信息、阅读状态和容器宽度变化下的表现。接口测试不代表真实新闻或后端已经上线。", importance_score: 92 - i, topics: [categories[i % categories.length]], published_at: i === 4 ? null : new Date(Date.UTC(2026, 9, 29, 5) - i * 45 * 60_000).toISOString(), first_seen_at: new Date(Date.UTC(2026, 9, 29, 5) - i * 45 * 60_000).toISOString() }));
const requests = [], checks = [], errors = [], held = new Map();
let fail = true, taxonomyFail = false, browser, serverLog = "";
const api = createServer(async (req, res) => {
  const url = new URL(req.url, origin), q = url.searchParams.get("q") ?? "";
  requests.push({ path: url.pathname, search: url.search });
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Cache-Control", q === "nostore" ? "no-store" : "public, max-age=60");
  if (url.pathname === "/api/v1/taxonomy") {
    if (taxonomyFail) { res.statusCode = 503; res.end("{}"); return; }
    res.end(JSON.stringify({ items: taxonomy })); return;
  }
  if (url.pathname === "/api/v1/sources") { res.end(JSON.stringify({ items: MOCK_HOME_DATA.sources })); return; }
  if (url.pathname === "/api/v1/articles") {
    if (q === "held") await new Promise(done => held.set("list", done));
    if (q === "fail" && fail) { res.statusCode = 503; res.end("{}"); return; }
    if (q === "malformed") { res.end('{"items":null,"next_cursor":null}'); return; }
    const region = url.searchParams.get("region"), topic = url.searchParams.get("topic");
    if (url.searchParams.get("cursor") === "bad") { res.statusCode = 400; res.end('{"error":{"code":"invalid_cursor"}}'); return; }
    const list = q === "empty" ? [] : rows.filter(item => (!region || item.region === region) && (!topic || item.topics.includes(topic)));
    const offset = url.searchParams.get("cursor") === "second" ? 40 : 0;
    res.end(JSON.stringify({ items: list.slice(offset, offset + 40), next_cursor: list.length > offset + 40 ? "second" : null, limit: 40 })); return;
  }
  const id = url.pathname.split("/").at(-1), item = rows.find(row => row.id === id);
  if (item) { res.end(JSON.stringify({ ...item, source_body: null, zh_body: null, author: null, quality_status: "test", body_status: "summary_only", translation_status: "source_unavailable", media: [], entities: [] })); return; }
  res.statusCode = 404; res.end("{}");
});
await new Promise(done => api.listen(3151, "127.0.0.1", done));
const server = spawn(process.execPath, ["node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "3150"], { cwd: process.cwd(), env: { ...process.env, BLUEPULSE_API_URL: "http://127.0.0.1:3151" }, stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
server.stdout.on("data", d => { serverLog += d; }); server.stderr.on("data", d => { serverLog += d; });
const check = name => { checks.push(name); console.log(`PASS ${name}`); };
const ready = async (page, path = "/all") => {
  await page.waitForFunction(path => location.pathname === path && document.querySelector('[data-entry="stable"] [data-phase="idle"]') && document.querySelector('[data-navigation-progress]')?.getAttribute("data-active") === "false" && (path !== "/all" || (document.querySelector("[data-all-status]") && document.querySelector("[data-all-status]").getAttribute("data-all-status") !== "loading")), path);
};
const goto = async (page, path) => { await page.goto(`${origin}${path}`); await ready(page, path.split(/[?#]/)[0]); };
const filter = (page, key) => page.locator(`[data-filter="${key}"]`);
const paper = page => page.locator("[data-p0-scroller]");
const cards = page => page.locator("article[data-item-id]");
async function menu(page, path) {
  const button = page.getByRole("button", { name: "打开菜单", exact: true });
  if (await button.isVisible()) await button.click();
  await page.locator(`aside a[href="${path}"]`).click(); await ready(page, path);
}
async function search(page, value) {
  await page.locator("#all-search").fill(value); await page.locator("#all-search").press("Enter");
  await page.waitForURL(url => (url.searchParams.get("q") ?? "") === value); await ready(page);
}
try {
  await mkdir(artifacts, { recursive: true });
  for (let i = 0; i < 100; i++) {
    try { if ((await fetch(`${origin}/hot`)).ok) break; } catch {}
    if (i === 99) throw Error(serverLog);
    await new Promise(done => setTimeout(done, 100));
  }
  browser = await chromium.launch({ headless: true });
  for (const mode of ["desktop", "mobile", "reduced"]) {
    const context = await browser.newContext({ viewport: mode === "mobile" ? { width: 390, height: 844 } : { width: 1360, height: 760 }, reducedMotion: mode === "reduced" ? "reduce" : "no-preference" });
    const page = await context.newPage(); page.on("pageerror", e => errors.push(e.message));
    await goto(page, "/all");
    assert.equal(await cards(page).count(), 40);
    assert.equal(await filter(page, "all").getAttribute("aria-current"), "page");
    const firstRequest = requests.find(r => r.path === "/api/v1/articles");
    assert.equal(new URLSearchParams(firstRequest.search).get("period"), "all");
    assert.equal(new URLSearchParams(firstRequest.search).get("limit"), "40");
    assert.equal(await cards(page).first().locator('[aria-label="AI 评分 92 分"]:visible').count(), 1);
    assert.equal(await paper(page).evaluate(el => el.scrollWidth <= el.clientWidth + 1), true);
    assert.deepEqual(await page.locator('[aria-label="筛选"] a').allTextContents(), ["全部", "国内", "国外", "产品", "实战", "论文", "法制", "具身", "舆情", "低空"]);
    const tabGeometry = await filter(page, "all").evaluate(el => { const s = getComputedStyle(el); return { height: el.getBoundingClientRect().height, padding: s.paddingInlineStart, font: s.fontSize }; });
    assert.deepEqual(tabGeometry, { height: mode === "mobile" ? 44 : 36, padding: "16px", font: "14px" });
    const tabBox = await page.locator('[aria-label="筛选"]').boundingBox(), inputBox = await page.locator("#all-search").boundingBox();
    if (mode === "mobile") assert.ok(inputBox.y > tabBox.y + tabBox.height);
    else { assert.ok(Math.abs(inputBox.y - tabBox.y) < 4); assert.equal(inputBox.width, 240); }
    const activeBox = await filter(page, "all").boundingBox(), thumbBox = await filter(page, "all").locator(':scope > span[aria-hidden="true"]').boundingBox();
    for (const dimension of ["x", "y", "width", "height"]) assert.ok(Math.abs(activeBox[dimension] - thumbBox[dimension]) < 1);
    assert.equal(await page.locator('[data-all-status] > header > p').count(), 0);
    assert.doesNotMatch(await page.locator('[data-all-status]').innerText(), /2026年|今天|本页\s*\d/);
    await page.evaluate(() => {
      window.__allScenePhases = [];
      const stage = document.querySelector('[data-home-view="/all"]');
      new MutationObserver(() => { if (stage.dataset.phase !== "idle") window.__allScenePhases.push(stage.dataset.phase); }).observe(stage, { attributes: true, attributeFilter: ["data-phase"] });
    });
    await page.screenshot({ path: `${artifacts}/${mode}.png` });
    check(`${mode}: 40 real rows, correct score and request, ten tabs, container layout and no overflow`);
    await page.keyboard.press("/"); assert.equal(await page.locator("#all-search").evaluate(el => el === document.activeElement), true);
    await page.locator("#all-search").fill("警务");
    await page.locator("#all-search").dispatchEvent("compositionstart"); await page.locator("#all-search").press("Enter");
    assert.equal(new URL(page.url()).searchParams.has("q"), false);
    await page.locator("#all-search").dispatchEvent("compositionend"); await page.locator("#all-search").press("Enter"); await page.waitForURL(url => url.searchParams.get("q") === "警务"); await ready(page);
    assert.equal(await page.getByRole("tab", { name: "全文相关", exact: true }).isDisabled(), true);
    assert.equal(await page.getByText("全文相关排序暂不可用", { exact: true }).count(), 0);
    await filter(page, "paper").click(); await page.waitForURL(url => url.searchParams.get("topic") === "paper"); await ready(page);
    assert.equal(new URL(page.url()).searchParams.get("q"), "警务");
    assert.equal(await cards(page).count(), 8);
    await filter(page, "domestic").click(); await page.waitForURL(url => url.searchParams.get("region") === "domestic"); await ready(page);
    assert.equal(new URL(page.url()).searchParams.has("topic"), false);
    await filter(page, "embodied").click(); await page.waitForURL(url => url.searchParams.get("topic") === "embodied"); await ready(page);
    assert.equal(new URL(page.url()).searchParams.has("region"), false);
    await page.getByRole("button", { name: "清空", exact: true }).click();
    assert.equal(new URL(page.url()).searchParams.get("q"), "警务");
    await page.locator("#all-search").press("Enter"); await page.waitForURL(url => !url.searchParams.has("q")); await ready(page);
    check(`${mode}: slash, IME guard, search modes, preserved query, mutually exclusive tabs and draft clearing`);
    await filter(page, "law").click(); await page.waitForURL(url => url.searchParams.get("topic") === "law"); await ready(page);
    assert.equal(await page.getByText("分类暂不可用", { exact: true }).count(), 1);
    await filter(page, "paper").click(); await page.waitForURL(url => url.searchParams.get("topic") === "paper"); await ready(page); await search(page, "empty");
    assert.equal(await page.getByText("没有找到相关内容", { exact: true }).count(), 1);
    assert.deepEqual(await page.evaluate(() => window.__allScenePhases), [], "all query changes must never run Pulse scene transitions");
    await page.screenshot({ path: `${artifacts}/${mode}-empty.png` });
    check(`${mode}: unregistered category is distinct from a registered empty result`);
    await goto(page, "/all");
    const bookmark = cards(page).first().getByRole("button", { name: "收藏", exact: true }); await bookmark.click();
    assert.equal(await cards(page).first().getByRole("button", { name: "取消收藏" }).getAttribute("aria-pressed"), "true");
    const card = cards(page).nth(3); const id = await card.getAttribute("data-item-id"); await card.scrollIntoViewIfNeeded();
    const before = await paper(page).evaluate(el => el.scrollTop);
    await card.locator("h3 a").click(); await ready(page, `/articles/${id}`);
    await page.goBack(); await ready(page);
    assert.equal(await page.locator(`article[data-item-id="${id}"]`).getAttribute("data-read"), "true");
    assert.ok(Math.abs(await paper(page).evaluate(el => el.scrollTop) - before) < 5);
    await page.locator('[aria-label="分页"]').getByRole("link", { name: "下一页" }).click(); await page.waitForURL(url => url.searchParams.get("cursor") === "second"); await ready(page);
    assert.equal(await cards(page).count(), 8); assert.equal(await page.getByRole("link", { name: "上一页", exact: true }).count(), 1);
    await page.getByRole("link", { name: "上一页", exact: true }).click(); await page.waitForURL(url => !url.searchParams.has("cursor")); await ready(page);
    assert.equal(await cards(page).count(), 40);
    await paper(page).evaluate(el => { el.scrollTop = 450; });
    await page.evaluate(() => new Promise(requestAnimationFrame));
    const sticky = await page.locator('section[aria-label="2026-10-29"] > div').first().boundingBox(), scrollBox = await paper(page).boundingBox();
    if (Math.abs(sticky.y - scrollBox.y) >= 3) { console.log({ mode, sticky, scrollBox, top: await paper(page).evaluate(el => el.scrollTop) }); await page.screenshot({ path: `${artifacts}/${mode}-sticky.png` }); }
    assert.ok(Math.abs(sticky.y - scrollBox.y) < 3, "day header sticks within p0");
    check(`${mode}: local bookmark/read, article return position, cursor round trip and p0 sticky date`);
    await context.close();
  }
  const context = await browser.newContext({ viewport: { width: 1360, height: 760 }, reducedMotion: "reduce" });
  const page = await context.newPage(); page.on("pageerror", e => errors.push(e.message));
  await goto(page, "/all?cursor=second"); assert.equal(await page.getByRole("link", { name: "返回第一页" }).count(), 1);
  await goto(page, "/all?period=7d&topic=policing&source_type=media&entity=test&sort=importance");
  assert.equal(await page.locator('[aria-label="其他筛选条件"]').count(), 0);
  await filter(page, "all").click(); await page.waitForURL(url => !url.searchParams.has("topic")); await ready(page);
  for (const [key, value] of [["period", "7d"], ["source_type", "media"], ["entity", "test"], ["sort", "importance"]]) assert.equal(new URL(page.url()).searchParams.get(key), value);
  check("direct cursor uses first-page recovery; legacy query dimensions persist without added filter UI");
  await goto(page, "/all?q=fail"); assert.equal(await page.locator('[data-all-status="error"]').getByRole("alert").count(), 1); fail = false;
  await page.getByRole("button", { name: "重试", exact: true }).click(); await page.waitForSelector('[data-all-status="ready"]');
  await goto(page, "/all?q=malformed"); assert.equal(await page.locator('[data-all-status="error"]').getByRole("alert").count(), 1);
  await goto(page, "/all?cursor=bad"); assert.equal(await page.locator('[data-all-status="error"]').getByRole("alert").count(), 1);
  assert.equal(await page.getByRole("link", { name: "返回第一页" }).count(), 1);
  check("503 is retryable and malformed data / invalid cursors never appear as empty results");
  await context.close();
  const fastContext = await browser.newContext({ viewport: { width: 1360, height: 760 }, reducedMotion: "reduce" });
  const fast = await fastContext.newPage(); fast.on("pageerror", e => errors.push(e.message));
  await goto(fast, "/all");
  await fast.locator("#all-search").fill("held"); await fast.locator("#all-search").press("Enter");
  await fast.waitForURL(url => url.searchParams.get("q") === "held");
  await fast.locator('[data-navigation-progress][data-visible="true"]').waitFor();
  assert.equal(await cards(fast).count(), 40, "old results remain during same-feed loading");
  assert.equal(await fast.locator('[data-home-view="/all"]').getAttribute("data-phase"), "idle");
  await fast.waitForFunction(() => getComputedStyle(document.querySelector('[data-feed-busy="true"]')).opacity === "0.5");
  await menu(fast, "/hot"); held.get("list")?.(); held.delete("list"); await fast.waitForTimeout(250);
  assert.equal(new URL(fast.url()).pathname, "/hot");
  check("leaving a slow request settles immediately and its late result cannot overwrite the destination");
  await goto(fast, "/all?q=nostore");
  const count = requests.filter(r => r.path === "/api/v1/articles" && r.search.includes("q=nostore")).length;
  await menu(fast, "/hot"); await fast.goBack(); await ready(fast);
  assert.equal(requests.filter(r => r.path === "/api/v1/articles" && r.search.includes("q=nostore")).length, count + 1);
  check("no-store data revalidates on history return");
  taxonomyFail = true;
  await goto(fast, "/all?topic=product&fresh=1");
  await fast.reload(); await ready(fast); assert.equal(await fast.locator('[data-all-status="error"]').getByRole("alert").count(), 1);
  taxonomyFail = false;
  check("taxonomy service failure is an error rather than unregistered or empty classification");
  await goto(fast, "/all?mock=1"); assert.equal(await fast.getByRole("heading", { name: "全部动态（演示）", exact: true }).count(), 1);
  await cards(fast).first().locator("h3 a").click(); await fast.waitForURL(url => url.pathname.startsWith("/articles/")); await ready(fast, new URL(fast.url()).pathname);
  assert.ok((await paper(fast).innerText()).includes("演示数据"));
  check("explicit mock data and its detail route are labeled and isolated");
  await fastContext.close(); assert.deepEqual(errors, []);
} finally {
  for (const release of held.values()) release();
  await writeFile(`${artifacts}/verification.json`, JSON.stringify({ checks, errors, requests }, null, 2));
  await browser?.close(); server.kill(); api.closeAllConnections(); await new Promise(done => api.close(done));
}
