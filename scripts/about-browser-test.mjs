import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdir, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import { layout } from "../src/app/about/_river-drawing.ts";

const { chromium } = await import(process.env.PULSE_PLAYWRIGHT_MODULE ? pathToFileURL(process.env.PULSE_PLAYWRIGHT_MODULE).href : "playwright");
const origin = "http://127.0.0.1:3120", artifacts = "test-results/pulse-about";
const articleId = "4ed2a8d4-efb7-4ce6-8a43-4ee36f27d001";
const complete = {
  sources: 2, sourceKinds: { rss: 1, web_list: 1 }, items: 146, selected: 12, dailies: 3,
  day: { collected: 7, selected: 2 },
  sampleSources: [{ name: "公开信源甲", kind: "rss", heatOnly: false }, { name: "公开信源乙", kind: "web_list", heatOnly: false }],
  latest: [{ id: articleId, title: "真实接口契约测试标题", source: "公开信源甲" }],
};
let mode = "complete", delay = 0, browser, serviceLog = "";
const requests = [], checks = [], browserErrors = [];
const api = createServer(async (req, res) => {
  requests.push(req.url);
  res.setHeader("Content-Type", "application/json");
  if (req.url === "/api/v1/site/stats") {
    const responseMode = mode;
    if (delay) await new Promise(resolve => setTimeout(resolve, delay));
    if (responseMode === "missing" || responseMode === "error") {
      res.statusCode = responseMode === "missing" ? 404 : 503;
      res.end(JSON.stringify({ error: { code: "unavailable" } })); return;
    }
    const data = responseMode === "empty" ? { ...complete, sources: 0, items: 0, selected: 0, dailies: 0, sourceKinds: {}, day: { collected: 0, selected: 0 }, sampleSources: [], latest: [] }
      : responseMode === "partial" ? { ...complete, dailies: null, day: { collected: 7, selected: null } }
      : responseMode === "invalid" ? { ...complete, sources: -1 } : complete;
    res.end(JSON.stringify(data)); return;
  }
  if (req.url === "/api/v1/taxonomy" || req.url === "/api/v1/sources") { res.end('{"items":[]}'); return; }
  res.statusCode = 404; res.end('{"error":{"code":"not_found"}}');
});
await new Promise(resolve => api.listen(3121, "127.0.0.1", resolve));
const server = spawn(process.execPath, ["node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "3120"], {
  cwd: process.cwd(), env: { ...process.env, BLUEPULSE_API_URL: "http://127.0.0.1:3121" }, stdio: ["ignore", "pipe", "pipe"], windowsHide: true,
});
server.stdout.on("data", chunk => { serviceLog += chunk; }); server.stderr.on("data", chunk => { serviceLog += chunk; });
const check = name => { checks.push(name); console.log(`PASS ${name}`); };
const settled = async (page, path = "/about") => {
  await page.waitForFunction(path => location.pathname === path && document.querySelector('[data-entry="stable"] [data-phase="idle"]'), path);
};
const liveReady = async page => { await page.locator('[data-about-status="ready"]').waitFor(); await settled(page); };
const scroller = page => page.locator("[data-p0-scroller]");
const fit = async page => {
  assert.equal(await scroller(page).evaluate(el => el.scrollWidth <= el.clientWidth + 1), true, "paper must have no horizontal overflow");
};
const modelFor = async (page, n) => {
  const geometry = await page.locator("[data-signal-river]").evaluate(el => ({ w: el.clientWidth, h: el.clientHeight }));
  return layout(geometry.w, geometry.h, Array.from({ length: n }, () => ({ name: "sample", kind: "rss", heatOnly: false })));
};
const moveTo = async (page, x, y) => {
  const box = await page.locator("[data-signal-river]").boundingBox();
  await page.mouse.move(box.x + x, box.y + y);
};
try {
  await mkdir(artifacts, { recursive: true });
  for (let i = 0; i < 100; i++) {
    try { if ((await fetch(`${origin}/about?mock=1`)).ok) break; } catch {}
    if (i === 99) throw Error(serviceLog);
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1360, height: 760 } });
  // Instrument painting in the test environment, without production debug APIs.
  await context.addInitScript(() => {
    const paint = CanvasRenderingContext2D.prototype.drawImage;
    const rect = CanvasRenderingContext2D.prototype.rect;
    CanvasRenderingContext2D.prototype.rect = function (...args) {
      if (this.canvas.closest?.("[data-signal-river]")) this.canvas.__revealClips = (this.canvas.__revealClips ?? 0) + 1;
      return Reflect.apply(rect, this, args);
    };
    CanvasRenderingContext2D.prototype.drawImage = function (...args) {
      if (this.canvas.closest?.("[data-signal-river]")) this.canvas.__paintCount = (this.canvas.__paintCount ?? 0) + 1;
      return Reflect.apply(paint, this, args);
    };
  });
  const page = await context.newPage();
  page.on("pageerror", error => browserErrors.push(error.message));

  // Restoration regression: stats grow the page after the historical scroll is applied.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${origin}/about`); await liveReady(page);
  await scroller(page).evaluate(el => { el.scrollTop = el.scrollHeight; });
  await page.getByRole("button", { name: "打开菜单", exact: true }).click();
  const savedTop = await scroller(page).evaluate(el => el.scrollTop);
  await page.locator('[data-home-sidebar] a[href="/changelog"]').click(); await settled(page, "/changelog");
  delay = 700;
  await page.goBack(); await liveReady(page);
  const restoredTop = await scroller(page).evaluate(el => el.scrollTop);
  assert.ok(Math.abs(restoredTop - savedTop) <= 3, `history must restore the populated page: saved=${savedTop}, actual=${restoredTop}`);
  delay = 0;
  check("delayed live statistics settle before restoring the saved paper scroll");

  await page.setViewportSize({ width: 1360, height: 760 });
  const beforeMock = requests.filter(url => url === "/api/v1/site/stats").length;
  await page.goto(`${origin}/about?mock=1`); await settled(page);
  await page.locator('[data-about-status="mock"]').waitFor();
  assert.equal(requests.filter(url => url === "/api/v1/site/stats").length, beforeMock);
  assert.equal(await page.locator("[data-about-figure]").count(), 4);
  assert.equal(await page.locator("h1").evaluate(el => getComputedStyle(el).fontWeight), "700");
  assert.ok(await page.locator("h1").evaluate(el => parseFloat(getComputedStyle(el).fontSize) < 40));
  check("explicit mock is isolated, shows figures and applies smaller bold display type");
  await page.waitForTimeout(2000);
  await fit(page);
  await page.screenshot({ path: `${artifacts}/desktop.png` });
  const diagram = page.locator("[data-signal-river]");
  await diagram.scrollIntoViewIfNeeded();
  const model = await modelFor(page, 100);
  const x = Math.round(model.w * .12 / 3) * 3;
  await moveTo(page, x, model.strands[0].ys[x / 3]);
  const tip = page.locator("[data-river-tooltip]");
  await tip.waitFor({ state: "visible" });
  assert.match(await tip.textContent(), /演示/);
  await moveTo(page, model.w * .55, model.bundles[0].y);
  assert.match(await tip.textContent(), /同一件事/);
  await moveTo(page, model.paper.x + model.paper.w / 2, model.paper.y + model.paper.h / 2);
  assert.match(await tip.textContent(), /警务科技日报/);
  const tipBox = await tip.boundingBox(), riverBox = await diagram.boundingBox();
  assert.ok(tipBox.x >= riverBox.x && tipBox.x + tipBox.width <= riverBox.x + riverBox.width + 1);
  assert.ok(tipBox.y + tipBox.height <= riverBox.y + riverBox.height + 1);
  check("source, bundle and paper hover labels are real and constrained to the diagram");
  await page.screenshot({ path: `${artifacts}/desktop-river.png` });

  for (let i = 0; i < 4; i++) {
    const stage = page.locator(`[data-about-stage="${i}"]`);
    await stage.focus();
    assert.equal(await stage.getAttribute("data-focused"), "true");
  }
  check("each stage supports keyboard focus and its corresponding highlight");
  await diagram.scrollIntoViewIfNeeded();
  await page.mouse.move(10, 10);
  const latest = page.locator("[data-about-latest]:visible");
  const firstTitle = await latest.textContent();
  await page.waitForFunction(first => [...document.querySelectorAll("[data-about-latest]")].some(el => el.getClientRects().length && el.textContent !== first), firstTitle, { timeout: 22000 });
  const changedAt = Date.now(), secondTitle = await latest.textContent();
  await page.waitForTimeout(1400);
  assert.equal(await latest.textContent(), secondTitle, "arrival titles must not cycle rapidly");
  assert.ok(Date.now() - changedAt >= 1400);
  check("travelling pulses reach the paper and rotate the real latest article without rapid cycling");

  const clips = await page.locator("[data-signal-river] canvas").evaluate(el => el.__revealClips ?? 0);
  await page.setViewportSize({ width: 1320, height: 760 });
  await page.waitForTimeout(150);
  assert.equal(await page.locator("[data-signal-river] canvas").evaluate(el => el.__revealClips ?? 0), clips);
  await page.setViewportSize({ width: 1360, height: 760 });
  check("resizing the paper does not replay the completed river reveal");
  await page.evaluate(() => { Object.defineProperty(document, "hidden", { configurable: true, value: true }); document.dispatchEvent(new Event("visibilitychange")); });
  const hiddenCount = await page.locator("[data-signal-river] canvas").evaluate(el => el.__paintCount ?? 0);
  await page.waitForTimeout(200);
  assert.equal(await page.locator("[data-signal-river] canvas").evaluate(el => el.__paintCount ?? 0), hiddenCount);
  await page.evaluate(() => { delete document.hidden; document.dispatchEvent(new Event("visibilitychange")); });
  check("document visibility changes pause the animation scheduler");

  await page.evaluate(() => { window.__departedRiver = document.querySelector("[data-signal-river] canvas"); });
  await page.getByRole("link", { name: "看今天的精选", exact: false }).click(); await settled(page, "/");
  assert.match(page.url(), /mock=1/);
  const unmountedCount = await page.evaluate(() => window.__departedRiver.__paintCount ?? 0);
  await page.waitForTimeout(200);
  assert.equal(await page.evaluate(() => window.__departedRiver.__paintCount ?? 0), unmountedCount);
  check("leaving about stops painting its detached canvas");
  await page.goBack(); await settled(page);
  await page.getByRole("link", { name: "读最新日报", exact: true }).click(); await settled(page, "/daily");
  assert.match(page.url(), /mock=1/);
  await page.goBack(); await settled(page);
  await page.goForward(); await settled(page, "/daily");
  await page.goBack(); await settled(page);
  const articleLink = page.locator("[data-about-latest]:visible");
  const articleHref = await articleLink.getAttribute("href");
  assert.match(articleHref, /^\/articles\/[0-9a-f-]+\?mock=1$/);
  await articleLink.click(); await settled(page, new URL(articleHref, origin).pathname);
  assert.ok(await page.locator("h1").textContent());
  await page.goBack(); await settled(page);
  await page.reload(); await settled(page);
  check("featured, daily and mock article links keep query state; Back and refresh remain usable");

  await page.getByRole("heading", { name: "如果觉得有点用，欢迎加入", exact: true }).scrollIntoViewIfNeeded();
  const qrImages = page.locator('img[src^="/contact/"]');
  assert.equal(await qrImages.count(), 2);
  await qrImages.evaluateAll(images => Promise.all(images.map(img => img.decode())));
  const ink = await qrImages.evaluateAll(images => images.map((img, i) => {
    const bounds = img.getBoundingClientRect();
    return bounds.width * (i === 0 ? 878 / 1046 : 633 / 804);
  }));
  assert.ok(Math.abs(ink[0] - ink[1]) < 1, `visible QR ink must match: ${ink}`);
  assert.equal(await page.locator("#about-maker").evaluate(el => getComputedStyle(el).fontWeight), "700");
  await page.screenshot({ path: `${artifacts}/desktop-maker.png` });
  check("transparent QR originals load with matched visual code sizes and bold team greeting");

  // When the river is clipped by p0, its own canvas must stop painting.
  await page.waitForTimeout(180);
  const count = await page.locator("[data-signal-river] canvas").evaluate(el => el.__paintCount ?? 0);
  await page.waitForTimeout(200);
  assert.equal(await page.locator("[data-signal-river] canvas").evaluate(el => el.__paintCount ?? 0), count);
  check("internal paper scrolling pauses an offscreen canvas");

  await page.setViewportSize({ width: 390, height: 844 });
  await scroller(page).evaluate(el => { el.scrollTop = 0; });
  await fit(page); await page.screenshot({ path: `${artifacts}/mobile.png` });
  await diagram.scrollIntoViewIfNeeded();
  await page.waitForTimeout(150);
  await page.screenshot({ path: `${artifacts}/mobile-river.png` });
  const narrow = await modelFor(page, 100);
  await moveTo(page, narrow.paper.x + narrow.paper.w / 2, narrow.paper.y + narrow.paper.h / 2);
  const mobileTip = await tip.boundingBox(), mobileRiver = await diagram.boundingBox();
  assert.ok(mobileTip.x >= mobileRiver.x && mobileTip.x + mobileTip.width <= mobileRiver.x + mobileRiver.width + 1);
  await page.getByRole("heading", { name: "如果觉得有点用，欢迎加入", exact: true }).scrollIntoViewIfNeeded();
  await fit(page); await page.screenshot({ path: `${artifacts}/mobile-maker.png` });
  await page.getByRole("img", { name: "网站负责人的微信二维码", exact: true }).scrollIntoViewIfNeeded();
  await fit(page); await page.screenshot({ path: `${artifacts}/mobile-wechat.png` });
  check("narrow mobile paper keeps full diagram, tooltips, stage text and uncropped QR codes");

  await page.setViewportSize({ width: 1360, height: 760 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await diagram.scrollIntoViewIfNeeded();
  await page.waitForTimeout(150);
  const stillCount = await page.locator("[data-signal-river] canvas").evaluate(el => el.__paintCount ?? 0);
  await page.waitForTimeout(250);
  assert.equal(await page.locator("[data-signal-river] canvas").evaluate(el => el.__paintCount ?? 0), stillCount);
  const stillModel = await modelFor(page, 100);
  await moveTo(page, stillModel.paper.x + 4, stillModel.paper.y + 4);
  assert.match(await tip.textContent(), /日报/);
  await page.screenshot({ path: `${artifacts}/reduced-motion.png` });
  check("reduced motion draws a coherent still river and keeps hover usable");
  await page.emulateMedia({ reducedMotion: "no-preference" });

  for (const state of ["complete", "partial", "empty", "missing", "error", "invalid"]) {
    mode = state;
    await page.goto(`${origin}/about`);
    const expected = state === "missing" ? "missing" : state === "error" || state === "invalid" ? "error" : "ready";
    await page.locator(`[data-about-status="${expected}"]`).waitFor(); await settled(page);
    assert.equal(await page.getByText("演示数据 · 仅用于流程交互预览", { exact: true }).count(), 0);
    assert.equal(await page.locator("[data-about-figure]").count(), expected !== "ready" ? 0 : state === "partial" ? 3 : 4);
    if (state === "empty") assert.equal(await page.locator("[data-about-latest]").count(), 0);
    if (expected === "error") {
      mode = "complete";
      await page.getByRole("button", { name: "重新读取", exact: true }).click(); await liveReady(page);
    }
    check(`live ${state} response displays its real state and never falls back to mock`);
  }
  const beforeUnknown = requests.length;
  assert.equal((await page.request.get(`${origin}/api/bluepulse/site/stats/extra`)).status(), 404);
  assert.equal((await page.request.get(`${origin}/api/bluepulse/site/contact`)).status(), 404);
  assert.equal(requests.length, beforeUnknown);
  check("proxy adds only the exact public stats path");
  assert.deepEqual(browserErrors, []);
  await writeFile(`${artifacts}/verification.json`, JSON.stringify({ date: new Date().toISOString(), checks, browserErrors }, null, 2));
} finally {
  await browser?.close(); server.kill();
  api.closeAllConnections(); await new Promise(resolve => api.close(resolve));
}
