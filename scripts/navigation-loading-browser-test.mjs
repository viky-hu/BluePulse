// Deterministic HTTP fixtures only; no production backend, collection, models or notifications.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import { MOCK_HOME_DATA } from "../src/app/_lib/home-mock.ts";

const { chromium } = await import(pathToFileURL(process.env.PULSE_PLAYWRIGHT_MODULE).href);
const origin = "http://127.0.0.1:3130", artifacts = "test-results/navigation-loading";
const counts = new Map(), held = new Map(), checks = [], errors = [];
let statsMode = "ready", statsHeld = false, policyNoStore = false, homeHeld = false, legacyHeld = false;
const stats = { sources: 1, sourceKinds: { rss: 1 }, items: 12, selected: 2, dailies: null, day: { collected: 3, selected: null }, sampleSources: [{ name: "契约测试源", kind: "rss", heatOnly: false }], latest: [] };
const api = createServer(async (req, res) => {
  const url = new URL(req.url, origin), q = url.searchParams.get("q") ?? "";
  const key = url.pathname === "/api/v1/site/stats" ? "stats" : q;
  counts.set(key, (counts.get(key) ?? 0) + 1);
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Cache-Control", q === "nostore" || (q === "policy" && policyNoStore) ? "no-store" : "public, max-age=60");
  if (homeHeld && url.pathname === "/api/v1/articles" && !q) await new Promise(done => held.set("home", done));
  if (legacyHeld && q === "rsc-refresh") await new Promise(done => held.set("legacy", done));
  if (q.startsWith("held") || (key === "stats" && statsHeld)) await new Promise(done => held.set(key, done));
  if (q === "fail" || (key === "stats" && statsMode === "error")) { res.statusCode = 503; res.end("{}"); return; }
  if (url.pathname === "/api/v1/site/stats") { res.end(JSON.stringify(stats)); return; }
  if (url.pathname === "/api/v1/articles") { res.end(JSON.stringify({ items: MOCK_HOME_DATA.articles, next_cursor: null, limit: 20 })); return; }
  res.end(JSON.stringify({ items: [] }));
});
await new Promise(done => api.listen(3131, "127.0.0.1", done));
const server = spawn(process.execPath, ["node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "3130"], { cwd: process.cwd(), env: { ...process.env, BLUEPULSE_API_URL: "http://127.0.0.1:3131" }, stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
let log = "", browser;
server.stdout.on("data", data => { log += data; }); server.stderr.on("data", data => { log += data; });
const check = text => { checks.push(text); console.log(`PASS ${text}`); };
const release = key => { held.get(key)?.(); held.delete(key); };
async function settled(page, path, timeout = 30000) {
  await page.waitForFunction(path => location.pathname === path && document.querySelector('[data-entry="stable"] [data-phase="idle"]') && document.querySelector('[data-navigation-progress]')?.getAttribute("data-active") === "false", path, { timeout });
}
async function menu(page, path) {
  const toggle = page.getByRole("button", { name: "打开菜单", exact: true });
  if (await toggle.isVisible()) await toggle.click();
  await page.locator(`aside a[href="${path}"]`).click();
}
async function search(page, q) {
  await page.getByRole("textbox", { name: "搜索关键词" }).fill(q);
  await page.getByRole("button", { name: "搜索资讯", exact: true }).click();
  await page.waitForURL(url => url.searchParams.get("q") === q);
}
try {
  await mkdir(artifacts, { recursive: true });
  for (let i = 0; i < 100; i++) {
    try { if ((await fetch(`${origin}/hot`)).ok) break; } catch {}
    if (i === 99) throw Error(log);
    await new Promise(done => setTimeout(done, 100));
  }
  browser = await chromium.launch({ headless: true });
  const introContext = await browser.newContext({ viewport: { width: 1360, height: 760 }, reducedMotion: "reduce" });
  const introPage = await introContext.newPage();
  homeHeld = true;
  await introPage.goto(origin);
  await introPage.locator('[data-scroll-cue-shell] button:not(:disabled)').click();
  await introPage.locator('[data-navigation-progress][data-visible="true"]').waitFor();
  assert.equal(await introPage.locator('[data-p0-scroller]').getAttribute("aria-busy"), "true");
  homeHeld = false; release("home"); await settled(introPage, "/");
  check("first reduced-motion entry keeps progress visible while the home feed is pending");
  await introContext.close();
  for (const mode of ["desktop", "mobile", "reduced"]) {
    const context = await browser.newContext({ viewport: mode === "mobile" ? { width: 390, height: 844 } : { width: 1360, height: 760 }, reducedMotion: mode === "reduced" ? "reduce" : "no-preference" });
    const page = await context.newPage(); page.on("pageerror", error => errors.push(error.message));
    await page.goto(`${origin}/search`);
    assert.equal(await page.locator("[data-navigation-progress]").count(), 1, "the shared shell must own one top progress line");
    await settled(page, "/search");
    await search(page, `held-${mode}`);
    const bar = page.locator("[data-navigation-progress]");
    await page.waitForFunction(() => document.querySelector('[data-navigation-progress]')?.getAttribute("data-visible") === "true");
    const rect = await bar.boundingBox();
    assert.equal(rect.x, 0); assert.equal(rect.y, 0); assert.equal(rect.height, 2);
    assert.equal(rect.width, mode === "mobile" ? 390 : 1360);
    const visibleLoading = await page.locator('[data-p0-scroller]').evaluate(el => [...el.querySelectorAll('*')].filter(item => item.childElementCount === 0 && /正在(?:载入|读取)/.test(item.textContent) && item.getBoundingClientRect().height > 2));
    assert.equal(visibleLoading.length, 0);
    if (mode === "reduced") assert.equal(await bar.locator("div").evaluate(el => getComputedStyle(el).transitionDuration), "0s");
    await page.screenshot({ path: `${artifacts}/${mode}-loading.png` });
    await menu(page, "/hot"); await settled(page, "/hot", 2000);
    assert.ok(held.has(`held-${mode}`), "the new destination must settle while the old request is still held");
    release(`held-${mode}`);
    await page.waitForTimeout(200);
    assert.equal(new URL(page.url()).pathname, "/hot");
    assert.equal(await bar.getAttribute("data-active"), "false");
    await page.screenshot({ path: `${artifacts}/${mode}-ready.png` });
    check(`${mode}: full-window progress, clean loading, immediate redirect and ignored late response`);
    await context.close();
  }
  const context = await browser.newContext({ viewport: { width: 1360, height: 760 } });
  const page = await context.newPage(); page.on("pageerror", error => errors.push(error.message));
  await page.clock.install();
  await page.goto(`${origin}/hot`); await settled(page, "/hot");
  const staticRefresh = page.waitForResponse(response => new URL(response.url()).pathname === "/hot" && response.request().headers().rsc === "1");
  await menu(page, "/hot"); await staticRefresh; await settled(page, "/hot");
  check("same-URL static page refresh terminates progress without remounting RouteReady");
  const before = counts.get("stats") ?? 0;
  const response = page.waitForResponse(response => response.url().includes("/api/bluepulse/site/stats"));
  await page.locator('aside a[href="/about"]').hover(); await response;
  await menu(page, "/about"); await settled(page, "/about");
  assert.equal(counts.get("stats"), before + 1);
  assert.equal(await page.locator('[data-about-status="ready"]').count(), 1);
  await menu(page, "/hot"); await settled(page, "/hot");
  await page.evaluate(() => {
    window.__progressFlash = false;
    new MutationObserver(() => { if (document.querySelector('[data-navigation-progress]')?.getAttribute("data-visible") === "true") window.__progressFlash = true; }).observe(document.body, { subtree: true, attributes: true });
  });
  await menu(page, "/about"); await settled(page, "/about");
  assert.equal(counts.get("stats"), before + 1);
  assert.equal(await page.evaluate(() => window.__progressFlash), false);
  await menu(page, "/about"); await settled(page, "/about");
  assert.equal(counts.get("stats"), before + 2);
  check("about intent prefetch and revisits share data without a progress flash; same-page activation refreshes");
  await page.reload(); await settled(page, "/about"); assert.equal(counts.get("stats"), before + 3);
  check("document reload does not restore the in-memory about cache");
  await page.goto(`${origin}/hot`); await settled(page, "/hot");
  statsHeld = true;
  const pendingStats = page.waitForResponse(response => response.url().includes("/api/bluepulse/site/stats"));
  const oldStatsCount = counts.get("stats");
  await page.locator('aside a[href="/about"]').hover();
  while (!held.has("stats")) await new Promise(done => setTimeout(done, 10));
  assert.equal(await page.locator('[data-navigation-progress]').getAttribute("data-active"), "false");
  await menu(page, "/about"); await page.locator('[data-navigation-progress][data-visible="true"]').waitFor();
  await menu(page, "/hot"); await settled(page, "/hot");
  statsHeld = false; release("stats"); await pendingStats;
  await menu(page, "/about"); await settled(page, "/about");
  assert.equal(counts.get("stats"), oldStatsCount + 1);
  check("about prefetch stays quiet and survives consumers leaving an in-flight shared request");
  await page.goto(`${origin}/all?q=policy`); await settled(page, "/all");
  policyNoStore = true;
  await page.getByRole("button", { name: "搜索资讯", exact: true }).click(); await settled(page, "/all");
  const policyCount = counts.get("policy");
  await menu(page, "/hot"); await settled(page, "/hot");
  await page.goBack(); await settled(page, "/all");
  assert.equal(counts.get("policy"), policyCount + 1);
  check("a no-store refresh invalidates older cacheable history data");
  await page.goto(`${origin}/all?q=nostore`); await settled(page, "/all");
  const noStoreCount = counts.get("nostore");
  await menu(page, "/hot"); await settled(page, "/hot");
  await page.goBack(); await settled(page, "/all");
  assert.equal(counts.get("nostore"), noStoreCount + 1);
  check("no-store results are rendered but not reused by history");
  await page.goto(`${origin}/all?q=history`); await settled(page, "/all");
  const scroller = page.locator('[data-p0-scroller]');
  await scroller.evaluate(el => { el.scrollTop = 450; }); await page.waitForTimeout(100);
  const savedTop = await scroller.evaluate(el => el.scrollTop), historyCount = counts.get("history");
  await menu(page, "/hot"); await settled(page, "/hot");
  // Advance cache time without freezing GSAP's Date.now-based ticker.
  await page.clock.setSystemTime(new Date(Date.now() + 61_000));
  await page.goBack(); await settled(page, "/all");
  assert.equal(counts.get("history"), historyCount + 1);
  assert.ok(Math.abs(await scroller.evaluate(el => el.scrollTop) - savedTop) < 3);
  check("an expired history feed is revalidated while its 30-minute scroll anchor is restored");
  await page.goto(`${origin}/search?q=fail`); await settled(page, "/search");
  assert.ok(await page.getByRole("alert").count());
  await page.getByRole("button", { name: "重试", exact: true }).click(); await settled(page, "/search");
  assert.equal(await page.locator('[data-navigation-progress]').getAttribute("data-active"), "false");
  check("errors and retries terminate progress");
  await page.goto(`${origin}/articles?q=rsc-refresh`); await settled(page, "/articles");
  legacyHeld = true;
  // Re-submit the same server-rendered URL through the shared navigation capture.
  await page.evaluate(() => {
    const link = document.createElement("a"); link.href = location.pathname + location.search; link.textContent = "重新读取当前文章列表";
    document.querySelector('[data-p0-scroller]').append(link);
  });
  await page.getByRole("link", { name: "重新读取当前文章列表", exact: true }).click();
  await page.locator('[data-navigation-progress][data-visible="true"]').waitFor();
  await menu(page, "/hot"); await settled(page, "/hot", 2000);
  assert.ok(held.has("legacy"));
  legacyHeld = false; release("legacy");
  check("server-rendered refresh shows progress and can be abandoned before its upstream finishes");
  assert.deepEqual(errors, []);
  await writeFile(`${artifacts}/verification.json`, JSON.stringify({ checks, browserErrors: errors }, null, 2));
  await context.close();
} finally {
  for (const key of held.keys()) release(key);
  await browser?.close(); server.kill(); api.closeAllConnections(); await new Promise(done => api.close(done));
}
