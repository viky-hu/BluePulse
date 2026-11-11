// Focused production checks for desktop sidebar scrolling and the separate phone shell.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

const { chromium } = await import(process.env.PULSE_PLAYWRIGHT_MODULE ? pathToFileURL(process.env.PULSE_PLAYWRIGHT_MODULE).href : "playwright");
const origin = "http://127.0.0.1:3110", artifactDir = "test-results/pulse-sidebar/responsive";
const server = spawn(process.execPath, ["node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "3110"], {
  cwd: process.cwd(), env: { ...process.env, BLUEPULSE_API_URL: "http://127.0.0.1:1" }, stdio: ["ignore", "pipe", "pipe"], windowsHide: true,
});
let serverLog = "", browser;
server.stdout.on("data", chunk => { serverLog += chunk; }); server.stderr.on("data", chunk => { serverLog += chunk; });
const checks = [], browserErrors = [];
const check = name => { checks.push(name); console.log(`PASS ${name}`); };
try {
  await mkdir(artifactDir, { recursive: true });
  for (let i = 0; i < 100; i++) {
    try { if ((await fetch(`${origin}/hot`)).ok) break; } catch {}
    if (i === 99) throw Error(serverLog);
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1360, height: 760 } });
  page.on("pageerror", error => browserErrors.push(error.message));
  await page.goto(`${origin}/hot`);
  await page.waitForSelector('[data-entry="stable"] [data-phase="idle"]');
  const sidebar = page.locator('[data-home-sidebar]'), search = sidebar.locator('a[href^="/search"]');
  const header = page.locator('[data-mobile-header]'), tabs = page.locator('[data-mobile-tabs]');
  await page.evaluate(() => { window.__sidebar = document.querySelector('[data-home-sidebar]'); window.__planes = document.querySelector('[data-main-scene]'); });
  await page.setViewportSize({ width: 1360, height: 480 });
  const searchTop = (await search.boundingBox()).y;
  await sidebar.getByRole("link", { name: "反馈", exact: true }).scrollIntoViewIfNeeded();
  assert.ok(await sidebar.locator('nav').evaluate(el => el.scrollTop > 50));
  assert.equal((await search.boundingBox()).y, searchTop);
  assert.equal(await sidebar.evaluate(el => el.scrollHeight <= el.clientHeight + 1 && el.scrollWidth <= el.clientWidth + 1), true);
  await page.screenshot({ path: `${artifactDir}/short-desktop.png` });
  check("short desktop scrolls all groups while wordmark and search stay fixed");
  await search.focus();
  await page.keyboard.press("Tab");
  await page.keyboard.press("Shift+Tab");
  assert.equal(await search.evaluate(el => el === document.activeElement), true);
  assert.equal(await search.evaluate(el => { const s = getComputedStyle(el); return s.outlineStyle === "solid" && s.outlineWidth === "2px"; }), true);
  check("desktop keyboard navigation keeps the visible search focus outline");

  await page.setViewportSize({ width: 390, height: 844 });
  await sidebar.waitFor({ state: "hidden" });
  assert.equal(await sidebar.isVisible(), false);
  assert.equal(await page.locator('button[aria-controls="pulse-main-menu"]').count(), 0);
  await search.evaluate(el => el.focus());
  assert.equal(await search.evaluate(el => el === document.activeElement), false);
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press("Tab");
    assert.equal(await sidebar.evaluate(el => el.contains(document.activeElement)), false);
  }
  assert.equal(await header.isVisible(), true);
  assert.equal(await tabs.isVisible(), true);
  assert.deepEqual(await tabs.locator("a").allTextContents(), ["精选", "全部", "热点", "日报", "更多"]);
  assert.equal(await tabs.locator('a[aria-current="page"]').textContent(), "热点");
  for (const link of await tabs.locator("a").all()) assert.equal(await link.isVisible(), true);
  for (const surface of [header, tabs]) {
    assert.equal(await surface.evaluate(el => el.scrollWidth <= el.clientWidth + 1), true);
  }
  await page.screenshot({ path: `${artifactDir}/phone.png` });
  check("phone replaces the sidebar with one header and five tabs, with hidden sidebar links unfocusable");

  await page.setViewportSize({ width: 768, height: 844 });
  await sidebar.waitFor({ state: "hidden" });
  assert.equal(await sidebar.isVisible(), false);
  assert.equal(await header.isVisible(), true);
  assert.equal(await tabs.isVisible(), true);
  await page.setViewportSize({ width: 769, height: 844 });
  await sidebar.waitFor({ state: "visible" });
  assert.equal(await sidebar.isVisible(), true);
  assert.equal(await header.isVisible(), false);
  assert.equal(await tabs.isVisible(), false);
  await search.focus();
  assert.equal(await search.evaluate(el => el === document.activeElement), true);
  check("768px uses phone navigation and 769px restores the usable desktop sidebar");

  await page.setViewportSize({ width: 1360, height: 760 });
  await sidebar.waitFor({ state: "visible" });
  assert.equal(await sidebar.isVisible(), true);
  assert.equal(await page.evaluate(() => window.__sidebar === document.querySelector('[data-home-sidebar]') && window.__planes === document.querySelector('[data-main-scene]')), true);
  check("breakpoint changes preserve the same sidebar and SVG scene nodes");
  assert.deepEqual(browserErrors, []);
  await writeFile(`${artifactDir}/verification.json`, JSON.stringify({ time: new Date().toISOString(), checks, browserErrors }, null, 2));
} finally { await browser?.close(); server.kill(); }
