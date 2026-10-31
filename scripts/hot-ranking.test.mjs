import assert from "node:assert/strict";
import { test } from "node:test";

const moduleAt = new URL("../src/app/hot/_data.ts", import.meta.url);
const read = () => import(moduleAt.href);
const entry = () => ({ rank: 2, story: { publicId: "event-2", title: "公开测试" }, heat: 12.5, trend: "unknown", trendPct: null, badges: [], participantCount: 2, sourceCount: 3, sourceNames: ["公开来源"], participants: [{ name: "公开来源", kind: "editorial" }], spark: [null, 2, 4, null, 3], summary: null, latest: null, cover: null });
test("hot responses keep published rank gaps and nullable observation hours", async () => {
  const { parseHot } = await read();
  const input = { computedAt: "2026-10-31T03:00:00Z", windowHours: 48, entries: [entry()] };
  assert.deepEqual(parseHot(input), input);
  assert.deepEqual(parseHot({ computedAt: null, windowHours: 48, entries: [] }).entries, []);
});
test("malformed heat, participants and conditional media never masquerade as an empty ranking", async () => {
  const { parseHot } = await read();
  for (const patch of [{ heat: NaN }, { trend: "other" }, { trend: ["up"] }, { spark: [1, "2", null] }, { participants: [{ name: "机构", kind: "unknown" }] }, { participants: [{ name: "机构", kind: ["editorial"] }] }, { cover: { url: "javascript:alert(1)", width: null, height: null } }, { badges: ["other"] }, { badges: [["new"]] }, { story: { publicId: "../secret", title: "新闻" } }, { summary: undefined }]) {
    assert.throws(() => parseHot({ computedAt: null, windowHours: 48, entries: [{ ...entry(), ...patch }] }));
  }
  assert.throws(() => parseHot({ entries: [] }));
});
test("repeated story identities are rejected without sorting or inventing ranks", async () => {
  const { parseHot } = await read();
  assert.throws(() => parseHot({ computedAt: null, windowHours: 48, entries: [entry(), { ...entry(), rank: 3 }] }));
});
test("observation gaps split the original curve and singletons add no fabricated filled area", async () => {
  const { observedRuns, curvePath, areaPath } = await import("../src/app/hot/curve.ts");
  assert.deepEqual(observedRuns([null, 1, 2, null, 4, null]), [[1, 2], [4]]);
  assert.equal(curvePath([[10, 20]]), "M10 20h0");
  assert.equal(areaPath([[10, 20]], 100), "");
  assert.equal(curvePath([[0, 100], [100, 0]]), "M0 100C33.33 66.67 66.67 33.33 100 0");
});
test("ranking reuse never renews upstream age or exceeds thirty seconds", async () => {
  const { hotDeadline } = await import("../src/app/hot/_cache.ts");
  const now = Date.parse("2026-10-31T03:00:20Z");
  assert.equal(hotDeadline(new Headers({ "Cache-Control": "max-age=60" }), now), now + 30_000);
  assert.equal(hotDeadline(new Headers({ "Cache-Control": "max-age=30", "Age": "25" }), now), now + 5_000);
  assert.equal(hotDeadline(new Headers({ "X-Accel-Expires": `@${(now + 2000) / 1000}` }), now), now + 2_000);
  assert.equal(hotDeadline(new Headers({ "Cache-Control": "no-store" }), now), 0);
});
test("forced refresh, failures and mock data remain independent of a cached successful read", async t => {
  const { loadHot, getCachedHot } = await import("../src/app/hot/_cache.ts");
  let calls = 0, status = 200;
  t.mock.method(globalThis, "fetch", async () => { calls++; return Response.json(status === 200 ? { computedAt: null, windowHours: 48, entries: [] } : {}, { status, headers: { "Cache-Control": "max-age=60" } }); });
  const key = "/hot?test=cache";
  assert.equal((await loadHot(key, false)).status, "ready");
  await loadHot(key, false); assert.equal(calls, 1);
  await loadHot(key, false, true); assert.equal(calls, 2);
  status = 404; assert.equal((await loadHot(key, false, true)).status, "unavailable");
  assert.equal(getCachedHot(key, false), null);
  await loadHot(key, false); assert.equal(calls, 4);
  const demo = await loadHot(key, true); assert.equal(demo.hot.entries.length, 10); assert.equal(calls, 4);
  assert.equal(getCachedHot(key, false), null);
});
test("prefetched query order cannot leave the canonical route permanently loading", async () => {
  const { loadHot, getCachedHot } = await import("../src/app/hot/_cache.ts");
  await loadHot("/hot?mock=1&a=1", true);
  assert.equal(getCachedHot("/hot?a=1&mock=1", true).key, "/hot?a=1&mock=1");
});
