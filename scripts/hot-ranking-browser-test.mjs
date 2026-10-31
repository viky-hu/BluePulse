// Production Next.js UI + precise proxy against a local deterministic HTTP service.
// No collection, model, notification or real news requests.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import { MOCK_HOT } from "../src/app/hot/_mock.ts";
const { chromium } = await import(pathToFileURL(process.env.PULSE_PLAYWRIGHT_MODULE ?? "C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs").href);
const origin = "http://127.0.0.1:3170", artifacts = "test-results/hot-ranking";
let payload = structuredClone(MOCK_HOT), mode = "ready", policy = "public, max-age=30", age = null, delay = 0, hold = false, release = null;
let browser, serverLog = "";
const requests = [], checks = [], errors = [];
const check = name => { checks.push(name); console.log(`PASS ${name}`); };
const reset = () => { payload = structuredClone(MOCK_HOT); mode = "ready"; policy = "public, max-age=30"; age = null; delay = 0; };
const api = createServer(async (req, res) => {
  requests.push(req.url);
  if (req.url !== "/api/v1/site/hot") { res.writeHead(404, { "Content-Type": "application/json" }); return res.end("{}"); }
  const status = mode === "unavailable" ? 404 : mode === "failure" ? 503 : 200;
  const body = mode === "malformed" ? { entries: [] } : mode === "empty" ? { computedAt: null, windowHours: 48, entries: [] } : structuredClone(payload);
  const headers = { "Content-Type": "application/json", "Cache-Control": policy };
  if (age !== null) headers.Age = String(age);
  if (hold) { hold = false; await new Promise(resolve => { release = resolve; }); }
  if (delay) await new Promise(resolve => setTimeout(resolve, delay));
  res.writeHead(status, headers); res.end(mode === "invalid-json" ? "{invalid" : JSON.stringify(body));
});
await new Promise(resolve => api.listen(3171, "127.0.0.1", resolve));
const server = spawn(process.execPath, ["node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "3170"], { cwd: process.cwd(), env: { ...process.env, BLUEPULSE_API_URL: "http://127.0.0.1:3171" }, stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
server.stdout.on("data", d => { serverLog += d; }); server.stderr.on("data", d => { serverLog += d; });
const count = () => requests.filter(r => r === "/api/v1/site/hot").length;
const paper = page => page.locator("[data-p0-scroller]");
const cards = page => page.locator("[data-hot-card]");
const lead = page => page.locator('[data-hot-card="lead"]');
async function ready(page, path = "/hot") { await page.waitForFunction(path => location.pathname === path && document.querySelector('[data-entry="stable"] [data-phase="idle"]') && document.querySelector('[data-p0-scroller]')?.getAttribute("aria-busy") === "false" && (path !== "/hot" || document.querySelector('[data-hot-status]')?.getAttribute("data-hot-status") !== "loading"), path); }
async function goto(page, path = "/hot") { await page.goto(`${origin}${path}`); await ready(page, path.split(/[?#]/)[0]); }
async function menu(page, href) {
  const toggle = page.getByRole("button", { name: "打开菜单", exact: true }); if (await toggle.isVisible()) await toggle.click();
  await page.locator(`aside a[href="${href}"]`).last().click(); await ready(page, href);
}
try {
  await mkdir(artifacts, { recursive: true });
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`${origin}/hot`)).ok) break; } catch {} if (i === 99) throw Error(serverLog); await new Promise(resolve => setTimeout(resolve, 100)); }
  browser = await chromium.launch({ headless: true });
  for (const spec of [{ name: "desktop", viewport: { width: 1360, height: 760 }, reducedMotion: "no-preference" }, { name: "mobile", viewport: { width: 390, height: 844 }, reducedMotion: "no-preference" }, { name: "reduced", viewport: { width: 1360, height: 760 }, reducedMotion: "reduce" }]) {
    if (process.env.PULSE_HOT_CASE && process.env.PULSE_HOT_CASE !== spec.name) continue;
    reset();
    payload.entries[0].participants[0].iconUrl = "/hot-fixture-icon.svg";
    payload.entries[0].participants[1].iconUrl = "/hot-fixture-missing.svg";
    const context = await browser.newContext({ viewport: spec.viewport, reducedMotion: spec.reducedMotion, isMobile: spec.name === "mobile", hasTouch: spec.name === "mobile" });
    await context.addInitScript(() => { localStorage.setItem("blue-pulse-entry-complete-v1", "1"); localStorage.setItem("blue-pulse-entry-complete-v1:mock", "1"); });
    await context.route("**/hot-fixture-*.svg", route => route.fulfill({ status: route.request().url().includes("missing") ? 404 : 200, contentType: "image/svg+xml", body: route.request().url().includes("missing") ? "invalid image" : '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="500"><rect width="800" height="500" fill="#a4d7c7"/><path d="M0 400L300 100L500 320L800 50V500H0Z" fill="#176b75"/></svg>' }));
    const page = await context.newPage(); page.on("pageerror", error => errors.push(`${spec.name}: ${error.message}`));
    await goto(page);
    assert.equal(await cards(page).count(), 10); assert.equal(await page.locator('[data-hot-card="runner"]').count(), 2); assert.equal(await page.locator('[data-hot-card="row"]').count(), 7);
    assert.equal(await lead(page).locator("[data-heat-panel]").count(), 1);
    assert.equal(await page.getByRole("heading", { name: "热点榜", exact: true, level: 1 }).count(), 1);
    assert.equal(await paper(page).evaluate(el => el.scrollWidth <= el.clientWidth + 1), true);
    const leadChildren = await lead(page).locator(':scope > div').evaluateAll(els => els.map(el => ({ width: el.getBoundingClientRect().width, scroll: el.scrollWidth })));
    assert.equal(leadChildren.every(e => e.scroll <= e.width + 1), true, JSON.stringify(leadChildren));
    check(`${spec.name}: original lead/runners/rows, heat panel and no paper overflow`);
    await page.screenshot({ path: `${artifacts}/${spec.name}.png`, fullPage: true });
    const faces = lead(page).getByRole("button", { name: "11 位参与者，查看名单" });
    await faces.locator('img[src*="missing"]').waitFor({ state: "detached" });
    assert.equal(await faces.locator('img').count(), 1); assert.equal(await faces.getByText("+5", { exact: true }).count(), 1);
    await faces.click(); const popup = page.getByRole("dialog", { name: "参与讨论的来源" }); await popup.waitFor();
    assert.ok(await popup.getByText("精选组", { exact: true }).isVisible()); assert.ok(await popup.getByText("氛围组", { exact: true }).isVisible()); assert.ok(await popup.getByText("另有 3 位未列出", { exact: true }).isVisible());
    assert.equal(await popup.evaluate(el => el.parentElement === document.body), true);
    await page.keyboard.press("Escape"); await popup.waitFor({ state: "hidden" });
    await faces.click(); await paper(page).evaluate(el => { el.scrollTop += 80; }); await popup.waitFor({ state: "hidden" });
    check(`${spec.name}: six faces, image failure initial, +N, portal names, Escape and internal-scroll close`);
    await paper(page).evaluate(el => { el.scrollTop = el.scrollHeight; });
    const method = page.locator("#hot-method"); await method.locator("summary").click(); assert.equal(await method.getAttribute("open"), "");
    await method.getByText("讨论快速增加", { exact: true }).waitFor({ state: "visible" });
    assert.ok(await method.getByText("讨论快速增加", { exact: true }).isVisible());
    await method.locator("summary").click(); assert.equal(await method.getAttribute("open"), null);
    check(`${spec.name}: original method disclosure and badge explanations`);
    if (spec.name === "mobile") {
      await paper(page).evaluate(el => { el.scrollTop = 0; });
      for (let i = 0; i < 20; i++) {
        const titleGone = await page.locator('[data-page-title]').evaluate(el => el.getBoundingClientRect().bottom < document.querySelector('header[class*="phoneBar"]').getBoundingClientRect().bottom);
        if (titleGone) break;
        await paper(page).evaluate(el => { el.scrollTop += 20; });
      }
      await page.waitForFunction(() => document.querySelector('[class*="phoneTitle"]')?.getAttribute("data-shown") === "true");
      assert.ok(await page.locator('[data-page-title] + div').evaluate(el => el.getBoundingClientRect().bottom > document.querySelector('header[class*="phoneBar"]').getBoundingClientRect().bottom));
      await page.getByRole("button", { name: "怎么算", exact: true }).click();
      assert.equal(await method.getAttribute("open"), ""); await page.waitForTimeout(650);
      assert.ok(await paper(page).evaluate(el => el.scrollTop > 300));
      const bar = page.locator('[class*="phoneBarGrid"]');
      assert.ok(await bar.isVisible());
      check("mobile: sticky PhoneBar and method action target the paper scroller");
    }
    if (spec.name === "reduced") {
      assert.equal(await page.locator('[class*="live"] i').evaluate(el => getComputedStyle(el).animationName), "none");
      check("reduced: static live marker retains reading and controls");
    }
    await goto(page, "/hot?mock=1"); assert.ok(await page.getByRole("heading", { level: 1, name: "热点榜（演示）", exact: true }).isVisible()); assert.equal(await cards(page).count(), 10);
    check(`${spec.name}: explicit police demo uses the original title without extra explanation rows`);
    if (spec.name === "desktop") {
      reset();
      for (const n of [0, 1, 2, 3]) {
        payload.entries = structuredClone(MOCK_HOT.entries.slice(0, n)); await goto(page);
        assert.equal(await cards(page).count(), n); assert.equal(await page.locator('[aria-label="其余热点"]').count(), 0);
        if (n === 0) assert.ok(await page.getByText("暂时没有热点", { exact: true }).isVisible());
      }
      payload.entries = structuredClone(MOCK_HOT.entries.slice(1, 5)); await goto(page);
      assert.equal(await lead(page).locator('[data-rank]').textContent(), "NO.02"); assert.ok(await page.getByText("No.05–05", { exact: true }).isVisible());
      check("desktop: zero/one/two/three entries and original rank gaps are not padded or renumbered");
      reset(); payload.entries[0].cover = { url: "/hot-fixture-cover.svg", srcSet: "/hot-fixture-cover.svg 800w", width: 800, height: 500 }; await goto(page);
      assert.equal(await lead(page).locator("[data-heat-panel]").count(), 0); assert.equal(await lead(page).locator("img[fetchpriority=high]").count(), 1); assert.equal(await lead(page).getByRole("img", { name: /近 24 小时/ }).count(), 1);
      await page.screenshot({ path: `${artifacts}/cover.png` });
      payload.entries[0].cover = null; payload.entries[0].spark = [null, 8, null, 10, null]; await goto(page);
      assert.equal(await lead(page).locator("[data-heat-panel]").count(), 0); assert.equal(await lead(page).getByRole("img", { name: /近 24 小时/ }).count(), 0);
      check("desktop: licensed-cover/compact-curve and insufficient-data source branches");
      reset(); await goto(page);
      assert.equal(await page.locator('[data-hot-card="runner"]').nth(1).locator('svg[role="img"] path[fill="none"]').count(), 2);
      for (const text of ["爆", "新", "发酵中", "新上榜", "持平", "暂不比较"]) assert.ok(await page.getByText(text, { exact: true }).first().count());
      const ids = await page.locator('linearGradient').evaluateAll(els => els.map(el => el.id)); assert.equal(new Set(ids).size, ids.length);
      check("desktop: all badges/trends and broken observed runs retain unique SVG gradients");
      const last = cards(page).last(); await last.scrollIntoViewIfNeeded(); const top = await paper(page).evaluate(el => el.scrollTop);
      await last.getByRole("link").click(); await ready(page, "/story/demo-event-10"); assert.ok(await page.getByText("事件详情正在建设中", { exact: false }).isVisible());
      await page.goBack(); await ready(page); assert.ok(Math.abs(await paper(page).evaluate(el => el.scrollTop) - top) < 3);
      const previousRequests = count(); await page.reload(); await ready(page); assert.ok(count() > previousRequests);
      check("desktop: story destination, history anchor and reload revalidation");
      for (const [state, expected] of [["unavailable", "unavailable"], ["failure", "error"], ["malformed", "error"], ["invalid-json", "error"]]) {
        mode = state; await goto(page); assert.equal(await page.locator('[data-hot-status]').getAttribute("data-hot-status"), expected); assert.equal(await cards(page).count(), 0);
        assert.equal(await page.getByText("Unexpected token", { exact: false }).count(), 0);
      }
      reset(); await page.getByRole("button", { name: "重试", exact: true }).click(); await ready(page); assert.equal(await cards(page).count(), 10);
      check("desktop: absent API/failure/malformed are distinct from empty and retry calls real service");
      assert.equal((await page.request.get(`${origin}/api/bluepulse/site/hot/extra`)).status(), 404);
      assert.equal((await page.request.get(`${origin}/api/bluepulse/site/hot`)).headers()["cache-control"], "public, max-age=30");
      check("desktop: precise hot-only proxy and upstream cache headers");
      await goto(page, "/daily"); const before = count(); await page.locator('aside a[href="/hot"]').hover(); await page.waitForTimeout(350); assert.equal(count(), before + 1); await menu(page, "/hot"); assert.equal(count(), before + 1);
      await menu(page, "/daily"); await menu(page, "/hot"); assert.equal(count(), before + 1);
      await menu(page, "/hot"); assert.equal(count(), before + 2);
      check("desktop: intent prefetch and navigation share cache, current menu forces refresh");
      policy = "no-store"; await goto(page); const noStoreBefore = count(); await menu(page, "/daily"); await page.goBack(); await ready(page); assert.ok(count() > noStoreBefore);
      policy = "public, max-age=30"; age = 29; await goto(page); await menu(page, "/daily"); const agedBefore = count(); await page.waitForTimeout(1200); await page.goBack(); await ready(page); assert.ok(count() > agedBefore); age = null;
      check("desktop: no-store and consumed upstream age cannot revive expired history data");
      await goto(page, "/daily"); hold = true; const slowBefore = count(); const anchor = page.locator('aside a[href="/hot"]'); await anchor.click();
      await page.waitForFunction(() => location.pathname === "/hot");
      for (let i = 0; i < 50 && count() === slowBefore; i++) await page.waitForTimeout(20);
      await page.waitForTimeout(200); await menu(page, "/daily"); release?.(); release = null; await page.waitForTimeout(150);
      assert.equal(new URL(page.url()).pathname, "/daily"); assert.equal(await cards(page).count(), 0);
      check("desktop: a held hot response cannot overwrite replacement navigation");
      delay = 6500; await goto(page); assert.equal(await page.locator('[data-hot-status]').getAttribute("data-hot-status"), "error"); delay = 0;
      check("desktop: real proxy timeout is an error, never a fabricated empty ranking");
    }
    await context.close();
  }
  assert.deepEqual(errors, []); await writeFile(`${artifacts}/verification.json`, JSON.stringify({ checks, errors, requests }, null, 2)); console.log(`${checks.length} hot ranking browser checks passed`);
} catch (error) {
  const page = browser?.contexts()[0]?.pages()[0];
  const state = page ? await page.evaluate(() => ({ url: location.href, body: document.body.innerText, phase: document.querySelector('[data-phase]')?.getAttribute("data-phase"), busy: document.querySelector('[data-p0-scroller]')?.getAttribute("aria-busy"), layout: [...document.querySelectorAll('[data-hot-card="lead"] *')].filter(el => el.scrollWidth > el.getBoundingClientRect().width + 1).map(el => ({ tag: el.tagName, class: el.className.baseVal ?? el.className, width: el.getBoundingClientRect().width, scroll: el.scrollWidth, minWidth: getComputedStyle(el).minWidth, grid: getComputedStyle(el).gridTemplateColumns, box: getComputedStyle(el).boxSizing })) })).catch(() => null) : null;
  await page?.screenshot({ path: `${artifacts}/failure.png` }).catch(() => {});
  await writeFile(`${artifacts}/failure.json`, JSON.stringify({ checks, errors, requests, serverLog, failure: String(error), stack: error.stack, state }, null, 2)); throw error;
} finally { release?.(); await browser?.close(); server.kill(); await new Promise(resolve => api.close(resolve)); }
