// Run with node --experimental-strip-types. Set PULSE_PLAYWRIGHT_MODULE if Playwright is bundled outside the project.
// Uses an isolated production server, isolated browser contexts and a deterministic HTTP fixture; no ingestion/models.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import { MOCK_HOME_DATA, MOCK_HOME_FEATURED, MOCK_ARTICLE_DETAILS, MOCK_TAXONOMY, MOCK_SOURCES } from "../src/app/_lib/home-mock.ts";
import { calculateMainPanelRect, calculatePanelGeometry, calculateReportGeometry } from "../src/app/_components/intro/intro-config.ts";

const { chromium } = await import(process.env.PULSE_PLAYWRIGHT_MODULE ? pathToFileURL(process.env.PULSE_PLAYWRIGHT_MODULE).href : "playwright");
const port = Number(process.env.PULSE_TEST_PORT ?? 3100), apiPort = port + 1;
const origin = `http://127.0.0.1:${port}`;
const artifactDir = "test-results/aihot-foundations";
const starredKey = "blue-pulse-starred-items-v1", enteredKey = "blue-pulse-entry-complete-v1";
const first = MOCK_HOME_DATA.articles[0];
let articleOnline = true, availabilityOnline = true, feedRequests = 0, detailRequests = 0;
const withdrawn = new Set();
function detail(article) { return { ...article, body_status: article.body_status ?? "full_text", translation_status: article.translation_status ?? "not_required", entities: article.entities ?? [], media: article.media ?? [] }; }
const api = createServer(async (request, response) => {
  const url = new URL(request.url, `http://127.0.0.1:${apiPort}`);
  response.setHeader("Content-Type", "application/json"); response.setHeader("Cache-Control", "no-store");
  let data;
  if (url.pathname === "/api/v1/taxonomy") data = MOCK_TAXONOMY;
  else if (url.pathname === "/api/v1/sources") data = MOCK_SOURCES;
  else if (url.pathname === "/api/v1/home/featured") data = MOCK_HOME_FEATURED;
  else if (url.pathname === "/api/v1/home/recently-collected") data = { items: MOCK_HOME_DATA.articles };
  else if (url.pathname === "/api/v1/articles/availability") {
    if (!availabilityOnline) response.statusCode = 503;
    data = { items: (url.searchParams.get("ids") ?? "").split(",").filter(Boolean).map(id => ({ id, available: !!MOCK_ARTICLE_DETAILS[id] && !withdrawn.has(id) })) };
  } else if (url.pathname === "/api/v1/articles") {
    feedRequests++;
    const q = url.searchParams.get("q") ?? "";
    if (q === "slow") await new Promise(resolve => setTimeout(resolve, 700));
    if (q === "fail") response.statusCode = 503;
    data = { items: q && !["slow", "fail"].includes(q) ? MOCK_HOME_DATA.articles.filter(a => a.title.includes(q)) : MOCK_HOME_DATA.articles, next_cursor: null, limit: 20 };
  } else if (url.pathname.startsWith("/api/v1/articles/")) {
    detailRequests++;
    const row = MOCK_ARTICLE_DETAILS[url.pathname.split("/").at(-1)];
    response.statusCode = !articleOnline ? 503 : row ? 200 : 404;
    data = row ? detail(row) : {};
  } else if (url.pathname === "/api/v1/entities") data = { items: [], next_cursor: null };
  else { response.statusCode = 404; data = {}; }
  response.end(JSON.stringify(data));
});
await new Promise(resolve => api.listen(apiPort, "127.0.0.1", resolve));
const server = spawn(process.execPath, ["node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", String(port)], { cwd: process.cwd(), env: { ...process.env, BLUEPULSE_API_URL: `http://127.0.0.1:${apiPort}` }, stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
let serverLog = "";
server.stdout.on("data", chunk => { serverLog += chunk; }); server.stderr.on("data", chunk => { serverLog += chunk; });
let browser;
const checks = [], browserErrors = [];
const check = (name) => { checks.push(name); console.log(`PASS ${name}`); };
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function settled(page, pathname) {
  await page.waitForFunction(path => location.pathname === path && document.querySelector('[data-entry="stable"] [data-phase="idle"]') && document.querySelector('[data-home-view]')?.getAttribute("inert") === null, pathname, { timeout: 20000 });
  await page.waitForFunction(() => ![...document.querySelectorAll('[data-p0-scroller] [role="status"]')].some(item => item.getClientRects().length && getComputedStyle(item).visibility !== "hidden" && item.textContent.includes("正在载入")), null, { timeout: 20000 }).catch(async error => {
    await page.screenshot({ path: `${artifactDir}/failure.png` });
    console.error(await page.locator('[data-p0-scroller]').innerText());
    throw error;
  });
}
async function menu(page, pathname) {
  if (await page.getByRole("button", { name: "打开菜单", exact: true }).isVisible()) await page.getByRole("button", { name: "打开菜单", exact: true }).click();
  await page.locator(`aside a[href="${pathname}?mock=1"]`).click();
  await settled(page, pathname);
}
async function geometry(page, width, height) {
  const expected = calculateMainPanelRect(calculatePanelGeometry(width, height), calculateReportGeometry(width, height));
  const bounds = await page.locator("[data-main-paper]").boundingBox();
  for (const [key, value] of Object.entries({ x: expected.x, y: expected.y, width: expected.width, height: expected.height })) assert.ok(Math.abs(bounds[key] - value) < 1, `${key}: ${bounds[key]} vs ${value}`);
  const frame = await page.locator("[data-p0-content]").boundingBox();
  for (const key of ["x", "y", "width", "height"]) assert.ok(Math.abs(bounds[key] - frame[key]) < .1);
  assert.equal(await page.evaluate(() => window.scrollY), 0);
}
try {
  for (let n = 0; n < 100; n++) { try { if ((await fetch(`${origin}/search?mock=1`)).ok) break; } catch {} if (n === 99) throw Error(serverLog); await pause(100); }
  browser = await chromium.launch({ headless: true });
  await mkdir(artifactDir, { recursive: true });
  for (const mode of (process.env.PULSE_TEST_MODES?.split(",").filter(Boolean) ?? ["desktop", "mobile", "reduced"])) {
    const width = mode === "mobile" ? 390 : 1360, height = mode === "mobile" ? 844 : 760;
    const context = await browser.newContext({ viewport: { width, height }, reducedMotion: mode === "reduced" ? "reduce" : "no-preference" });
    const page = await context.newPage(); page.on("pageerror", error => browserErrors.push(`${mode}: ${error.message}`));
    await page.goto(`${origin}/?mock=1`);
    await page.waitForSelector('[data-scroll-cue-shell] button:not(:disabled)', { timeout: 45000 });
    assert.equal(await page.evaluate(key => localStorage.getItem(key), `${enteredKey}:mock`), null);
    await page.locator('[data-scroll-cue-shell] button').click();
    if (mode !== "reduced") assert.equal(await page.evaluate(key => localStorage.getItem(key), `${enteredKey}:mock`), null);
    await settled(page, "/");
    assert.equal(await page.evaluate(key => localStorage.getItem(key), `${enteredKey}:mock`), "1");
    await geometry(page, width, height);
    if (mode === "mobile") {
      assert.equal(await page.locator('aside[aria-label="主菜单"]').isVisible(), false);
      await page.getByRole("button", { name: "打开菜单", exact: true }).click();
      assert.equal(await page.locator('aside[aria-label="主菜单"]').isVisible(), true);
      await page.getByRole("button", { name: "关闭菜单", exact: true }).first().click();
      assert.equal(await page.locator('aside[aria-label="主菜单"]').isVisible(), false);
    }
    await page.screenshot({ path: `${artifactDir}/${mode}.png` }); check(`${mode}: intro completion, endpoint geometry and menu`);
    await page.reload(); await settled(page, "/");
    assert.equal(await page.locator('[data-scroll-cue-shell]').count(), 0); check(`${mode}: revisit and refresh skip intro`);
    await menu(page, "/search");
    await page.getByRole("textbox", { name: "搜索关键词" }).fill("警务");
    await page.getByRole("button", { name: "搜索资讯", exact: true }).click();
    await page.waitForURL(url => url.pathname === "/search" && url.searchParams.get("q") === "警务");
    await settled(page, "/search");
    assert.equal(new URL(page.url()).searchParams.get("q"), "警务");
    await menu(page, "/topics/policing");
    assert.ok(await page.locator('[data-card-key]').count());
    await page.screenshot({ path: `${artifactDir}/${mode}-topic.png` }); check(`${mode}: search and real topic URL`);
    if (mode === "desktop") {
      await page.evaluate(() => { window.__planes = document.querySelector('[data-main-scene]'); });
      await page.locator('aside a[href="/search?mock=1"]').click(); await pause(40);
      await page.locator('aside a[href="/history?mock=1"]').click(); await pause(40);
      await page.locator('aside a[href="/starred?mock=1"]').click(); await settled(page, "/starred");
      assert.equal(await page.evaluate(() => window.__planes === document.querySelector('[data-main-scene]')), true);
      check("desktop: rapid navigation queues latest destination and keeps shared scene");
      await menu(page, "/");
      await page.locator('[data-star-id]').first().click();
      const second = await context.newPage(); await second.goto(`${origin}/starred?mock=1`); await settled(second, "/starred");
      assert.equal(await second.locator('[data-card-key]').count(), 1);
      await second.getByRole("button", { name: "移除收藏", exact: true }).click();
      await page.waitForFunction(() => !document.querySelector('[data-star-id][aria-pressed="true"]'));
      await second.close(); check("desktop: favorites persist and update across tabs");
      const before = await page.evaluate(() => { const area = document.querySelector('[data-p0-scroller]'); area.scrollTop = 400; return area.scrollTop; });
      await pause(100);
      const savedBefore = await page.evaluate(() => Object.fromEntries(Object.entries(sessionStorage).filter(([key]) => key.includes("position:"))));
      await page.evaluate(() => { const area = document.querySelector('[data-p0-scroller]'); const top = area.getBoundingClientRect().top; const row = [...area.querySelectorAll('[data-card-key]')].find(item => item.getBoundingClientRect().top > top); row.querySelector('a').click(); });
      await page.waitForURL(/\/articles\//);
      await settled(page, new URL(page.url()).pathname);
      await page.waitForSelector('[data-reading-page] h1');
      assert.equal(await page.locator('[data-star-id]').count(), 1);
      const sameBeforeBack = await page.evaluate(() => window.__planes === document.querySelector('[data-main-scene]'));
      await page.goBack(); await settled(page, "/"); await pause(150);
      const after = await page.locator('[data-p0-scroller]').evaluate(el => el.scrollTop);
      const savedAfter = await page.evaluate(() => Object.fromEntries(Object.entries(sessionStorage).filter(([key]) => key.includes("position:"))));
      const sameAfterBack = await page.evaluate(() => window.__planes === document.querySelector('[data-main-scene]'));
      assert.ok(before > 200 && Math.abs(before - after) < 2, `scroll ${before} -> ${after}; snapshots ${JSON.stringify({savedBefore,savedAfter,sameBeforeBack,sameAfterBack})}`); check("desktop: p0 return position and article read history");
      await menu(page, "/history"); assert.ok(await page.locator('[data-card-key]').count());
    }
    await context.close();
  }
  const deep = await browser.newContext({ viewport: { width: 1360, height: 760 } });
  const page = await deep.newPage(); page.on("pageerror", error => browserErrors.push(`deep: ${error.message}`));
  await page.goto(`${origin}/search?mock=1`); await settled(page, "/search");
  assert.equal(await page.locator('[data-scroll-cue-shell]').count(), 0);
  await menu(page, "/"); assert.equal(await page.locator('[data-scroll-cue-shell]').count(), 0); check("fresh deep link then home remains stable");
  await page.goto(`${origin}/search?q=slow`); await settled(page, "/search");
  const requests = feedRequests; await page.reload(); await settled(page, "/search"); assert.ok(feedRequests > requests); check("active refresh requests fresh feed");
  await page.goto(`${origin}/search?q=fail`); await settled(page, "/search"); assert.ok(await page.getByRole("alert").count()); check("errors are terminal content states");
  articleOnline = false;
  await page.goto(`${origin}/articles/${first.id}`); await settled(page, `/articles/${first.id}`);
  const detailCount = detailRequests; articleOnline = true;
  await page.getByRole("link", { name: "重新载入 ↗", exact: true }).click();
  await page.waitForSelector('[data-reading-page] h1'); await page.waitForFunction(title => document.querySelector('[data-reading-page] h1')?.textContent === title, first.title);
  assert.ok(detailRequests > detailCount); check("same-URL article retry refreshes server content");
  const snapshot = { id: first.id, title: first.title, summary: first.summary, sourceName: first.source.name, publishedAt: first.published_at, score: first.importance_score, savedAt: new Date().toISOString() };
  await page.evaluate(({ key, value }) => localStorage.setItem(key, JSON.stringify([value])), { key: starredKey, value: snapshot });
  withdrawn.add(first.id);
  await page.goto(`${origin}/starred`); await settled(page, "/starred");
  await page.getByText("文章已不可公开访问，保留本机收藏快照。", { exact: true }).waitFor(); assert.equal(await page.locator(`[data-card-key="${first.id}"] a`).count(), 0); check("withdrawn favorites retain snapshot without accessible link");
  availabilityOnline = false;
  await page.reload(); await settled(page, "/starred"); await page.getByText("暂时无法核对文章状态，已保留收藏；可稍后重新打开此页。", { exact: true }).waitFor();
  assert.equal(await page.locator(`[data-card-key="${first.id}"] a`).count(), 1); check("availability failure remains unknown instead of withdrawn");
  await deep.close();
  const damaged = await browser.newContext(); await damaged.addInitScript(key => localStorage.setItem(key, "{damaged"), `${starredKey}:mock`);
  const corrupt = await damaged.newPage(); await corrupt.goto(`${origin}/search?mock=1`); await settled(corrupt, "/search"); await corrupt.locator('[data-star-id]').first().click();
  assert.equal(await corrupt.evaluate(key => localStorage.getItem(key), `${starredKey}:mock`), "{damaged"); await corrupt.getByText("已保留无法读取的浏览器数据，变更仅在本次访问有效。", { exact: true }).waitFor(); check("damaged storage preserved with working memory favorites"); await damaged.close();
  const denied = await browser.newContext(); await denied.addInitScript(() => { Object.defineProperty(window, "localStorage", { get() { throw new DOMException("denied", "SecurityError"); } }); Object.defineProperty(window, "sessionStorage", { get() { throw new DOMException("denied", "SecurityError"); } }); });
  const restricted = await denied.newPage(); await restricted.goto(`${origin}/search?mock=1`); await settled(restricted, "/search"); await restricted.locator('[data-star-id]').first().click();
  await menu(restricted, "/starred"); assert.equal(await restricted.locator('[data-card-key]').count(), 1); await menu(restricted, "/"); assert.equal(await restricted.locator('[data-scroll-cue-shell]').count(), 0); check("restricted storage permits in-memory navigation and favorites"); await denied.close();
  assert.deepEqual(browserErrors, []);
  await writeFile(`${artifactDir}/verification.json`, JSON.stringify({ time: new Date().toISOString(), checks, browserErrors }, null, 2));
  console.log(`${checks.length} browser checks passed`);
} catch (error) {
  console.error(serverLog); throw error;
} finally { await browser?.close(); server.kill(); await new Promise(resolve => api.close(resolve)); }
