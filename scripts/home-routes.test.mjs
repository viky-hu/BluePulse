import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const routes = await import("../src/app/_components/home/home-routes.ts").catch(() => null);
assert.ok(routes, "URL-driven home routing must exist");
const { parseHomeRoute, buildHomeHref, canonicalHref, entryMode } = routes;
const { MENU_SECTIONS, isMenuItemActive } = await import("../src/app/_components/home/navigation-config.ts");
const readme = readFileSync(new URL("../README.md", import.meta.url), "utf8");
const menuSelection = readme.split("具体菜单栏内容改成如下结构：")[1];
assert.ok(menuSelection, "README must contain the explicit menu selection");
const selectedSections = [];
for (const line of menuSelection.split(/\r?\n/).map(line => line.trim()).filter(Boolean)) {
  if (line.startsWith("#")) break;
  if (line.endsWith("：")) selectedSections.push([line.slice(0, -1)]);
  else { assert.ok(selectedSections.length, "menu items must follow a group label"); selectedSections.at(-1).push(line.replace(/（.*）$/, "")); }
}
assert.deepEqual(MENU_SECTIONS.map(section => [section.title, ...section.items.map(item => item.label)]), selectedSections,
  "only README's explicitly selected menus may be displayed; source-site groups are not permission to add items");
assert.equal(isMenuItemActive("/all", "/articles"), true);
assert.equal(isMenuItemActive("/all", "/articles/123"), false);
assert.equal(isMenuItemActive("/topics", "/topics/policing"), true);
assert.equal(isMenuItemActive("/topics", "/topics-other"), false);
assert.equal(isMenuItemActive("/", "/search"), false);
for (const path of ["/all", "/hot", "/daily", "/topics", "/agent", "/about", "/changelog", "/feedback"]) {
  assert.equal(parseHomeRoute(path, "").valid, true, `${path} must participate in shared-shell navigation`);
  assert.equal(entryMode(path, false), "stable", `${path} must open directly without the intro`);
}
for (const path of ["/leaderboard", "/codex-reset"]) {
  assert.equal(parseHomeRoute(path, "").valid, false, `${path} was not selected in README`);
}
assert.equal(parseHomeRoute("/all", "").filters.period, "30d", "all news keeps the library's default period");
assert.equal(parseHomeRoute("/all", "q=test&region=domestic&sort=importance&cursor=next").cursor, "next");
assert.equal(parseHomeRoute("/leaderboard/missing", "").valid, false, "unimplemented descendants must remain unknown");
assert.equal(entryMode("/", false), "intro");
assert.equal(entryMode("/", true), "stable");
assert.equal(entryMode("/starred", false), "stable", "direct links never play the intro");
const search = parseHomeRoute("/search", "q=%E8%AD%A6%E5%8A%A1&period=all&region=domestic&sort=importance&cursor=next");
assert.equal(search.kind, "search");
assert.equal(search.filters.q, "警务");
assert.equal(search.filters.period, "all");
assert.equal(search.filters.region, "domestic");
assert.equal(search.cursor, "next");
assert.equal(parseHomeRoute("/topics/policing", "topic=research").filters.topic, "policing", "the path owns a topic page's category");
assert.equal(parseHomeRoute("/articles", "").filters.period, "30d", "legacy library defaults remain compatible");
assert.equal(parseHomeRoute("/search", "period=bad&sort=bad&region=bad").filters.period, "7d");
assert.equal(parseHomeRoute("/topics/missing", "").valid, false);
assert.equal(parseHomeRoute("/articles/not-an-id", "").valid, false);
const filters = { period: "7d", q: "警务", topic: "", region: "", source: "", sourceType: "", entity: "", sort: "recent" };
assert.equal(buildHomeHref("/all", { ...filters, period: "30d" }), "/all?q=%E8%AD%A6%E5%8A%A1");
assert.equal(buildHomeHref("/all", filters), "/all?period=7d&q=%E8%AD%A6%E5%8A%A1");
assert.equal(buildHomeHref("/search", filters), "/search?q=%E8%AD%A6%E5%8A%A1", "changing filters drops the old page cursor");
assert.equal(buildHomeHref("/search", filters, { cursor: "next", mock: true }), "/search?q=%E8%AD%A6%E5%8A%A1&cursor=next&mock=1");
assert.equal(canonicalHref("/search?sort=recent&q=a"), canonicalHref("/search?q=a&sort=recent"));
console.log("home URL and entry intent checks passed");
