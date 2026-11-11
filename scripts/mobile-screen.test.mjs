import assert from "node:assert/strict";

const screen = await import("../src/app/_components/home/mobile/screen.ts").catch(() => null);
assert.ok(screen, "mobile screen metadata must exist");
const { mobileScreen, mobileTabAction, savedMobileTab, mobileTabState, canNoteMobileScreen } = screen;

// A prefix match must not light unrelated routes, and Story belongs to Hot.
for (const [path, want] of [
  ["/", "featured"], ["/all", "all"], ["/articles", "all"],
  ["/hot", "hot"], ["/story/police-robot", "hot"],
  ["/daily", "daily"], ["/daily/2026-11-10", "daily"],
  ["/more", "more"], ["/starred", "more"], ["/history", "more"],
  ["/agent", "more"], ["/about", "more"], ["/changelog", "more"], ["/feedback", "more"],
]) assert.equal(mobileScreen(path).tab, want, path);
assert.equal(mobileScreen("/alligator").tab, undefined, "unrelated prefixes have no explicit tab");
assert.equal(mobileScreen("/search").tab, undefined, "search keeps the source tab rather than declaring its own");
assert.equal(mobileScreen("/search").fallback, "more", "a direct search has a deterministic fallback");
for (const path of [
  "/articles/12345678-1234-1234-1234-123456789abc",
  "/articles/12345678-1234-1234-1234-123456789abc/original",
]) assert.equal(mobileScreen(path).toolbar, true, "article controls replace the tabs");
assert.equal(mobileScreen("/articles/not-a-uuid").toolbar, false);

// Each history entry owns its source; malformed or foreign values must be ignored.
assert.equal(savedMobileTab({ pulseMobileTab: "hot", __NA: true }), "hot");
assert.equal(savedMobileTab({ pulseMobileTab: "topics" }), undefined);
assert.equal(savedMobileTab(null), undefined);
const original = { __NA: true, tree: ["next-tree"], pulsePrevious: "/all", pulseMobileTab: "all" };
assert.deepEqual(mobileTabState(original, "hot"), {
  __NA: true, tree: ["next-tree"], pulsePrevious: "/all", pulseMobileTab: "hot",
});
assert.equal(original.pulseMobileTab, "all", "merging must not mutate Next's state object");
assert.equal(canNoteMobileScreen("/all?q=robot&mock=1", "/all?mock=1&q=robot"), true);
assert.equal(canNoteMobileScreen("/?mock=1", "/?intro=1&mock=1"), true,
  "the temporary intro flag must not prevent source-tab recording");
assert.equal(canNoteMobileScreen("/all?q=robot", "/search?q=robot"), false,
  "the outgoing route must not write the POP destination entry");

// Root repeat taps preserve query filters on refresh, descendants return to their tab root.
assert.equal(mobileTabAction("all", "all", "/all", 120), "scroll");
assert.equal(mobileTabAction("all", "all", "/all", 0), "refresh");
assert.equal(mobileTabAction("hot", "hot", "/story/robot", 120), "navigate");
assert.equal(mobileTabAction("daily", "hot", "/hot", 0), "navigate");
assert.equal(mobileTabAction("all", "all", "/search", 0), "navigate");
console.log("mobile screen and repeat-tab checks passed");
