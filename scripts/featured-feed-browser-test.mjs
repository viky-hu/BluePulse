// Real production UI and Next proxy against a controlled HTTP service; no worker/model calls.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import { MOCK_HOME_DATA } from "../src/app/_lib/home-mock.ts";
const { chromium } = await import(pathToFileURL(process.env.PULSE_PLAYWRIGHT_MODULE ?? "C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs").href);
const origin = "http://127.0.0.1:3160", artifacts = "test-results/featured-feed";
const slugs = ["product", "practice", "paper", "law", "embodied", "public-opinion", "low-altitude"];
const taxonomy = slugs.map(slug => ({ id: slug, slug, name_zh: slug, name_en: slug, parent_id: null }));
const rows = Array.from({ length: 76 }, (_, i) => ({ ...MOCK_HOME_DATA.articles[i % 8], id: `f3300000-0000-4000-8000-${String(i + 1).padStart(12, "0")}`, title: `警务科技公开材料 ${i + 1}：系统适用条件、证据引用与人工复核`, summary: `受控接口演示摘要 ${i + 1}。公开材料记录具体场景中的适用边界与人工复核流程，测试结果不代表真实新闻或后端已经上线。`, importance_score: 92 - i % 35, published_at: new Date(Date.UTC(2026, 9, 30, 7, 25) - i * 47 * 60000).toISOString(), topics: [slugs[i % 7]], selected: true, channel: "news", x: null, media_preview: null, featured_reason: "关注可核查的公开证据，以及人工复核与责任边界。" }));
rows[1] = { ...rows[1], channel: "x", x: { authorName: "公共安全研究站", handle: "safety_lab", avatarUrl: null, media: [{ kind: "image", url: "/favicon.ico", fullUrl: "/favicon.ico", width: 128, height: 128, alt: "受控媒体预览", poster: null }], quoted: { authorName: "研究团队", handle: "research", text: "公开评测关注跨场景误差。", translation: null } } };
rows[2].sameEvent = { id: rows[0].id, title: rows[0].title };
const hot = Array.from({ length: 5 }, (_, i) => ({ rank: i + 1, title: `公共安全热点事件 ${i + 1}：公开验证与应用边界`, heat: 137 - i * 19, trend: ["up", "new", "flat", "down", "unknown"][i], storyPublicId: i === 1 ? null : `event-${i + 1}`, itemId: rows[i].id, participantCount: 9, participants: ["研究站", "装备观察", "法治观察", "技术实验室", "公共安全", "实战研究", "技术社区"].map((name, j) => ({ name, kind: j < 6 ? "editorial" : "signal", iconUrl: j === 0 ? "/favicon.ico" : null })) }));
const cards = rows.map((item, i) => ({ key: `fact-${i + 1}`, anchorAt: item.published_at, item, group: i % 4 === 0 ? { factId: `group-${i + 1}`, reportCount: 4, additionalSourceCount: 3 } : null }));
const dayOf = at => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(at));
const requests = [], checks = [], errors = [];
let mode = "ready", missingTopic = false, cursorInvalid = false, holdCursor = false, releaseCursor = null, holdTopic = null, releaseHeld = null, groupDelay = 0, browser, serverLog = "";
const api = createServer(async (req, res) => {
  const url = new URL(req.url, origin); requests.push({ path: url.pathname, query: url.search });
  res.setHeader("Content-Type", "application/json"); res.setHeader("Cache-Control", mode === "nostore" ? "no-store" : "public,max-age=60");
  res.setHeader("X-Accel-Expires", `@${Math.floor(Date.now() / 1000) + 60}`);
  const send = value => res.end(JSON.stringify(value));
  if (url.pathname === "/api/v1/taxonomy") return send({ items: missingTopic ? taxonomy.filter(t => t.slug !== "law") : taxonomy });
  if (url.pathname === "/api/v1/home/featured") return send({ items: [], generated_at: null, window_policy: "24h_then_7d" });
  if (url.pathname === "/api/v1/site/timeline") {
    if (holdTopic && url.searchParams.get("topic") === holdTopic) await new Promise(resolve => { releaseHeld = resolve; });
    if (mode === "unavailable" || mode === "error") { res.statusCode = mode === "unavailable" ? 404 : 503; return send({ error: { code: "not_found" } }); }
    if (mode === "malformed") return send({ cards: null });
    const filters = { region: url.searchParams.get("region") ?? "", topic: url.searchParams.get("topic") ?? "" };
    const cursor = url.searchParams.get("cursor");
    if (cursor && holdCursor) await new Promise(resolve => { releaseCursor = resolve; });
    if (cursor && cursorInvalid) { cursorInvalid = false; res.statusCode = 400; return send({ error: { code: "invalid_cursor" } }); }
    const filtered = mode === "empty" ? [] : cards.filter(c => (!filters.region || c.item.region === filters.region) && (!filters.topic || c.item.topics.includes(filters.topic)));
    const offset = cursor ? Number(cursor.slice(5)) : 0;
    const dayCounts = {}; for (const card of filtered) dayCounts[dayOf(card.anchorAt)] = (dayCounts[dayOf(card.anchorAt)] ?? 0) + 1;
    return send({ filters, cards: filtered.slice(offset, offset + 20), nextCursor: offset + 20 < filtered.length ? `page-${offset + 20}` : null, dayCounts, hot: !filters.region && !filters.topic && !cursor ? hot : null });
  }
  if (/^\/api\/v1\/site\/groups\/group-\d+\/reports$/.test(url.pathname)) { if (groupDelay) await new Promise(resolve => setTimeout(resolve, groupDelay)); res.setHeader("Cache-Control", "no-store"); return send({ factId: url.pathname.split("/")[5], reports: rows.slice(0, 4).map(item => ({ id: item.id, title: item.title, source: item.source, timelineAt: item.published_at, originalUrl: item.url })) }); }
  if (url.pathname === "/api/v1/articles") {
    const topic = url.searchParams.get("topic"), region = url.searchParams.get("region");
    return send({ items: rows.filter(item => (!topic || item.topics.includes(topic)) && (!region || item.region === region)).slice(0, 40), next_cursor: null, limit: 40 });
  }
  if (url.pathname === "/api/v1/sources") return send({ items: MOCK_HOME_DATA.sources });
  const item = rows.find(row => url.pathname === `/api/v1/articles/${row.id}`);
  if (item) return send({ ...item, source_body: null, zh_body: null, author: null, quality_status: "test", body_status: "summary_only", translation_status: "source_unavailable", media: [], entities: [] });
  res.statusCode = 404; send({});
});
await new Promise(resolve => api.listen(3161, "127.0.0.1", resolve));
const server = spawn(process.execPath, ["node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "3160"], { cwd: process.cwd(), env: { ...process.env, BLUEPULSE_API_URL: "http://127.0.0.1:3161" }, stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
server.stdout.on("data", d => { serverLog += d; }); server.stderr.on("data", d => { serverLog += d; });
const check = name => { checks.push(name); console.log(`PASS ${name}`); };
async function ready(page, path = "/") { await page.waitForFunction(path => location.pathname === path && document.querySelector('[data-entry="stable"] [data-phase="idle"]') && document.querySelector("[data-p0-scroller]")?.getAttribute("aria-busy") === "false" && (path !== "/" || document.querySelector("[data-featured-status]")?.getAttribute("data-featured-status") !== "loading"), path); }
async function goto(page, path = "/", expectedPath = path.split(/[?#]/)[0]) { await page.goto(`${origin}${path}`); await ready(page, expectedPath); }
const news = page => page.locator("article[data-item-id]");
const paper = page => page.locator("[data-p0-scroller]");
async function menu(page, href) { const toggle = page.getByRole("button", { name: "打开菜单", exact: true }); if (await toggle.isVisible()) await toggle.click(); await page.locator(`aside a[href="${href}"]`).last().click(); await ready(page, href); }
async function end(page) { await paper(page).evaluate(el => { el.scrollTop = el.scrollHeight; }); }
try {
  await mkdir(artifacts, { recursive: true });
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`${origin}/hot`)).ok) break; } catch {} if (i === 99) throw Error(serverLog); await new Promise(resolve => setTimeout(resolve, 100)); }
  browser = await chromium.launch({ headless: true });
  for (const spec of [{ name: "desktop", viewport: { width: 1360, height: 760 }, reducedMotion: "no-preference" }, { name: "mobile", viewport: { width: 390, height: 844 }, reducedMotion: "no-preference" }, { name: "reduced", viewport: { width: 1360, height: 760 }, reducedMotion: "reduce" }]) {
    const context = await browser.newContext({ viewport: spec.viewport, reducedMotion: spec.reducedMotion, isMobile: spec.name === "mobile", hasTouch: spec.name === "mobile" });
    await context.addInitScript(() => { localStorage.setItem("blue-pulse-entry-complete-v1", "1"); localStorage.setItem("blue-pulse-entry-complete-v1:mock", "1"); });
    const page = await context.newPage(); page.on("pageerror", error => errors.push(`${spec.name}: ${error.message}`));
    if (spec.name === "desktop") await page.clock.install();
    await goto(page); assert.equal(await news(page).count(), 20);
    assert.equal(await page.locator("#hot-topics").textContent(), "当前热点");
    assert.equal(await page.getByText("公共安全热点事件", { exact: false }).count(), 5);
    const hotRows = page.locator('a[href^="/story/event-"]'); assert.equal(await hotRows.first().getAttribute("href"), "/story/event-1");
    const wide = spec.name !== "mobile";
    assert.equal(await page.getByText("+3", { exact: true }).first().isVisible(), wide);
    assert.equal(await page.getByText("同新闻", { exact: true }).isVisible(), wide);
    await page.screenshot({ path: `${artifacts}/${spec.name}.png`, fullPage: true });
    assert.equal(await paper(page).evaluate(el => el.scrollWidth <= el.clientWidth + 1), true);
    check(`${spec.name}: source composition, faces, conditional badges and paper width`);
    const firstDay = page.locator('section[data-collapsed]').first(), toggle = firstDay.getByRole("button", { name: /^收起/ }).filter({ visible: true }).last();
    await toggle.click(); await page.waitForTimeout(spec.name === "reduced" ? 30 : 280); assert.equal(await firstDay.getAttribute("data-collapsed"), "true");
    await firstDay.getByRole("button", { name: /^展开/ }).filter({ visible: true }).last().click(); await page.waitForTimeout(280); check(`${spec.name}: dated sections fold and reopen`);
    if (wide) {
      await news(page).first().getByRole("button", { name: /另有 3 家/ }).click();
      await page.waitForFunction(() => document.querySelectorAll('a[class*="groupTitle"]').length >= 3); check(`${spec.name}: desktop same-news group expands`);
    } else {
      const opener = news(page).first().getByRole("button", { name: /另有 3 家/ }); await opener.click();
      const dialog = page.getByRole("dialog", { name: "同一新闻的其他报道" }); await dialog.waitFor();
      assert.equal(await paper(page).evaluate(el => el.style.overflow), "hidden");
      await page.keyboard.press("Tab"); assert.equal(await dialog.evaluate(el => el.contains(document.activeElement)), true);
      await page.keyboard.press("/"); assert.equal(await dialog.evaluate(el => el.contains(document.activeElement)), true);
      await page.keyboard.press("Escape"); await dialog.waitFor({ state: "hidden" }); assert.equal(await opener.evaluate(el => el === document.activeElement), true);
      check("mobile: group sheet portal, focus trap, Escape and scroll unlock");
    }
    await news(page).nth(1).getByRole("button", { name: /查看图片/ }).click();
    await page.getByRole("dialog", { name: /图片/ }).waitFor(); await page.keyboard.press("/"); assert.equal(await page.getByRole("dialog", { name: /图片/ }).evaluate(el => el.contains(document.activeElement)), true); await page.keyboard.press("Escape"); await page.getByRole("dialog", { name: /图片/ }).waitFor({ state: "hidden" }); check(`${spec.name}: original-post image lightbox, quote and confined search shortcut`);
    await news(page).first().getByRole("button", { name: "收藏", exact: true }).click();
    assert.equal(await news(page).first().getByRole("button", { name: "取消收藏", exact: true }).getAttribute("aria-pressed"), "true");
    await page.locator('[data-filter="paper"]').click(); await ready(page);
    assert.equal(new URL(page.url()).searchParams.get("topic"), "paper"); assert.equal(await page.locator("#hot-topics").count(), 0); assert.equal(await page.locator('[data-phase]').getAttribute("data-phase"), "idle");
    await page.locator('[data-filter="foreign"]').click(); await ready(page); assert.equal(new URL(page.url()).searchParams.has("topic"), false);
    await page.locator('input[name="q"]').fill("警务"); await page.locator('input[name="q"]').press("Enter"); await ready(page, "/all");
    assert.equal(new URL(page.url()).searchParams.get("region"), "foreign");
    await menu(page, "/"); assert.equal(new URL(page.url()).search, ""); assert.equal(await page.locator('[data-filter="all"]').getAttribute("aria-current"), "page");
    check(`${spec.name}: independent category URLs, search handoff and menu reset`);
    if (spec.name === "desktop") {
      holdCursor = true; await end(page); await page.getByText("正在加载", { exact: true }).waitFor();
      const pendingDay = page.locator('section[data-collapsed]').first(); await pendingDay.getByRole("button", { name: /^收起/ }).filter({ visible: true }).last().click();
      holdCursor = false; releaseCursor?.(); releaseCursor = null;
      await page.waitForFunction(() => Number(document.querySelector('[data-featured-batches]')?.getAttribute('data-featured-batches')) >= 2);
      assert.equal(await pendingDay.getAttribute("data-collapsed"), "true");
      await pendingDay.getByRole("button", { name: /^展开/ }).filter({ visible: true }).last().click(); await page.waitForTimeout(280); check("desktop: append preserves a date folded while the next page is pending");
      await end(page); await page.waitForFunction(() => document.querySelector('[data-featured-batches]')?.getAttribute('data-featured-batches') === "3");
      await end(page); await page.getByRole("button", { name: "加载更多", exact: true }).waitFor(); assert.equal(await news(page).count(), 60);
      await page.getByRole("button", { name: "加载更多", exact: true }).click(); await page.getByText("已经到底了", { exact: true }).waitFor(); assert.equal(await news(page).count(), 76);
      assert.equal(new Set(await news(page).evaluateAll(nodes => nodes.map(el => el.dataset.itemId))).size, 76);
      check("desktop: three automatic batches, manual continuation and stable deduplication");
      await news(page).first().getByRole("button", { name: /另有 3 家/ }).click(); await page.locator('a[class*="groupTitle"]').first().waitFor(); await page.waitForTimeout(280);
      const item = news(page).nth(45); await item.locator("h3 a").scrollIntoViewIfNeeded();
      // Playwright click can scroll again after scrollIntoViewIfNeeded. Compare with the actual
      // departure position, captured before MainShell handles this specific article navigation.
      await page.evaluate(id => {
        window.__featuredDepartureTop = null;
        const capture = event => {
          if (event.target.closest('a')?.getAttribute('href') !== `/articles/${id}`) return;
          window.__featuredDepartureTop = document.querySelector('[data-p0-scroller]').scrollTop;
          document.removeEventListener('click', capture, true);
        };
        document.addEventListener('click', capture, true);
      }, rows[45].id);
      groupDelay = 500;
      await item.locator("h3 a").click(); await ready(page, `/articles/${rows[45].id}`); await page.goBack(); await ready(page);
      await page.waitForTimeout(850); groupDelay = 0;
      const before = await page.evaluate(() => window.__featuredDepartureTop); assert.equal(typeof before, "number");
      assert.equal(await news(page).count(), 76); assert.ok(Math.abs((await paper(page).evaluate(el => el.scrollTop)) - before) < 40, `anchor drift: ${await paper(page).evaluate(el => el.scrollTop)} versus ${before}`);
      assert.equal(await news(page).nth(45).getAttribute("data-read"), "true"); check("desktop: detail return restores cumulative list, read state and deep anchor");
      await page.clock.setSystemTime(new Date(Date.now() + 70000));
      await menu(page, "/hot"); const countBefore = requests.filter(r => r.path === "/api/v1/site/timeline").length; await page.goBack(); await ready(page);
      assert.equal(await news(page).count(), 76); assert.ok(requests.filter(r => r.path === "/api/v1/site/timeline").length > countBefore);
      check("desktop: expired list reconstructs batches before restoring position");
      await page.clock.setSystemTime(new Date());
      await menu(page, "/"); assert.equal(await news(page).count(), 20); assert.equal(await paper(page).evaluate(el => el.scrollTop), 0); check("desktop: tapping current menu refreshes the head and resets reading position");
      const beforeInvalid = requests.filter(r => r.path === "/api/v1/site/timeline" && !r.query.includes("cursor=")).length;
      cursorInvalid = true; await end(page); await page.waitForFunction(() => Number(document.querySelector('[data-featured-batches]')?.getAttribute('data-featured-batches')) >= 2);
      assert.ok(requests.filter(r => r.path === "/api/v1/site/timeline" && !r.query.includes("cursor=")).length > beforeInvalid); assert.equal(new Set(await news(page).evaluateAll(nodes => nodes.map(el => el.dataset.itemId))).size, await news(page).count()); check("desktop: invalid cursor restarts from a fresh head without duplicate cards");
      await goto(page); holdTopic = "low-altitude"; await page.locator('[data-filter="low-altitude"]').click();
      await page.waitForFunction(() => document.querySelector('[data-featured-status]')?.getAttribute('data-featured-status') === "loading");
      assert.ok(await news(page).count() > 0); assert.equal(await page.locator('[data-phase]').getAttribute("data-phase"), "idle");
      await page.locator('[data-filter="practice"]').click(); await ready(page); holdTopic = null; releaseHeld?.(); releaseHeld = null; await page.waitForTimeout(120);
      assert.equal(new URL(page.url()).searchParams.get("topic"), "practice"); assert.equal(await news(page).first().getAttribute("data-item-id"), rows[1].id); check("desktop: slow filter keeps old list, permits replacement and drops late result");
      mode = "unavailable"; await goto(page); assert.equal(await page.locator('[data-featured-status]').getAttribute("data-featured-status"), "unavailable"); assert.equal(await news(page).count(), 0);
      mode = "ready"; await page.getByRole("button", { name: "重试", exact: true }).click(); await ready(page); assert.equal(await news(page).count(), 20); check("desktop: absent API is distinct from empty and retry uses real service");
      mode = "empty"; await page.reload(); await ready(page); assert.equal(await news(page).count(), 0); assert.ok(await page.getByText("这个筛选下还没有精选内容", { exact: true }).isVisible());
      mode = "malformed"; await page.reload(); await ready(page); assert.equal(await page.locator('[data-featured-status]').getAttribute("data-featured-status"), "error");
      mode = "ready"; check("desktop: genuine empty and malformed response remain distinct");
      missingTopic = true; await goto(page, "/?topic=law"); assert.equal(await page.locator('[data-featured-status]').getAttribute("data-featured-status"), "category-unavailable"); missingTopic = false;
      await goto(page, "/?q=警务&region=foreign", "/all"); assert.equal(new URL(page.url()).searchParams.get("region"), "foreign"); check("desktop: unregistered category and legacy home search redirect");
      const proxyResponse = await page.request.get(`${origin}/api/bluepulse/site/groups/group-1/reports?topic=paper`); assert.equal(proxyResponse.headers()["cache-control"], "no-store");
      assert.equal((await page.request.get(`${origin}/api/bluepulse/site/groups/bad.id/reports`)).status(), 404);
      await goto(page); await page.locator('a[href="/story/event-1"]').click(); await ready(page, "/story/event-1"); assert.ok(await page.getByText("事件详情正在建设中", { exact: false }).isVisible()); assert.equal(await page.locator('aside a[href="/hot"]').getAttribute("aria-current"), "page"); check("desktop: proxy whitelist and no-store groups, original story destination");
      await goto(page, "/?mock=1"); assert.equal(await page.locator("h1").textContent(), "精选（演示）"); assert.equal(await news(page).first().getByRole("button", { name: "收藏", exact: true }).isVisible(), true); check("desktop: explicit demo and local state stay separate from live");
      mode = "nostore"; await goto(page); await menu(page, "/hot"); const old = requests.filter(r => r.path === "/api/v1/site/timeline").length; await page.goBack(); await ready(page); assert.ok(requests.filter(r => r.path === "/api/v1/site/timeline").length > old); mode = "ready"; check("desktop: no-store data cannot be revived from history snapshot");
    }
    await context.close();
  }
  assert.deepEqual(errors, []); await writeFile(`${artifacts}/verification.json`, JSON.stringify({ checks, errors, requests }, null, 2)); console.log(`${checks.length} featured browser checks passed`);
} catch (error) {
  const failedPage = browser?.contexts()[0]?.pages()[0];
  const state = failedPage ? await failedPage.evaluate(() => ({ url: location.href, status: document.querySelector('[data-featured-status]')?.getAttribute('data-featured-status'), phase: document.querySelector('[data-phase]')?.getAttribute('data-phase'), busy: document.querySelector('[data-p0-scroller]')?.getAttribute('aria-busy'), body: document.body.innerText.slice(0, 5000) })).catch(() => null) : null;
  if (failedPage) await failedPage.screenshot({ path: `${artifacts}/failure.png` }).catch(() => {});
  await writeFile(`${artifacts}/failure.json`, JSON.stringify({ checks, errors, requests, serverLog, state, failure: String(error), stack: error.stack }, null, 2)); throw error;
}
finally { holdTopic = null; holdCursor = false; releaseHeld?.(); releaseCursor?.(); await browser?.close(); server.kill(); await new Promise(resolve => api.close(resolve)); }
