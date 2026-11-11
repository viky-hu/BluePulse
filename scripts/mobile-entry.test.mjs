import assert from "node:assert/strict";
import { entryMode, canonicalHref, parseHomeRoute } from "../src/app/_components/home/home-routes.ts";

assert.equal(entryMode("/", false, { mobile: true }), "stable", "first phone visit opens the feed");
assert.equal(entryMode("/", true, { mobile: true }), "stable");
assert.equal(entryMode("/", true, { mobile: true, replay: true }), "intro", "explicit replay wins over mobile and saved entry");
assert.equal(entryMode("/", false, { replay: true }), "intro");
assert.equal(entryMode("/all", false, { mobile: true, replay: true }), "stable", "replay belongs to home only");
assert.equal(entryMode("/", false), "intro", "desktop first visit is unchanged");
assert.equal(entryMode("/", true), "stable");
assert.equal(canonicalHref("/?intro=1&mock=1&topic=paper"), "/?mock=1&topic=paper", "replay intent must not fragment feed/cache/history identities");
assert.equal(parseHomeRoute("/more", "").valid, true);
console.log("9 mobile entry and route checks passed");
