import assert from "node:assert/strict";
import { test } from "node:test";

const data = await import("../src/app/about/_data.ts").catch(() => null);
const river = await import("../src/app/about/_river-drawing.ts").catch(() => null);

test("about statistics reject malformed data instead of inventing counts", () => {
  assert.ok(data, "about statistics adapter must exist");
  const partial = { sources: 0, items: null, selected: null, dailies: null, sourceKinds: {}, day: { collected: null, selected: null }, sampleSources: [], latest: [] };
  assert.deepEqual(data.parseSiteStats(partial), partial);
  assert.throws(() => data.parseSiteStats({ ...partial, sources: -1 }));
  assert.throws(() => data.parseSiteStats({ ...partial, latest: [{ id: "not-a-uuid", title: "hidden", source: "source" }] }));
  assert.throws(() => data.parseSiteStats({ error: { code: "not_found" } }));
});

test("the river remains finite at narrow paper sizes; heat-only sources never pass", () => {
  assert.ok(river, "original river geometry must be available");
  const sources = [{ name: "热度样本", kind: "rss", heatOnly: true }];
  for (const width of [180, 520, 800, 1200]) {
    const layout = river.layout(width, 260, sources);
    assert.ok(layout.strands.length >= 40);
    assert.ok(layout.paper.x + layout.paper.w <= width);
    assert.ok(layout.strands.every(strand => !strand.pass && [...strand.ys].every(Number.isFinite)));
    assert.deepEqual(river.layout(width, 260, sources), layout, "geometry must be stable between visits");
  }
});
