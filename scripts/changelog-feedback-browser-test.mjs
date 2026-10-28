import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

const bundled = "C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs";
let playwright = process.env.PULSE_PLAYWRIGHT_MODULE;
if (!playwright) { try { await access(bundled); playwright = bundled; } catch {} }
const { chromium } = await import(playwright ? pathToFileURL(playwright).href : "playwright");
const artifacts = "test-results/changelog-feedback";
const reportName = process.env.PULSE_FEEDBACK_TEST_FILTER ? "verification-filtered.json" : "verification.json";
const disabledOrigin = "http://localhost:3140", liveOrigin = "http://localhost:3142";
const changelog = JSON.parse(await readFile("site/changelog.json", "utf8"));
const keys = { live: "bluepulse:feedback-draft:v1:live", mock: "bluepulse:feedback-draft:v1:mock", seen: "blue-pulse-changelog-seen-v1:mock" };
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jG/8AAAAASUVORK5CYII=", "base64");
const checks = [], errors = [], browserErrors = [], requests = [], posts = [], serverLogs = {};
let mode = "success", delay = 0, browser, currentPage;
await mkdir(artifacts, { recursive: true });
const api = createServer(async (req, res) => {
  requests.push({ method: req.method, path: req.url });
  res.setHeader("Content-Type", "application/json");
  if (req.method === "POST" && req.url === "/api/v1/site/feedback") {
    const chunks = []; for await (const chunk of req) chunks.push(chunk);
    const bytes = Buffer.concat(chunks), capture = { headers: { ...req.headers }, bytes: bytes.length, fields: {}, file: null, mode };
    try {
      const form = await new Request("http://127.0.0.1:3141/api/v1/site/feedback", { method: "POST", headers: { "Content-Type": req.headers["content-type"] }, body: bytes }).formData();
      for (const [key, value] of form) {
        if (typeof value === "string") capture.fields[key] = value;
        else capture.file = { field: key, name: value.name, type: value.type, size: value.size, bytes: Buffer.from(await value.arrayBuffer()).toString("base64") };
      }
    } catch (error) { capture.parseError = String(error); }
    posts.push(capture);
    const responseMode = mode;
    if (delay) await new Promise(resolve => setTimeout(resolve, delay));
    if (responseMode === "disconnect") { res.destroy(); return; }
    if (responseMode === "invalid201") { res.statusCode = 201; res.end('{"id":0}'); return; }
    if (responseMode === "200") { res.statusCode = 200; res.end('{"id":77}'); return; }
    if (responseMode === "success") { res.statusCode = 201; res.end('{"id":77}'); return; }
    res.statusCode = Number(responseMode);
    if (responseMode === "429") res.setHeader("Retry-After", "2");
    res.end(JSON.stringify({ error: { code: `test_${responseMode}`, message: "controlled local service response", request_id: `local-${responseMode}` } })); return;
  }
  if (["/api/v1/taxonomy", "/api/v1/sources"].includes(req.url)) { res.end('{"items":[]}'); return; }
  res.statusCode = 404; res.end('{"error":{"code":"not_found"}}');
});
await new Promise(resolve => api.listen(3141, "127.0.0.1", resolve));
function start(port, enabled) {
  const child = spawn(process.execPath, ["node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", String(port)], {
    cwd: process.cwd(), env: { ...process.env, BLUEPULSE_API_URL: "http://127.0.0.1:3141", BLUEPULSE_FEEDBACK_ENABLED: enabled ? "1" : "0", BLUEPULSE_SITE_ORIGIN: `http://localhost:${port}` },
    stdio: ["ignore", "pipe", "pipe"], windowsHide: true,
  });
  serverLogs[port] = "";
  child.stdout.on("data", chunk => { serverLogs[port] += chunk; }); child.stderr.on("data", chunk => { serverLogs[port] += chunk; });
  return child;
}
const servers = [start(3140, false), start(3142, true)];
const wait = (ms) => new Promise(resolve => setTimeout(resolve, ms));
const paper = page => page.locator("[data-p0-scroller]");
const alert = page => page.locator('form [role="alert"]');
const ready = async (page, path) => {
  await page.waitForFunction(path => location.pathname === path && document.querySelector('[data-entry="stable"] [data-phase="idle"]'), path);
  if (path === "/feedback") await page.locator("#fb-content").waitFor({ state: "visible" });
};
const goto = async (page, path, origin = disabledOrigin) => { await page.goto(`${origin}${path}`); await ready(page, path.split(/[?#]/)[0]); };
const button = (page, kind) => page.locator("button[aria-pressed]:visible").filter({ has: page.locator("span", { hasText: new RegExp(`^${kind}$`) }) });
async function context(options = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1360, height: 760 }, ...options });
  await ctx.addInitScript(() => {
    window.__feedbackFetches = 0; window.__revokedShots = [];
    const fetcher = window.fetch;
    window.fetch = function (input, options) {
      if (String(input).includes("/api/bluepulse/site/feedback")) window.__feedbackFetches++;
      return Reflect.apply(fetcher, this, [input, options]);
    };
    const revoke = URL.revokeObjectURL;
    URL.revokeObjectURL = function (url) { window.__revokedShots.push(url); return revoke.call(this, url); };
  });
  ctx.on("page", page => { page.on("pageerror", error => browserErrors.push({ url: page.url(), message: error.message })); });
  return ctx;
}
async function fit(page) { assert.equal(await paper(page).evaluate(el => el.scrollWidth <= el.clientWidth + 1), true, "p0 horizontal overflow"); }
async function saveResults() {
  await writeFile(`${artifacts}/${reportName}`, JSON.stringify({ date: new Date().toISOString(), checks, errors, browserErrors, upstreamFeedbackCount: posts.length, requests, posts, serverLogs }, null, 2));
}
async function run(name, fn) {
  if (process.env.PULSE_FEEDBACK_TEST_FILTER && !name.includes(process.env.PULSE_FEEDBACK_TEST_FILTER)) return;
  console.log(`RUN ${name}`);
  try { await fn(); checks.push(name); console.log(`PASS ${name}`); }
  catch (error) {
    const entry = { name, message: String(error), stack: error.stack, url: currentPage?.url(), diagnostics: error.pageDiagnostics, screenshot: error.failureScreenshot };
    if (currentPage && !currentPage.isClosed()) {
      const prefix = `${artifacts}/failure-${String(errors.length + 1).padStart(2, "0")}`;
      await currentPage.screenshot({ path: `${prefix}.png` }).catch(() => {});
      entry.diagnostics = await currentPage.evaluate(() => ({ title: document.title, headings: [...document.querySelectorAll("h1,h2")].map(el => el.textContent), paper: [...document.querySelectorAll("[data-p0-scroller]")].map(el => ({ width: el.clientWidth, scrollWidth: el.scrollWidth, top: el.scrollTop })), alerts: [...document.querySelectorAll('[role="alert"]')].map(el => el.textContent), mode: document.querySelector("[data-feedback-mode]")?.getAttribute("data-feedback-mode"), body: document.body.innerText.slice(0, 12000) })).catch(() => null);
    }
    errors.push(entry); console.error(`FAIL ${name}: ${error.message}`);
  } finally { await saveResults(); }
}
async function withPage(fn, options) {
  const ctx = await context(options), page = await ctx.newPage(); currentPage = page;
  page.setDefaultTimeout(7000);
  try { await fn(page, ctx); }
  catch (error) {
    error.failureScreenshot = `${artifacts}/failure-${String(errors.length + 1).padStart(2, "0")}.png`;
    await page.screenshot({ path: error.failureScreenshot }).catch(() => {});
    error.pageDiagnostics = await page.evaluate(() => ({ title: document.title, headings: [...document.querySelectorAll("h1,h2")].map(el => el.textContent), mode: document.querySelector("[data-feedback-mode]")?.getAttribute("data-feedback-mode"), paper: [...document.querySelectorAll("[data-p0-scroller]")].map(el => ({ width: el.clientWidth, scrollWidth: el.scrollWidth, top: el.scrollTop })), alerts: [...document.querySelectorAll('form [role="alert"]')].map(el => el.textContent), body: document.body.innerText.slice(0, 12000) })).catch(() => null);
    throw error;
  } finally { await ctx.close(); }
}
async function submit(page) { await page.locator('button[type="submit"]').click(); }
async function assertPreserved(page, text) {
  await alert(page).waitFor(); assert.equal(await page.locator("#fb-content").inputValue(), text);
  assert.equal(await page.getByRole("heading", { name: "收到了，谢谢你", exact: true }).count(), 0);
}
try {
  for (const origin of [disabledOrigin, liveOrigin]) {
    let up = false;
    for (let attempt = 0; attempt < 100; attempt++) { try { if ((await fetch(`${origin}/feedback`)).ok) { up = true; break; } } catch {} await wait(100); }
    assert.ok(up, `Next server did not start: ${JSON.stringify(serverLogs)}`);
  }
  browser = await chromium.launch({ headless: true });
  console.log("Browser checks started on controlled ports 3140/3141/3142");

  await run("changelog/meta HTTP payloads, cache durations, ETags and empty conditional 304", async () => {
    for (const [path, maxAge] of [["changelog", 300], ["meta", 60]]) {
      const response = await fetch(`${disabledOrigin}/api/bluepulse/site/${path}`);
      assert.equal(response.status, 200); const body = await response.json();
      assert.equal(path === "meta" ? body.changelogVersion : body.latestVersion, changelog.latestVersion);
      if (path === "changelog") assert.equal(body.releases.length, changelog.releases.length);
      assert.match(response.headers.get("cache-control"), new RegExp(`max-age=${maxAge}(?:,|$)`));
      const etag = response.headers.get("etag"); assert.ok(etag);
      const conditional = await fetch(`${disabledOrigin}/api/bluepulse/site/${path}`, { headers: { "If-None-Match": etag } });
      assert.equal(conditional.status, 304); assert.equal(await conditional.text(), ""); assert.equal(conditional.headers.get("etag"), etag);
    }
  });

  await run("responsive desktop/mobile/reduced-motion screenshots for changelog and feedback", () => withPage(async page => {
    for (const target of ["changelog", "feedback"]) for (const view of ["desktop", "mobile", "reduced-motion"]) {
      await page.setViewportSize(view === "mobile" ? { width: 390, height: 844 } : { width: 1360, height: 760 });
      await page.emulateMedia({ reducedMotion: view === "reduced-motion" ? "reduce" : "no-preference" });
      await goto(page, `/${target}?mock=1`); await fit(page);
      await page.screenshot({ path: `${artifacts}/${target}-${view}.png` });
      const geometry = await paper(page).evaluate(el => ({ width: el.clientWidth, height: el.clientHeight }));
      assert.ok(geometry.width > 190 && geometry.height > 100);
      if (view === "desktop") {
        const aside = page.locator('aside').filter({ has: page.getByRole("heading", { name: target === "feedback" ? "写清楚这几点，处理更快" : "按类型看", exact: true }) });
        const layout = await aside.evaluate(el => ({ position: getComputedStyle(el).position, width: el.getBoundingClientRect().width, parent: el.parentElement.getBoundingClientRect().width }));
        if (layout.parent >= 760) { assert.equal(layout.position, "sticky"); assert.ok(Math.abs(layout.width - 200) < 2); }
      }
    }
  }));

  await run("changelog type counts, filtered groups, empty state, month jump/reload and Back", () => withPage(async page => {
    await goto(page, "/changelog?mock=1");
    assert.equal(await page.locator("article h3").count(), changelog.releases.length);
    for (const kind of ["更新", "优化", "下线", "公告"]) {
      const count = changelog.releases.filter(r => r.kind === kind).length;
      assert.equal(await button(page, kind).locator("small").textContent(), String(count));
      await button(page, kind).click(); assert.equal(await page.locator("article h3").count(), count);
      if (!count) { await page.getByText(`暂时没有“${kind}”记录。`, { exact: false }).waitFor(); await page.getByRole("button", { name: "查看全部更新" }).click(); }
    }
    await button(page, "全部").click();
    const month = page.locator('nav[aria-label="按月份"]:visible a').last();
    const hash = await month.getAttribute("href"); await month.click();
    assert.equal(new URL(page.url()).hash, hash); assert.ok(await paper(page).evaluate(el => el.scrollTop) > 0);
    await page.reload(); await ready(page, "/changelog"); assert.equal(new URL(page.url()).hash, hash);
    await fit(page);
    await button(page, "优化").click();
    await page.getByRole("link", { name: /去反馈/ }).click(); await ready(page, "/feedback");
    assert.equal(await page.locator("#fb-page").inputValue(), "/changelog");
    await page.goBack(); await ready(page, "/changelog");
    assert.equal(await button(page, "优化").getAttribute("aria-pressed"), "true");
  }));

  await run("prefetch does not mark changelog read; visible activation and cross-tab storage clear unread", () => withPage(async (page, ctx) => {
    await goto(page, "/feedback?mock=1");
    const dot = page.locator('[aria-label="有新的更新"]'); await dot.waitFor();
    const peer = await ctx.newPage(); await goto(peer, "/feedback?mock=1"); await peer.locator('[aria-label="有新的更新"]').waitFor();
    const link = page.locator("[data-home-sidebar]").getByRole("link", { name: "更新日志", exact: false });
    await link.hover(); await page.waitForLoadState("networkidle");
    assert.equal(await page.evaluate(key => localStorage.getItem(key), keys.seen), null); assert.equal(await dot.count(), 1);
    await link.click(); await ready(page, "/changelog");
    await page.waitForFunction(key => localStorage.getItem(key) !== null, keys.seen);
    await peer.locator('[aria-label="有新的更新"]').waitFor({ state: "detached" });
    assert.equal(await page.evaluate(key => localStorage.getItem(key), keys.seen), changelog.latestVersion);
  }));

  await run("disabled receiver allows drafts, links real contact and never submits", () => withPage(async page => {
    const before = posts.length;
    await goto(page, "/feedback"); await page.locator('[data-feedback-mode="disabled"]').waitFor();
    await page.locator("#fb-content").fill("关闭接收时仍可编辑的草稿");
    assert.equal(await page.locator('button[type="submit"]').isDisabled(), true);
    assert.match(await page.locator('[data-feedback-mode="disabled"]').textContent(), /不会产生服务器回执/);
    assert.equal(await page.locator('[data-feedback-mode="disabled"] a').getAttribute("href"), "/about#pulse-contact");
    await page.locator('[data-feedback-draft="local"]').waitFor();
    assert.equal(posts.length, before); assert.equal(await page.evaluate(() => window.__feedbackFetches), 0);
    // A previously visited about page has its own saved reading position. An explicit
    // contact link must take precedence over restoring that old position.
    await goto(page, "/about"); await page.locator('[data-p0-scroller][aria-busy="false"]').waitFor();
    await paper(page).evaluate(el => { el.scrollTop = 100; });
    await page.locator('[data-home-sidebar] a[href="/feedback"]').click(); await ready(page, "/feedback");
    await page.locator('[data-feedback-mode="disabled"] a').click(); await ready(page, "/about");
    await page.waitForFunction(() => {
      const area = document.querySelector('[data-p0-scroller]'), contact = document.getElementById('pulse-contact');
      return area?.getAttribute('aria-busy') === 'false' && contact && Math.abs(contact.getBoundingClientRect().top - area.getBoundingClientRect().top) < 45;
    });
  }));

  await run("400ms drafts survive reload/SPA return, isolate live/mock, flush immediate departure", () => withPage(async page => {
    await goto(page, "/feedback"); await page.locator("#fb-content").fill("普通草稿独立保存"); await page.locator('[data-feedback-draft="local"]').waitFor();
    await goto(page, "/feedback?mock=1&from=%2Farticles%2Fsource-test");
    assert.equal(await page.locator("#fb-content").inputValue(), ""); assert.equal(await page.locator("#fb-page").inputValue(), "/articles/source-test");
    await page.locator("#fb-content").fill("演示草稿重载恢复"); await page.locator('[data-feedback-draft="local"]').waitFor();
    await page.reload(); await ready(page, "/feedback"); assert.equal(await page.locator("#fb-content").inputValue(), "演示草稿重载恢复");
    await page.locator("#fb-content").fill("离开前最后一刻修改");
    await page.locator("[data-home-sidebar]").getByRole("link", { name: "更新日志", exact: false }).click(); await ready(page, "/changelog");
    await page.goBack(); await ready(page, "/feedback"); assert.equal(await page.locator("#fb-content").inputValue(), "离开前最后一刻修改");
    assert.equal(await page.evaluate(key => JSON.parse(localStorage.getItem(key)).content, keys.live), "普通草稿独立保存");
  }));

  await run("denied local storage reports memory fallback and retains draft on SPA return", () => withPage(async page => {
    await page.addInitScript(() => Object.defineProperty(window, "localStorage", { configurable: true, get() { throw new DOMException("denied", "SecurityError"); } }));
    await goto(page, "/feedback?mock=1"); await page.locator('[data-feedback-draft="memory"]').waitFor();
    await page.locator("#fb-content").fill("仅当前会话保留的草稿");
    await page.locator("[data-home-sidebar]").getByRole("link", { name: "更新日志", exact: false }).click(); await ready(page, "/changelog");
    await page.goBack(); await ready(page, "/feedback"); assert.equal(await page.locator("#fb-content").inputValue(), "仅当前会话保留的草稿");
    assert.match(await page.locator('[data-feedback-draft="memory"]').textContent(), /刷新或关闭可能丢失/);
  }));

  await run("screenshots picker/drop/paste/remove/same-file/normalization/invalid/oversized and object URL cleanup", () => withPage(async page => {
    await goto(page, "/feedback?mock=1"); const file = page.locator('input[type="file"]');
    await file.setInputFiles({ name: "picked.png", mimeType: "image/png", buffer: png });
    await page.getByAltText("待发送截图预览").waitFor(); const firstUrl = await page.getByAltText("待发送截图预览").getAttribute("src");
    await page.getByRole("button", { name: "移除截图" }).click(); await page.getByAltText("待发送截图预览").waitFor({ state: "detached" });
    assert.ok(await page.evaluate(url => window.__revokedShots.includes(url), firstUrl));
    await file.setInputFiles({ name: "picked.png", mimeType: "image/png", buffer: png }); await page.getByAltText("待发送截图预览").waitFor();
    await page.locator("form").evaluate((form, bytes) => { const dataTransfer = new DataTransfer(); dataTransfer.items.add(new File([new Uint8Array(bytes)], "dropped.jpg", { type: "image/jpg" })); form.dispatchEvent(new DragEvent("dragover", { bubbles: true, cancelable: true, dataTransfer })); form.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer })); }, [...png]);
    await page.getByText("dropped.jpg", { exact: true }).waitFor();
    await page.locator("#fb-content").focus();
    await page.locator("#fb-content").evaluate((input, bytes) => { const clipboardData = new DataTransfer(); clipboardData.items.add(new File([new Uint8Array(bytes)], "pasted.png", { type: "" })); input.dispatchEvent(new ClipboardEvent("paste", { bubbles: true, cancelable: true, clipboardData })); }, [...png]);
    await page.getByText("pasted.png", { exact: true }).waitFor();
    await file.setInputFiles({ name: "invalid.svg", mimeType: "image/svg+xml", buffer: Buffer.from("<svg/>") }); await alert(page).filter({ hasText: "PNG" }).waitFor();
    await file.setInputFiles({ name: "large.png", mimeType: "image/png", buffer: Buffer.alloc(5 * 1024 * 1024 + 1) }); await alert(page).filter({ hasText: "5 MB" }).waitFor();
    assert.equal(await page.getByText("pasted.png", { exact: true }).count(), 1); await fit(page);
  }));

  await run("mock receipt uses no fetch, guards duplicate submission and never recreates successful draft", () => withPage(async page => {
    const before = posts.length;
    await goto(page, "/feedback?mock=1"); await page.locator("#fb-content").fill("本机演示提交不会发送");
    await page.locator("form").evaluate(form => { form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
    await page.getByRole("heading", { name: "演示提交完成，谢谢你" }).waitFor();
    assert.match(await page.locator("[data-p0-scroller]").innerText(), /#10001/); assert.equal(await page.evaluate(() => window.__feedbackFetches), 0); assert.equal(posts.length, before);
    assert.equal(await page.evaluate(key => localStorage.getItem(key), keys.mock), null);
    await page.getByRole("link", { name: "回到精选" }).click(); await ready(page, "/"); await page.goBack(); await ready(page, "/feedback");
    assert.equal(await page.locator("#fb-content").inputValue(), "");
  }));

  await run("live receiver is enabled by runtime env and invalid success/error responses preserve drafts", () => withPage(async page => {
    await goto(page, "/feedback", liveOrigin); await page.locator('[data-feedback-mode="live"]').waitFor();
    for (const responseMode of ["invalid201", "200", "400", "403", "413", "404", "503", "429"]) {
      mode = responseMode; const text = `保留内容测试 ${responseMode}`; await page.locator("#fb-content").fill(text);
      await submit(page); await assertPreserved(page, text);
      assert.equal(await page.evaluate(key => JSON.parse(localStorage.getItem(key)).content, keys.live), text);
      if (responseMode === "429") { assert.equal(await page.locator('button[type="submit"]').isDisabled(), true); await page.waitForFunction(() => !document.querySelector('button[type="submit"]').disabled); }
    }
  }));

  await run("live guarded receipt, exact multipart screenshot and HTTP credential boundary", () => withPage(async page => {
    mode = "success"; delay = 300;
    await goto(page, "/feedback", liveOrigin); await page.locator('[data-feedback-mode="live"]').waitFor();
    // Public readers use local storage, not an account/session credential fixture.
    await page.locator("#fb-content").fill("有效回执完整提交"); await page.locator("#fb-email").fill("local@example.test"); await page.locator("#fb-page").fill("/articles/check");
    await page.locator('input[type="file"]').setInputFiles({ name: "contract.png", mimeType: "image/png", buffer: png });
    const before = posts.length;
    const outgoing = page.waitForRequest(request => request.method() === "POST" && request.url().endsWith("/api/bluepulse/site/feedback"));
    await page.locator("form").evaluate(form => { form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
    assert.equal(await page.locator("#fb-content").isDisabled(), true);
    await page.getByRole("heading", { name: "收到了，谢谢你", exact: true }).waitFor({ timeout: 20000 });
    assert.equal(posts.length - before, 1); const post = posts.at(-1);
    const sentHeaders = await (await outgoing).allHeaders();
    assert.equal(sentHeaders.authorization, undefined);
    assert.deepEqual(post.fields, { content: "有效回执完整提交", email: "local@example.test", pageUrl: "/articles/check" });
    assert.deepEqual(post.file, { field: "screenshot", name: "contract.png", type: "image/png", size: png.length, bytes: png.toString("base64") });
    assert.equal(post.headers.cookie, undefined); assert.equal(post.headers.authorization, undefined); assert.equal(post.headers["x-real-ip"], undefined); assert.ok(post.headers["x-request-id"]);
    assert.match(await paper(page).innerText(), /#77/); assert.equal(await page.evaluate(key => localStorage.getItem(key), keys.live), null);
    await page.reload(); await ready(page, "/feedback"); assert.equal(await page.locator("#fb-content").inputValue(), ""); delay = 0;
    // The public form never adds Authorization. Check that extra caller credential at the
    // actual HTTP boundary without replacing the form's native browser fetch implementation.
    const credentialForm = new FormData(); credentialForm.set("content", "HTTP credential boundary");
    const credentialResponse = await fetch(`${liveOrigin}/api/bluepulse/site/feedback`, { method: "POST", body: credentialForm, headers: { Origin: liveOrigin, Cookie: "private-http-test=must-not-forward", Authorization: "Bearer local-test-only" } });
    assert.equal(credentialResponse.status, 201); assert.equal((await credentialResponse.json()).id, 77);
    assert.equal(posts.at(-1).headers.cookie, undefined); assert.equal(posts.at(-1).headers.authorization, undefined);
  }));

  // Stop the deliberately stalled transport after the normal receipt contract is verified.
  await run("network and timeout unknown outcomes preserve content", () => withPage(async page => {
    await goto(page, "/feedback", liveOrigin); await page.locator('[data-feedback-mode="live"]').waitFor();
    await page.route("**/api/bluepulse/site/feedback", route => route.abort("failed"));
    await page.locator("#fb-content").fill("网络中断需要保留"); await submit(page); await assertPreserved(page, "网络中断需要保留");
    assert.match(await alert(page).textContent(), /无法确认/); await page.unroute("**/api/bluepulse/site/feedback");
    mode = "success"; delay = 17000;
    await page.locator("#fb-content").fill("超时不能声称未发送"); await submit(page);
    await alert(page).waitFor({ timeout: 20000 }); assert.equal(await page.locator("#fb-content").inputValue(), "超时不能声称未发送");
    assert.match(await alert(page).textContent(), /无法确认/); delay = 0;
  }));

  await run("no uncaught browser errors", async () => assert.deepEqual(browserErrors, []));
} catch (error) { errors.push({ name: "harness startup", message: String(error), stack: error.stack }); }
finally {
  await saveResults();
  for (const server of servers) server.kill();
  api.closeAllConnections(); await new Promise(resolve => api.close(resolve));
  // Chromium may wait on a pending service connection; cap only teardown, after results are saved.
  if (browser) await Promise.race([browser.close(), wait(5000)]);
}
console.log(`Completed: ${checks.length} passed, ${errors.length} failed. See ${artifacts}/${reportName}`);
if (errors.length) process.exitCode = 1;
