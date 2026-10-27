// Focused checks for the sidebar's scroll boundary and mobile/desktop activation.
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
  const sidebar = page.locator('[data-home-sidebar]'), search = sidebar.getByRole("link", { name: "搜索", exact: true });
  await page.evaluate(() => { window.__sidebar = document.querySelector('[data-home-sidebar]'); window.__planes = document.querySelector('[data-main-scene]'); });
  await page.setViewportSize({ width: 1360, height: 480 });
  const searchTop = (await search.boundingBox()).y;
  await sidebar.getByRole("link", { name: "反馈", exact: true }).scrollIntoViewIfNeeded();
  assert.ok(await sidebar.locator('nav').evaluate(el => el.scrollTop > 50));
  assert.equal((await search.boundingBox()).y, searchTop);
  assert.equal(await sidebar.evaluate(el => el.scrollHeight <= el.clientHeight + 1 && el.scrollWidth <= el.clientWidth + 1), true);
  await page.screenshot({ path: `${artifactDir}/short-desktop.png` });
  check("short desktop scrolls all groups while wordmark and search stay fixed");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForFunction(() => document.querySelector('[data-home-sidebar]')?.inert === true);
  assert.equal(await sidebar.isVisible(), false);
  await page.getByRole("button", { name: "打开菜单", exact: true }).click();
  await page.waitForFunction(() => document.querySelector('[data-home-sidebar]')?.inert === false);
  assert.equal(await sidebar.isVisible(), true);
  check("desktop-to-mobile with closed menu removes hidden links from focus");
  for (let i = 0; i < 5; i++) {
    await page.keyboard.press("Tab");
    if (await search.evaluate(el => el === document.activeElement)) break;
  }
  assert.equal(await search.evaluate(el => el === document.activeElement), true);
  assert.equal(await search.evaluate(el => { const s = getComputedStyle(el); return s.outlineStyle === "solid" && s.outlineWidth === "2px"; }), true);
  check("keyboard navigation has a visible focus outline");
  await page.setViewportSize({ width: 1360, height: 760 });
  assert.equal(await sidebar.isVisible(), true); assert.equal(await sidebar.getAttribute("inert"), null);
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await sidebar.isVisible(), true); assert.equal(await sidebar.getAttribute("inert"), null);
  await page.keyboard.press("Escape");
  assert.equal(await sidebar.isVisible(), false); assert.equal(await sidebar.getAttribute("inert"), "");
  assert.equal(await page.getByRole("button", { name: "打开菜单", exact: true }).evaluate(el => el === document.activeElement), true);
  check("open menu survives breakpoint changes and Escape returns focus");
  await page.setViewportSize({ width: 1360, height: 760 });
  await page.waitForFunction(() => document.querySelector('[data-home-sidebar]')?.inert === false);
  assert.equal(await sidebar.isVisible(), true);
  assert.equal(await page.evaluate(() => window.__sidebar === document.querySelector('[data-home-sidebar]') && window.__planes === document.querySelector('[data-main-scene]')), true);
  check("closed mobile menu becomes usable desktop menu without rebuilding the scene");
  assert.deepEqual(browserErrors, []);
  await writeFile(`${artifactDir}/verification.json`, JSON.stringify({ time: new Date().toISOString(), checks, browserErrors }, null, 2));
} finally { await browser?.close(); server.kill(); }
