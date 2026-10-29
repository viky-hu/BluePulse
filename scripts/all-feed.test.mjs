import assert from "node:assert/strict";
import { test } from "node:test";
import { parseHomeRoute, buildHomeHref } from "../src/app/_components/home/home-routes.ts";

const data = await import("../src/app/all/_data.ts").catch(() => null);
test("all feed requests all time without changing legacy library and search defaults", () => {
  assert.equal(parseHomeRoute("/all", "").filters.period, "all");
  assert.equal(parseHomeRoute("/articles", "").filters.period, "30d");
  assert.equal(parseHomeRoute("/search", "").filters.period, "7d");
  assert.equal(buildHomeHref("/all", parseHomeRoute("/all", "").filters), "/all");
  assert.equal(buildHomeHref("/all", parseHomeRoute("/all", "period=30d").filters), "/all?period=30d");
  assert.equal(parseHomeRoute("/all", "q=test&sort=importance").filters.sort, "recent", "search results must match the visible latest ordering");
  assert.equal(parseHomeRoute("/all", "sort=importance").filters.sort, "importance", "old browse ordering remains available");
});
test("tab selection clears the opposite dimension and keeps search and legacy filters", () => {
  assert.ok(data, "all feed adapter must exist");
  const filters = parseHomeRoute("/all", "q=警务&topic=policing&region=foreign&source=abc&period=7d").filters;
  assert.deepEqual(data.selectAllFilter(filters, "paper"), { ...filters, topic: "paper", region: "" });
  assert.deepEqual(data.selectAllFilter(filters, "domestic"), { ...filters, topic: "", region: "domestic" });
  assert.deepEqual(data.selectAllFilter(filters, "all"), { ...filters, topic: "", region: "" });
  assert.equal(data.activeAllFilter(filters), "custom");
  const params = data.allArticleParams(data.selectAllFilter(filters, "paper"), null);
  assert.equal(params.get("limit"), "40");
  assert.equal(params.get("q"), "警务");
  assert.equal(params.get("source"), "abc");
  assert.equal(params.has("cursor"), false);
});
test("day grouping uses Beijing midnight, preserves ranked order and marks discovery dates", () => {
  assert.ok(data);
  const rows = [
    { id: "a", published_at: "2026-10-28T16:01:00Z" },
    { id: "b", published_at: "2026-10-28T15:59:00Z" },
    { id: "c", published_at: null, first_seen_at: "2026-10-28T16:02:00Z" },
    { id: "d", published_at: "invalid", first_seen_at: null },
  ];
  const groups = data.groupAllItems(rows);
  assert.deepEqual(groups.map(g => [g.day, g.items.map(i => i.id)]), [["2026-10-29", ["a"]], ["2026-10-28", ["b"]], ["2026-10-29", ["c"]], [null, ["d"]]]);
  assert.equal(new Set(groups.map(g => g.key)).size, 4);
  assert.deepEqual(data.articleMoment(rows[2]), { day: "2026-10-29", time: "00:02", at: "2026-10-28T16:02:00Z", discovered: true });
  assert.equal(data.articleMoment(rows[3]).at, null);
});
test("only registered exact categories can be queried; old broad categories stay compatible", () => {
  assert.ok(data);
  assert.equal(data.categorySupported("paper", [{ slug: "research" }]), false);
  assert.equal(data.categorySupported("paper", [{ slug: "paper" }]), true);
  assert.equal(data.categorySupported("policing", []), true);
  assert.equal(data.categorySupported("", []), true);
});
test("day headings follow source month/day copy without year or today labels", () => {
  assert.ok(data);
  assert.equal(data.dayHeading("2026-10-29", Date.parse("2026-10-29T00:00:00Z")).label, "10月29日");
});
