import assert from "node:assert/strict";
import { writeFile } from "node:fs/promises";

const port = process.env.CHROME_DEBUG_PORT ?? "9223";
const base = `http://127.0.0.1:${port}`;
const pageUrl = process.env.HOME_TEST_URL ?? "http://localhost:3000/?mock=1";
const mode = process.env.HOME_TEST_MODE ?? "desktop";
const target = await fetch(`${base}/json/new?${encodeURIComponent(pageUrl)}`, { method: "PUT" }).then((response) => response.json());
const socket = new WebSocket(target.webSocketDebuggerUrl);
const pending = new Map();
let commandId = 0;

await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});
socket.addEventListener("message", ({ data }) => {
  const message = JSON.parse(data);
  if (!message.id || !pending.has(message.id)) return;
  const { resolve, reject } = pending.get(message.id);
  pending.delete(message.id);
  if (message.error) reject(new Error(message.error.message));
  else resolve(message.result);
});

function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++commandId;
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
}

async function evaluate(expression) {
  const response = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  if (response.exceptionDetails) throw new Error(response.exceptionDetails.text);
  return response.result.value;
}

async function until(expression, timeout = 30000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await evaluate(expression)) return;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  const diagnostic = await evaluate("({ phase: document.querySelector('main[data-phase]')?.dataset.phase, button: document.querySelector('[data-scroll-cue-shell] button')?.outerHTML, body: document.body?.innerText.slice(0, 200) })");
  throw new Error(`Timed out waiting for ${expression}: ${JSON.stringify(diagnostic)}`);
}

try {
  await send("Runtime.enable");
  await send("Page.enable");
  if (mode === "mobile") {
    await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
    await send("Emulation.setTouchEmulationEnabled", { enabled: true });
  } else {
    await send("Emulation.setDeviceMetricsOverride", { width: 1360, height: 760, deviceScaleFactor: 1, mobile: false });
  }
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: mode === "reduced" ? "reduce" : "no-preference" }] });
  await send("Page.reload", { ignoreCache: true });
  await until("document.querySelector('[data-scroll-cue-shell] button:not(:disabled)') !== null", 45000);
  await evaluate("document.querySelector('[data-scroll-cue-shell] button').click()");
  await until("document.querySelector('[data-home-view=home][data-phase=idle]') && getComputedStyle(document.querySelector('[data-home-view=home]')).opacity === '1'", 30000);

  await evaluate(`(() => {
    window.__homeFrames = [];
    window.__recordHomeFrames = true;
    function sample() {
      if (!window.__recordHomeFrames) return;
      const stage = document.querySelector('[data-home-view]');
      if (stage) window.__homeFrames.push({
        key: stage.dataset.homeView,
        phase: stage.dataset.phase,
        opacity: Number(getComputedStyle(stage).opacity),
        visible: getComputedStyle(stage).visibility,
      });
      requestAnimationFrame(sample);
    }
    requestAnimationFrame(sample);
  })()`);

  const click = async (label) => {
    if (mode === "mobile") {
      await evaluate("document.querySelector('button[aria-label=\"打开菜单\"]').click()");
      await until("Number(getComputedStyle(document.querySelector('aside[aria-label=\"主菜单\"]')).opacity) > 0.9");
    }
    await evaluate(`(() => {
    const button = [...document.querySelectorAll('aside button')].find((item) => item.textContent.trim() === ${JSON.stringify(label)});
    if (!button) throw new Error('Missing menu button: ${label}');
    button.click();
  })()`);
  };

  await click("警务应用");
  await new Promise((resolve) => setTimeout(resolve, 55));
  await click("搜索");
  await new Promise((resolve) => setTimeout(resolve, 55));
  await click("账号");
  await until("document.querySelector('[data-home-view=account][data-phase=idle]') !== null");
  await evaluate("new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))");

  await click("搜索");
  if (mode !== "reduced") {
    await until("document.querySelector('[data-home-view=search][data-phase=entering]') !== null");
    await click("警务应用");
    await click("搜索");
  }
  await until("document.querySelector('[data-home-view=search][data-phase=idle]') !== null");
  const frames = await evaluate("window.__recordHomeFrames = false; window.__homeFrames");
  for (const key of ["account", "search"]) {
    const first = frames.find((frame) => frame.key === key);
    assert.ok(first, `${key} was never rendered`);
    if (mode === "reduced") {
      assert.equal(first.phase, "idle", `${key} should switch without animation`);
      assert.equal(first.opacity, 1, `${key} should remain visible`);
    } else {
      assert.ok(first.opacity < 0.95 || first.visible === "hidden", `${key} first appeared fully visible: ${JSON.stringify(first)}`);
      assert.ok(frames.some((frame) => frame.key === key && frame.phase === "entering" && frame.opacity > 0.15 && frame.opacity < 1), `${key} skipped its fade in`);
    }
  }
  assert.ok(!frames.some((frame) => frame.key.startsWith("topic:") && frame.phase === "entering"), "superseded topic became visible");
  if (process.env.HOME_TEST_SCREENSHOT) {
    const screenshot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    await writeFile(process.env.HOME_TEST_SCREENSHOT, Buffer.from(screenshot.data, "base64"));
  }
  console.log(`${mode} browser transitions passed: ${frames.length} frames, final view search`);
} finally {
  const closed = new Promise((resolve) => socket.addEventListener("close", resolve, { once: true }));
  socket.close();
  await closed;
}
