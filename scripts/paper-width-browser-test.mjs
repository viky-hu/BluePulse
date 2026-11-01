// Focused production UI checks. Local fixtures only; no ingestion or paid calls.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { MOCK_HOME_FEATURED } from '../src/app/_lib/home-mock.ts';
const { chromium } = await import(pathToFileURL(process.env.PULSE_PLAYWRIGHT_MODULE ?? 'C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs').href);
const port = 3180, origin = `http://127.0.0.1:${port}`, artifacts = 'test-results/paper-width';
const checks = [], errors = [];
const pass = name => { checks.push(name); console.log(`PASS ${name}`); };
const api = createServer((req, res) => { res.writeHead(req.url === '/api/v1/home/featured' ? 200 : 404, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(req.url === '/api/v1/home/featured' ? MOCK_HOME_FEATURED : {})); });
await new Promise(resolve => api.listen(port + 1, '127.0.0.1', resolve));
const server = spawn(process.execPath, ['node_modules/next/dist/bin/next', 'start', '--hostname', '127.0.0.1', '--port', String(port)], { cwd: process.cwd(), env: { ...process.env, BLUEPULSE_API_URL: `http://127.0.0.1:${port + 1}` }, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
let log = '', browser;
server.stdout.on('data', data => { log += data; }); server.stderr.on('data', data => { log += data; });
async function ready(page) { await page.waitForFunction(() => document.querySelector('[data-entry="stable"] [data-phase="idle"]') && document.querySelector('[data-p0-scroller]')?.getAttribute('aria-busy') === 'false'); }
async function bounds(page) {
  return page.evaluate(() => {
    const rect = selector => { const r = document.querySelector(selector).getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height, right: r.right }; };
    const scroller = document.querySelector('[data-p0-scroller]'), style = getComputedStyle(scroller);
    return { paper: rect('[data-main-paper]'), green: rect('[data-main-green]'), frame: rect('[data-p0-content]'), menu: rect('[data-home-sidebar]'), contentWidth: scroller.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight), overflow: scroller.scrollWidth - scroller.clientWidth };
  });
}
try {
  for (let n = 0; n < 100; n++) { try { if ((await fetch(`${origin}/daily`)).ok) break; } catch {} if (n === 99) throw Error(log); await new Promise(resolve => setTimeout(resolve, 100)); }
  await mkdir(artifacts, { recursive: true }); browser = await chromium.launch({ headless: true });
  for (const spec of [{ width: 1440, height: 900 }, { width: 1920, height: 1080 }, { width: 390, height: 844 }, { width: 768, height: 900 }, { width: 769, height: 900 }, { width: 1000, height: 900 }, { width: 1440, height: 900, reducedMotion: 'reduce' }]) {
    const context = await browser.newContext({ viewport: { width: spec.width, height: spec.height }, reducedMotion: spec.reducedMotion ?? 'no-preference' });
    await context.addInitScript(() => { localStorage.setItem('blue-pulse-entry-complete-v1:mock', '1'); });
    const page = await context.newPage(); page.on('pageerror', e => errors.push(e.message));
    const pages = [1440, 1920, 390].includes(spec.width) && !spec.reducedMotion ? ['/', '/all', '/hot', '/starred', '/about', '/changelog', '/feedback', '/search', '/history', '/articles', '/entities', '/daily', '/agent', '/story/demo-event-1'] : ['/hot'];
    for (const path of pages) {
      await page.goto(`${origin}${path}?mock=1`); await ready(page);
      const b = await bounds(page);
      for (const key of ['x', 'y', 'width', 'height']) assert.ok(Math.abs(b.paper[key] - b.frame[key]) < .2, `${path} frame ${key}`);
      assert.ok(b.overflow <= 1, `${spec.width} ${path} overflow ${b.overflow}`);
      if (spec.width <= 768) { assert.ok(Math.abs(b.paper.x - 18) < .2); assert.ok(Math.abs(b.paper.width - (spec.width - 36)) < .2); assert.ok(Math.abs(b.paper.x - b.green.x - 8) < .2); }
      else { assert.ok(b.paper.x - b.menu.right >= 15.8); assert.ok(Math.abs(b.paper.x - b.green.x - spec.width * .025) < .2); assert.ok(Math.abs(b.green.right - b.paper.right - spec.width * .02) < .2); }
      if (path === '/hot') { const want = { 1440: 943.6, 1920: 1291.8, 390: 324 }[spec.width]; if (want) assert.ok(Math.abs(b.contentWidth - want) < 2, `${spec.width} content ${b.contentWidth}`); }
      if (path === '/about') {
        await page.waitForFunction(() => { const c = document.querySelector('[data-signal-river] canvas'); return c && c.width > 0 && c.getContext('2d').getImageData(0, 0, c.width, c.height).data.some((v, i) => i % 4 === 3 && v > 0); });
        await page.waitForTimeout(2200);
      }
      if (['/all', '/hot', '/about'].includes(path) && [1440, 1920, 390].includes(spec.width) && !spec.reducedMotion) { await page.waitForTimeout(250); await page.screenshot({ path: `${artifacts}/${spec.width}-${path.slice(1)}.png` }); }
      pass(`${spec.width}${spec.reducedMotion ? ' reduced' : ''} ${path}: frame, safe edges, no horizontal overflow`);
    }
    await context.close();
  }
  // Capture the last animated SVG frame before unmount, then compare to the stable CSS targets.
  for (const reduced of [false, true]) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: reduced ? 'reduce' : 'no-preference' });
    const page = await context.newPage(); page.on('pageerror', e => errors.push(e.message));
    await page.goto(`${origin}/?mock=1`); await page.locator('[data-scroll-cue-shell] button:not(:disabled)').waitFor({ timeout: 45000 });
    await page.evaluate(() => { window.__lastIntro = null; const tick = () => { const paper = document.querySelector('[data-intro-panel-surface]'), green = document.querySelector('[data-report-green]'); if (!paper || !green) return; const r = e => { const b = e.getBoundingClientRect(); return { x: b.x, y: b.y, width: b.width, height: b.height }; }; window.__lastIntro = { paper: r(paper), green: r(green) }; requestAnimationFrame(tick); }; requestAnimationFrame(tick); });
    await page.locator('[data-scroll-cue-shell] button').click();
    if (!reduced) { await page.waitForTimeout(450); await page.setViewportSize({ width: 1000, height: 800 }); }
    await ready(page); const stable = await bounds(page), last = await page.evaluate(() => window.__lastIntro);
    // Reduced motion updates and unmounts in one task; the normal path supplies an actual last animation frame.
    if (!reduced) for (const part of ['paper', 'green']) for (const key of ['x', 'y', 'width', 'height']) assert.ok(Math.abs(last[part][key] - stable[part][key]) < 2, `${part} ${key} handoff ${JSON.stringify({last,stable})}`);
    assert.equal(await page.locator('[data-intro-panel]').count(), 0); await page.reload(); await ready(page); assert.equal(await page.locator('[data-intro-panel]').count(), 0);
    pass(`${reduced ? 'reduced' : 'resize during transition'}: stable handoff and completed-intro revisit`); await context.close();
  }
  assert.deepEqual(errors, []); await writeFile(`${artifacts}/results.json`, JSON.stringify({ checks, errors }, null, 2)); console.log(`${checks.length} focused checks passed`);
} finally { await browser?.close(); server.kill(); await new Promise(resolve => api.close(resolve)); }
