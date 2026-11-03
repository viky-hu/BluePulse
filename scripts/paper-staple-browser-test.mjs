// Focused production checks for the persistent p0 corner mark; local fixtures only.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { MOCK_HOME_FEATURED } from '../src/app/_lib/home-mock.ts';

const { chromium } = await import(pathToFileURL(process.env.PULSE_PLAYWRIGHT_MODULE ?? 'C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs').href);
const port = Number(process.env.PULSE_TEST_PORT ?? 3192), origin = `http://127.0.0.1:${port}`;
const artifacts = 'test-results/paper-staple', checks = [], errors = [];
const pass = name => { checks.push(name); console.log(`PASS ${name}`); };
const api = createServer((req, res) => {
  res.writeHead(req.url === '/api/v1/home/featured' ? 200 : 404, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(req.url === '/api/v1/home/featured' ? MOCK_HOME_FEATURED : {}));
});
await new Promise(resolve => api.listen(port + 1, '127.0.0.1', resolve));
const server = spawn(process.execPath, ['node_modules/next/dist/bin/next', 'start', '--hostname', '127.0.0.1', '--port', String(port)], {
  cwd: process.cwd(), env: { ...process.env, BLUEPULSE_API_URL: `http://127.0.0.1:${port + 1}` },
  windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
});
let log = '', browser;
server.stdout.on('data', data => { log += data; }); server.stderr.on('data', data => { log += data; });
async function ready(page) {
  await page.waitForFunction(() => document.querySelector('[data-entry="stable"] [data-phase="idle"]') && document.querySelector('[data-p0-scroller]')?.getAttribute('aria-busy') === 'false');
}
async function mark(page) {
  assert.equal(await page.locator('[data-main-paper-staple] line').count(), 1, 'main paper must keep exactly one corner line');
  return page.evaluate(() => {
    const line = document.querySelector('[data-main-paper-staple] line'), style = getComputedStyle(line);
    const point = (x, y) => { const p = new DOMPoint(x, y).matrixTransform(line.getScreenCTM()); return { x: p.x, y: p.y }; };
    const paper = document.querySelector('[data-main-paper]').getBoundingClientRect();
    return { a: point(line.x1.baseVal.value, line.y1.baseVal.value), b: point(line.x2.baseVal.value, line.y2.baseVal.value),
      paper: { x: paper.x, y: paper.y }, stroke: style.stroke, width: style.strokeWidth,
      visible: line.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }), pointerEvents: style.pointerEvents };
  });
}
function sameLine(a, b, tolerance = .2) {
  for (const end of ['a', 'b']) for (const axis of ['x', 'y']) assert.ok(Math.abs(a[end][axis] - b[end][axis]) < tolerance, `corner ${end}.${axis}: ${JSON.stringify({ a, b })}`);
}
try {
  for (let n = 0; n < 100; n++) {
    try { if ((await fetch(`${origin}/hot?mock=1`)).ok) break; } catch {}
    if (n === 99) throw Error(log);
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  await mkdir(artifacts, { recursive: true }); browser = await chromium.launch({ headless: true });
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    for (const reduced of [false, true]) {
      let context = await browser.newContext({ viewport, reducedMotion: reduced ? 'reduce' : 'no-preference' });
      let page = await context.newPage(); page.on('pageerror', e => errors.push(e.message));
      // Direct entry has no intro; the corner must already belong to the shared scene.
      await page.goto(`${origin}/hot?mock=1`); await ready(page);
      const initial = await mark(page);
      assert.ok(initial.visible); assert.equal(initial.stroke, 'rgb(155, 157, 153)'); assert.equal(initial.width, '1.6px');
      assert.equal(initial.pointerEvents, 'none');
      assert.ok(Math.abs(initial.a.x - initial.paper.x - 19.8) < .2);
      assert.ok(Math.abs(initial.b.y - initial.paper.y - 19.8) < .2);
      const scrolled = await page.locator('[data-p0-scroller]').evaluate(el => { el.scrollTop = 400; return el.scrollTop; });
      assert.ok(scrolled > 0, 'exercise actual content scrolling'); sameLine(initial, await mark(page));
      await page.reload(); await ready(page); sameLine(initial, await mark(page));
      // Use the actual menu navigation (mobile menu opens before choosing a destination).
      if (viewport.width <= 768) await page.getByRole('button', { name: '打开菜单' }).click();
      await page.locator('[data-home-sidebar] a[href*="/about"]').click(); await ready(page);
      sameLine(initial, await mark(page));
      pass(`${viewport.width}${reduced ? ' reduced' : ''}: direct, scroll, reload, menu navigation`);

      await context.close();
      // A fresh browser session isolates first-entry behavior from the revisit checks above.
      context = await browser.newContext({ viewport, reducedMotion: reduced ? 'reduce' : 'no-preference' });
      page = await context.newPage(); page.on('pageerror', e => errors.push(e.message));
      await page.goto(`${origin}/?mock=1`);
      await page.locator('[data-scroll-cue-shell] button:not(:disabled)').waitFor({ timeout: 45000 });
      await page.evaluate(() => {
        window.__cornerFrames = [];
        const tick = () => {
          const line = document.querySelector('[data-white-paper-staple-line="p0"]') ?? document.querySelector('[data-main-paper-staple] line');
          if (!line) return;
          const p = (x, y) => { const q = new DOMPoint(x, y).matrixTransform(line.getScreenCTM()); return { x: q.x, y: q.y }; };
          const isIntro = line.hasAttribute('data-white-paper-staple-line');
          window.__cornerFrames.push({ intro: isIntro, a: p(line.x1.baseVal.value, line.y1.baseVal.value), b: p(line.x2.baseVal.value, line.y2.baseVal.value), visible: line.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) });
          if (isIntro) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      });
      await page.locator('[data-scroll-cue-shell] button').click();
      if (!reduced) { await page.waitForTimeout(450); await page.setViewportSize({ width: viewport.width === 1440 ? 1000 : 430, height: 800 }); }
      await ready(page);
      const stable = await mark(page), frames = await page.evaluate(() => window.__cornerFrames);
      assert.ok(stable.visible); assert.ok(frames.length > 0); assert.ok(frames.every(frame => frame.visible), 'corner stays visible throughout handoff');
      if (!reduced) sameLine(frames.findLast(frame => frame.intro), stable, 1);
      await page.screenshot({ path: `${artifacts}/${viewport.width}${reduced ? '-reduced' : ''}.png` });
      pass(`${viewport.width}${reduced ? ' reduced' : ' resize'}: intro handoff without disappearance or jump`);
      await context.close();
    }
  }
  assert.deepEqual(errors, []); await writeFile(`${artifacts}/results.json`, JSON.stringify({ checks, errors }, null, 2));
  console.log(`${checks.length} focused checks passed`);
} finally { await browser?.close(); server.kill(); await new Promise(resolve => api.close(resolve)); }
