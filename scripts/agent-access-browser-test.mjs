// Production Next + real FastAPI + the existing local DB. No ingestion, models or data writes.
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { createServer } from 'node:http';
const { chromium } = await import(pathToFileURL(process.env.PULSE_PLAYWRIGHT_MODULE ?? 'C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs').href);
const origin = 'http://127.0.0.1:3160', output = 'test-results/agent-access';
const children = [], logs = {}, checks = [], errors = [], captures = [], browserErrors = [];
let browser, page, api, slowApi;
await mkdir(output, {recursive: true});
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
function start(name, command, args, cwd, env) {
  const child = spawn(command, args, {cwd, env: {...process.env, ...env}, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe']});
  logs[name] = ''; child.stdout.on('data', chunk => logs[name] += chunk); child.stderr.on('data', chunk => logs[name] += chunk);
  children.push(child); return child;
}
async function stop(child) {
  if (!child || child.exitCode !== null) return;
  if (process.platform === 'win32') { try { execFileSync('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], {windowsHide: true, stdio: 'ignore'}); } catch {} }
  else child.kill('SIGTERM');
  await wait(250);
}
async function ready(url) { for (let i = 0; i < 80; i++) { try { if ((await fetch(url)).ok) return; } catch {} await wait(500); } throw Error(`service not ready: ${url}`); }
async function run(name, fn) {
  console.log(`RUN ${name}`);
  try { await fn(); checks.push(name); console.log(`PASS ${name}`); }
  catch (error) { errors.push({name, message: String(error), stack: error.stack}); console.error(`FAIL ${name}: ${error.message}`); if (page && !page.isClosed()) await page.screenshot({path: `${output}/failure-${errors.length}.png`}).catch(() => {}); }
}
const scroller = () => page.locator('[data-p0-scroller]');
async function goto(path = '/agent', base = origin) { await page.goto(base + path); await page.locator('[data-entry="stable"] [data-phase="idle"]').waitFor(); await page.waitForFunction(() => document.querySelector('[data-p0-scroller]')?.getAttribute('aria-busy') === 'false'); }
async function selected(key) { await page.waitForFunction(key => document.getElementById(`agent-tab-${key}`)?.getAttribute('aria-selected') === 'true' && document.querySelector('[data-p0-scroller]')?.getAttribute('aria-busy') === 'false', key); }
async function fits() { assert.equal(await scroller().evaluate(el => el.scrollWidth <= el.clientWidth + 1), true, 'p0 must not scroll horizontally'); }
function backend(configured) { return start(`api-${configured}`, 'D:/pulse/backend/.venv/Scripts/python.exe', ['-m', 'uvicorn', 'bluepulse_backend.api:app', '--host', '127.0.0.1', '--port', '3161'], 'D:/pulse/backend', {BLUEPULSE_SITE_ORIGIN: configured ? origin : '', BLUEPULSE_DATABASE_URL: 'sqlite:///D:/pulse/backend/data/bluepulse.db'}); }
try {
  api = backend(true);
  start('web', process.execPath, ['node_modules/next/dist/bin/next', 'start', '--hostname', '127.0.0.1', '--port', '3160'], process.cwd(), {BLUEPULSE_SITE_ORIGIN: origin, BLUEPULSE_API_URL: 'http://127.0.0.1:3161'});
  await ready('http://127.0.0.1:3161/api/v1/health/ready'); await ready(origin + '/agent');
  await run('Codex HTTP instructions → real recent/search empty results', async () => {
    const guide = await fetch(origin + '/api/v1/agent'); assert.equal(guide.status, 200); assert.match(guide.headers.get('content-type'), /text\/markdown/); assert.equal(guide.headers.get('cache-control'), 'no-store');
    const text = await guide.text(); assert.match(text, /window=7d/); assert.match(text, /window=all/); assert.match(text, /127\.0\.0\.1:3160/);
    // Run the same actual command that a Windows Codex Agent can use, not only a JS fetch.
    assert.match(execFileSync('curl.exe', ['--silent', '--show-error', origin + '/api/v1/agent'], {encoding: 'utf8', windowsHide: true}), /# BluePulse Agent/);
    captures.push({path: '/api/v1/agent', status: guide.status, contentType: guide.headers.get('content-type'), body: text});
    for (const path of ['/api/v1/agent/latest?window=7d&limit=10', '/api/v1/agent/search?q=%E8%AD%A6%E5%8A%A1%E6%8A%80%E6%9C%AF&window=all&limit=10']) {
      const response = await fetch(origin + path); assert.equal(response.status, 200); assert.equal(response.headers.get('cache-control'), 'no-store'); assert.ok(response.headers.get('x-request-id'));
      const body = await response.json(); assert.equal(body.schema_version, 1); assert.deepEqual(body.items, []); captures.push({path, status: response.status, body});
    }
  });
  await run('real 422 boundaries and exact route/method restrictions', async () => {
    for (const path of ['/latest?window=all', '/latest?limit=31', '/search?q=x', '/search?q=%20%20']) { const response = await fetch(origin + '/api/v1/agent' + path); assert.equal(response.status, 422); assert.equal(response.headers.get('cache-control'), 'no-store'); assert.ok((await response.json()).error); }
    assert.equal((await fetch(origin + '/api/v1/agent/hot')).status, 404);
    assert.equal((await fetch(origin + '/api/v1/agent', {method: 'POST'})).status, 405);
  });
  browser = await chromium.launch({headless: true});
  const ctx = await browser.newContext({viewport: {width: 1360, height: 760}, permissions: ['clipboard-read', 'clipboard-write']});
  page = await ctx.newPage(); page.on('pageerror', error => browserErrors.push(error.message));
  page.on('request', request => { if (request.url().includes('/api/v1/agent')) captures.push({browserRequest: request.url()}); });
  await run('desktop stable p0, accurate status and first-screen address', async () => {
    await goto(); await page.getByText('HTTP 入口可响应', {exact: true}).waitFor(); await fits();
    assert.equal(await page.getByRole('tab').count(), 2); assert.equal(await page.getByRole('heading', {name: /MCP|RSS/}).count(), 0);
    const address = await page.getByRole('button', {name: '复制地址', exact: true}).boundingBox(); assert.ok(address.y + address.height <= 710, 'copyable address must fit the desktop first screen');
    await page.screenshot({path: `${output}/desktop-guide.png`});
  });
  await run('copy address and prompt use the configured public base', async () => {
    await page.getByRole('button', {name: '复制地址', exact: true}).click(); assert.equal(await page.evaluate(() => navigator.clipboard.readText()), origin + '/api/v1/agent');
    await page.locator('#agent-panel').getByRole('button', {name: '复制', exact: true}).click(); assert.match(await page.evaluate(() => navigator.clipboard.readText()), /先读取 http:\/\/127\.0\.0\.1:3160\/api\/v1\/agent/);
  });
  await run('tab navigation preserves scroll, history and avoids duplicate probes', async () => {
    const before = captures.filter(x => x.browserRequest).length;
    await page.getByRole('tab', {name: /JSON API/}).scrollIntoViewIfNeeded();
    const top = await scroller().evaluate(el => el.scrollTop);
    await page.getByRole('tab', {name: /JSON API/}).click(); await selected('api');
    assert.equal(new URL(page.url()).searchParams.get('tab'), 'api');
    assert.ok(Math.abs(await scroller().evaluate(el => el.scrollTop) - top) <= 2);
    assert.equal(captures.filter(x => x.browserRequest).length, before);
    await page.getByRole('tab', {name: /JSON API/}).click(); assert.equal(captures.filter(x => x.browserRequest).length, before);
    await page.goBack(); await selected('guide'); await page.goForward(); await selected('api'); await page.reload(); await selected('api');
    await page.screenshot({path: `${output}/desktop-api.png`});
  });
  await run('keyboard arrows, Home and End activate the corresponding URL panel', async () => {
    const tab = page.getByRole('tab', {selected: true}); await tab.focus(); await tab.press('ArrowLeft'); await selected('guide');
    await page.getByRole('tab', {selected: true}).press('End'); await selected('api');
    await page.getByRole('tab', {selected: true}).press('Home'); await selected('guide');
  });
  await run('cross-panel anchor direct access switches panel and scrolls inside p0', async () => {
    await goto('/agent#agent-api-recovery'); await selected('api');
    await page.getByRole('heading', {name: '出错了怎么办'}).waitFor();
    await page.waitForFunction(() => { const area = document.querySelector('[data-p0-scroller]'); const section = document.getElementById('agent-api-recovery'); return area && section && area.scrollTop > 0 && section.getBoundingClientRect().top < area.getBoundingClientRect().bottom; });
    await fits();
  });
  await run('copy denial gives feedback and retains selectable text', async () => {
    await goto(); await page.evaluate(() => { Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {writeText: async () => { throw Error('denied'); }}}); });
    await page.getByRole('button', {name: '复制地址', exact: true}).click(); await page.getByText('复制失败，请选择文本手动复制。', {exact: true}).waitFor();
    assert.equal(await page.locator('code').filter({hasText: origin + '/api/v1/agent'}).first().evaluate(el => getComputedStyle(el).userSelect), 'text');
  });
  await run('mobile guide/API local overflow, full address and resources after steps', async () => {
    await page.setViewportSize({width: 390, height: 844}); await goto(); await fits();
    assert.equal(await page.getByRole('navigation', {name: '接入方式', exact: true}).isVisible(), false);
    const address = page.locator('code').filter({hasText: origin + '/api/v1/agent'}).first(); assert.ok(await address.isVisible());
    const copyBox = await page.getByRole('button', {name: '复制地址', exact: true}).boundingBox(); assert.ok(copyBox.y + copyBox.height < 797, 'address copy button must fit the mobile first screen');
    await page.screenshot({path: `${output}/mobile-guide.png`});
    await page.getByRole('tab', {name: /JSON API/}).click(); await selected('api'); await fits();
    await scroller().evaluate(el => el.scrollTop = 700); await page.screenshot({path: `${output}/mobile-api.png`});
    assert.ok(await page.locator('pre').first().evaluate(el => el.scrollWidth >= el.clientWidth));
  });
  await run('reduced motion retains tabs and coherent stable scene', async () => {
    await page.emulateMedia({reducedMotion: 'reduce'}); await goto('/agent?tab=api'); await selected('api'); await fits();
    assert.equal(await page.getByRole('tab', {name: /JSON API/}).evaluate(el => getComputedStyle(el).transitionDuration), '0s');
    await page.getByRole('tab', {name: /给 Agent 使用/}).click(); await selected('guide');
    await page.screenshot({path: `${output}/reduced-motion.png`});
  });
  await run('real backend missing-origin 503 is distinct from an empty result', async () => {
    await stop(api); api = backend(false); await ready('http://127.0.0.1:3161/api/v1/health/ready');
    for (const path of ['', '/latest', '/search?q=police']) {
      const response = await fetch(origin + '/api/v1/agent' + path); assert.equal(response.status, 503); assert.equal((await response.json()).error.code, 'agent_origin_unconfigured'); assert.equal(response.headers.get('cache-control'), 'no-store');
    }
    await goto(); await page.getByText('后端接入地址尚未配置', {exact: true}).waitFor();
  });
  await run('real backend disconnect retains guide and shows unavailable status', async () => {
    await stop(api);
    const response = await fetch(origin + '/api/v1/agent/latest'); assert.equal(response.status, 503); assert.equal((await response.json()).error.code, 'upstream_unavailable');
    await goto(); await page.getByText('HTTP 入口暂不可用', {exact: true}).waitFor(); assert.ok(await page.getByRole('heading', {name: '把说明交给 Agent，就能开始查'}).isVisible());
  });
  await run('controlled slow upstream returns actual 504 within the six-second proxy deadline', async () => {
    slowApi = createServer((req, res) => { const timer = setTimeout(() => res.end('{}'), 9000); res.on('close', () => clearTimeout(timer)); });
    await new Promise(resolve => slowApi.listen(3161, '127.0.0.1', resolve));
    const started = Date.now(), response = await fetch(origin + '/api/v1/agent/latest');
    assert.equal(response.status, 504); assert.equal((await response.json()).error.code, 'upstream_timeout'); assert.equal(response.headers.get('cache-control'), 'no-store');
    assert.ok(Date.now() - started >= 5900 && Date.now() - started < 8500);
    slowApi.closeAllConnections(); await new Promise(resolve => slowApi.close(resolve)); slowApi = null;
  });
  await run('unconfigured frontend does not invent copyable URLs', async () => {
    start('web-unconfigured', process.execPath, ['node_modules/next/dist/bin/next', 'start', '--hostname', '127.0.0.1', '--port', '3162'], process.cwd(), {BLUEPULSE_SITE_ORIGIN: '', BLUEPULSE_API_URL: 'http://127.0.0.1:3161'});
    await ready('http://127.0.0.1:3162/agent'); await goto('/agent', 'http://127.0.0.1:3162');
    assert.equal(await page.getByRole('button', {name: /复制/}).count(), 0); await page.getByText('接入地址尚未配置', {exact: true}).waitFor();
  });
  await ctx.close();
} finally {
  if (slowApi) { slowApi.closeAllConnections(); slowApi.close(); }
  await browser?.close(); for (const child of children.reverse()) await stop(child);
  await writeFile(`${output}/verification.json`, JSON.stringify({date: new Date().toISOString(), checks, errors, browserErrors, captures, logs}, null, 2));
}
assert.deepEqual(errors, []); assert.deepEqual(browserErrors, []);
console.log(`${checks.length} Agent checks passed`);
