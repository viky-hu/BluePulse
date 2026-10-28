import assert from "node:assert/strict";
import { test } from "node:test";
import { createTimedPageCache } from "../src/app/_lib/page-cache.ts";

test("reuses a successful page until its freshness deadline, then reloads it", async () => {
  let now = 1_000;
  let loads = 0;
  const cache = createTimedPageCache(60_000, 16, () => now);
  const load = async () => ({ revision: ++loads });

  assert.deepEqual(await cache.load("/all", load), { revision: 1 });
  now += 59_999;
  assert.deepEqual(cache.get("/all"), { revision: 1 });
  assert.deepEqual(await cache.load("/all", load), { revision: 1 });
  assert.equal(loads, 1);

  now += 1;
  assert.equal(cache.get("/all"), undefined);
  assert.deepEqual(await cache.load("/all", load), { revision: 2 });
  assert.equal(loads, 2);
});

test("coalesces an intent prefetch with the page request", async () => {
  const cache = createTimedPageCache(60_000, 16, () => 1_000);
  let loads = 0;
  let resolve;
  const pending = new Promise(done => { resolve = done; });
  const prefetched = cache.load("/search?q=police", () => { loads++; return pending; });
  const navigated = cache.load("/search?q=police", () => { loads++; return { result: "duplicate" }; });

  await Promise.resolve();
  assert.equal(loads, 1);
  resolve({ result: "ready" });
  assert.deepEqual(await prefetched, { result: "ready" });
  assert.deepEqual(await navigated, { result: "ready" });
  assert.deepEqual(cache.get("/search?q=police"), { result: "ready" });
});

test("keeps query variants separate and does not cache failed or rejected results", async () => {
  const cache = createTimedPageCache(60_000, 16, () => 1_000);
  let loads = 0;
  const load = async value => ({ value, revision: ++loads });

  assert.deepEqual(await cache.load("/all?period=7d", () => load("7d")), { value: "7d", revision: 1 });
  assert.deepEqual(await cache.load("/all?period=30d", () => load("30d")), { value: "30d", revision: 2 });
  assert.deepEqual(cache.get("/all?period=7d"), { value: "7d", revision: 1 });

  await cache.load("/all?q=unavailable", async () => ({ ok: false }), { shouldCache: value => value.ok });
  assert.equal(cache.get("/all?q=unavailable"), undefined);
  await assert.rejects(cache.load("/all?q=network-error", async () => { throw new Error("offline"); }));
  assert.equal(cache.get("/all?q=network-error"), undefined);
});

test("forced refresh replaces fresh data without letting an older request overwrite it", async () => {
  const cache = createTimedPageCache(60_000, 16, () => 1_000);
  await cache.load("/all", async () => "old");
  let resolveOld;
  const oldPending = cache.load("/all?q=pending", () => new Promise(done => { resolveOld = done; }));
  const fresh = await cache.load("/all?q=pending", async () => "fresh", { force: true });
  resolveOld("stale");

  assert.equal(fresh, "fresh");
  assert.equal(await oldPending, "stale");
  assert.equal(cache.get("/all?q=pending"), "fresh");
  assert.equal(await cache.load("/all", async () => "should not load"), "old");
});

test("evicts the least recently used page after reaching the page limit", async () => {
  const cache = createTimedPageCache(60_000, 2, () => 1_000);
  await cache.load("/a", async () => "a");
  await cache.load("/b", async () => "b");
  assert.equal(cache.get("/a"), "a");
  await cache.load("/c", async () => "c");

  assert.equal(cache.get("/b"), undefined);
  assert.equal(cache.get("/a"), "a");
  assert.equal(cache.get("/c"), "c");
});

test("an upstream deadline is not renewed by a load or a revisit", async () => {
  let now = 1_000;
  const cache = createTimedPageCache(60_000, 16, () => now);
  await cache.load("/all", async () => ({ expiresAt: 2_000 }), { expiresAt: value => value.expiresAt });
  now = 1_999;
  assert.deepEqual(cache.get("/all"), { expiresAt: 2_000 });
  now = 2_000;
  assert.equal(cache.get("/all"), undefined, "server deadline must take precedence over the local 60 seconds");
});

test("an uncacheable result is delivered but never reused", async () => {
  const cache = createTimedPageCache(60_000, 16, () => 1_000);
  const result = await cache.load("/all", async () => ({ expiresAt: 0 }), { expiresAt: value => value.expiresAt });
  assert.deepEqual(result, { expiresAt: 0 });
  assert.equal(cache.get("/all"), undefined);
});
