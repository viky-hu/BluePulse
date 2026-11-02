import assert from "node:assert/strict";
import { navigationIntent, requestNavigation } from "../src/app/_components/home/view-transition.ts";

const mainMenu = (from, to) => navigationIntent(from, to, "main-menu");
const content = (from, to) => navigationIntent(from, to, "content");

assert.equal(mainMenu("/daily", "/hot"), "scene");
assert.equal(mainMenu("/", "/search"), "scene");
assert.equal(content("/daily", "/daily/2026-11-01"), "content");
assert.equal(content("/daily/2026-11-01", "/articles/123"), "content");
assert.equal(content("/hot", "/story/example"), "content");
assert.equal(content("/all", "/all?period=7d"), "content");
assert.equal(content("/search", "/search?q=police"), "content");
assert.equal(content("/history", "/articles/123"), "content");
assert.equal(content("/", "/?topic=security"), "content");
const interrupted = requestNavigation({ phase: "exiting", currentKey: "/daily", pending: { key: "/hot", view: "/hot" } }, { key: "/articles/123", view: "/articles/123" }, false, false, false);
assert.equal(interrupted.state.phase, "idle", "content navigation cancels an active scene transition");
assert.equal(interrupted.commit?.key, "/articles/123");
console.log("navigation intent checks passed");
