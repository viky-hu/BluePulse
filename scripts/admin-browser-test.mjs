import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { createServer } from "node:net";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const { chromium } = await import(pathToFileURL(process.env.PULSE_PLAYWRIGHT_MODULE ??
  "C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs").href);
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAE0lEQVR4nGNkaGBgYGBgAhEMDAAGKgCE2O/yUgAAAABJRU5ErkJggg==", "base64");
const password = randomUUID();
const output = resolve("test-results", "admin-browser-" + randomUUID());
await mkdir(output, { recursive: true });

async function localPort() {
  const listener = createServer();
  await new Promise((accept, reject) => listener.once("error", reject).listen(0, "127.0.0.1", accept));
  const port = listener.address().port;
  await new Promise(accept => listener.close(accept));
  return port;
}

const apiPort = await localPort();
const webPort = await localPort();
const apiOrigin = `http://127.0.0.1:${apiPort}`;
const origin = `http://127.0.0.1:${webPort}`;
const env = { ...process.env,
  BLUEPULSE_DATABASE_URL: "sqlite:///" + resolve(output, "isolated.db").replaceAll("\\", "/"),
  BLUEPULSE_SITE_ORIGIN: origin,
  BLUEPULSE_API_URL: apiOrigin,
  BLUEPULSE_ADMIN_PASSWORD: password,
  BLUEPULSE_ADMIN_SESSION_SECRET: randomUUID() + randomUUID(),
  BLUEPULSE_FEEDBACK_ENABLED: "1",
  BLUEPULSE_TRUST_PROXY: "0",
};
const backend = resolve("backend");
const python = process.env.PULSE_TEST_PYTHON ?? resolve("backend/.venv/Scripts/python.exe");
const setup = spawnSync(python, ["-m", "bluepulse_backend.cli", "initialize"], { cwd: backend, env, encoding: "utf8", windowsHide: true });
assert.equal(setup.status, 0, setup.error?.message ?? setup.stderr);

const children = [];
let logs = "", browser;
function service(executable, args, cwd) {
  const child = spawn(executable, args, { cwd, env, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] });
  children.push(child);
  child.on("error", error => { logs += error.message; });
  child.stdout.on("data", chunk => { logs += chunk.toString(); });
  child.stderr.on("data", chunk => { logs += chunk.toString(); });
}
async function ready(url) {
  for (let attempt = 0; attempt < 100; attempt++) {
    try { if ((await fetch(url, { signal: AbortSignal.timeout(1200) })).ok) return; } catch {}
    await new Promise(accept => setTimeout(accept, 200));
  }
  throw Error("服务未就绪\n" + logs);
}

try {
  service(python, ["-m", "uvicorn", "bluepulse_backend.api:app", "--host", "127.0.0.1", "--port", String(apiPort)], backend);
  await ready(apiOrigin + "/api/v1/health/ready");
  service(process.execPath, ["node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", String(webPort)], process.cwd());
  await ready(origin + "/admin");
  browser = await chromium.launch({ headless: true });

  for (const [name, width, height, reducedMotion] of [
    ["desktop", 1360, 760, "no-preference"],
    ["mobile", 390, 844, "no-preference"],
    ["reduced", 1360, 760, "reduce"],
  ]) {
    const context = await browser.newContext({ viewport: { width, height }, reducedMotion });
    const page = await context.newPage();
    const feedback = `隔离反馈验收 ${name}`;
    await page.goto(origin + "/feedback");
    await page.getByLabel("想说点什么？").fill(feedback);
    if (name === "desktop") {
      await page.getByLabel("选择反馈截图").setInputFiles({ name: "capture.png", mimeType: "image/png", buffer: png });
    }
    await page.getByRole("button", { name: "发送反馈", exact: true }).click();
    await page.getByRole("heading", { name: "收到了，谢谢你" }).waitFor();

    await page.goto(origin + "/admin/feedback");
    assert.equal((await page.request.get(origin + "/api/bluepulse/admin/feedback")).status(), 401);
    await page.getByLabel("管理员密码").fill(password);
    await page.getByRole("button", { name: "登录", exact: true }).click();
    const entry = page.locator("details").filter({ hasText: feedback });
    await entry.locator("summary").click();
    if (name === "desktop") {
      const screenshot = await entry.getByRole("link", { name: "打开私有截图" }).getAttribute("href");
      const image = await page.request.get(origin + screenshot);
      assert.equal(image.headers()["content-type"], "image/png");
      assert.deepEqual(await image.body(), png);
    }
    assert.equal((await page.request.post(origin + "/api/bluepulse/admin/logout", {
      headers: { Origin: origin },
    })).status(), 403);
    await entry.getByLabel("处理状态").selectOption("resolved");
    await entry.getByRole("button", { name: "保存处理记录" }).click();
    await entry.locator("summary").filter({ hasText: "resolved" }).waitFor();
    await page.getByRole("button", { name: "退出登录" }).click();
    await page.getByLabel("管理员密码").waitFor();
    assert.equal((await page.request.get(origin + "/api/bluepulse/admin/feedback")).status(), 401);
    console.log(`PASS ${name} anonymous feedback, login, CSRF, private handling, logout`);
    await context.close();
  }
} finally {
  if (browser) await browser.close();
  for (const child of children.reverse()) child.kill();
}
