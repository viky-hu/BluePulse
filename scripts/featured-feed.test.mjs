import assert from "node:assert/strict";
import { test } from "node:test";
const data = await import("../src/app/_components/featured/_data.ts").catch(() => null);

test("timeline requests the selected read layer with only its scope and opaque cursor", () => {
  assert.ok(data, "featured timeline adapter is implemented");
  assert.equal(data.timelineUrl({ region: "foreign", topic: "" }, "opaque/+="), "/api/bluepulse/site/timeline?region=foreign&cursor=opaque%2F%2B%3D&limit=20");
  assert.equal(data.timelineUrl({ region: "", topic: "paper" }), "/api/bluepulse/site/timeline?topic=paper&limit=20");
});
test("appending pages deduplicates cards, keeps hot head, and cannot extend any batch deadline", () => {
  assert.ok(data);
  const a = { key: "fact-a", anchorAt: "2026-10-29T01:00:00Z" }, b = { key: "fact-b", anchorAt: "2026-10-28T01:00:00Z" };
  const first = { cards: [a], nextCursor: "second", hot: [{ rank: 1 }], dayCounts: { "2026-10-29": 6 }, expiresAt: 3000, batches: 1, collapsed: ["2026-10-29"] };
  const page = { cards: [a, b], nextCursor: null, hot: null, dayCounts: { "2026-10-28": 4 }, expiresAt: 6000 };
  const merged = data.appendTimeline(first, page);
  assert.deepEqual(merged.cards, [a, b]); assert.equal(merged.expiresAt, 3000); assert.equal(merged.nextCursor, null);
  assert.deepEqual(merged.hot, [{ rank: 1 }]); assert.deepEqual(merged.collapsed, ["2026-10-29"]);
  assert.deepEqual(merged.dayCounts, { "2026-10-29": 6, "2026-10-28": 4 }); assert.equal(merged.batches, 2);
  assert.equal(data.appendTimeline(first, { ...page, expiresAt: 0 }).expiresAt, 0);
});
test("timeline dates are anchored by the server rather than the representative article timestamp", () => {
  assert.ok(data);
  const groups = data.groupTimeline([
    { key: "a", anchorAt: "2026-10-29T16:00:00Z", item: { published_at: "2026-10-20T00:00:00Z" } },
    { key: "b", anchorAt: "2026-10-29T15:59:00Z", item: {} },
  ]);
  assert.deepEqual(groups.map(g => [g.day, g.cards.map(c => c.key)]), [["2026-10-30", ["a"]], ["2026-10-29", ["b"]]]);
});
test("hot destinations preserve story first, then article, then ranking", () => {
  assert.ok(data);
  assert.equal(data.hotHref({ storyPublicId: "event-1", itemId: "article-1" }), "/story/event-1");
  assert.equal(data.hotHref({ storyPublicId: null, itemId: "article-1" }), "/articles/article-1");
  assert.equal(data.hotHref({ storyPublicId: null, itemId: null }), "/hot");
});
test("missing day totals and malformed data are errors rather than fabricated empty feeds", () => {
  assert.ok(data);
  const filters = { region: "", topic: "" };
  assert.throws(() => data.parseTimeline({ filters, cards: null, nextCursor: null, hot: null, dayCounts: {} }, filters));
  assert.deepEqual(data.parseTimeline({ filters, cards: [], nextCursor: null, hot: null, dayCounts: {} }, filters).cards, []);
  assert.throws(() => data.parseTimeline({ filters: { ...filters, topic: "paper" }, cards: [], nextCursor: null, hot: null, dayCounts: {} }, filters));
});
test("conditional card payloads must be well formed and dated totals are never inferred", () => {
  assert.ok(data);
  const filters = { region: "", topic: "" };
  const card = { key: "fact-1", anchorAt: "2026-10-30T00:00:00Z", group: null, item: { id: "f3300000-0000-4000-8000-000000000001", title: "公开材料", url: "https://example.com/1", source: { name: "来源" }, selected: true } };
  const response = { filters, cards: [card], nextCursor: null, hot: null, dayCounts: { "2026-10-30": 8 } };
  assert.equal(data.parseTimeline(response, filters).dayCounts["2026-10-30"], 8);
  assert.throws(() => data.parseTimeline({ ...response, dayCounts: {} }, filters));
  assert.throws(() => data.parseTimeline({ ...response, cards: [{ ...card, item: { ...card.item, channel: "x", x: { media: null } } }] }, filters));
  assert.throws(() => data.parseTimeline({ ...response, cards: [{ ...card, item: { ...card.item, sameEvent: { id: "wrong", title: "其他报道" } } }] }, filters));
});
