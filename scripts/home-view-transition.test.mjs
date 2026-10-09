import assert from "node:assert/strict";
import { requestNavigation, finishExit, finishEnter } from "../src/app/_components/home/view-transition.ts";

const initial = () => ({ phase: "idle", currentKey: "home", pending: null });
let filters = "home";
let detailRequests = 0;
const target = (key) => ({
  key, view: { kind: key },
  commit: () => { filters = key; if (key === "article") detailRequests++; },
});
const apply = (step) => { step.commit?.commit?.(); return step.state; };

let state = apply(requestNavigation(initial(), target("topic")));
assert.equal(state.phase, "exiting");
assert.equal(state.currentKey, "home");
assert.equal(filters, "home", "filters must not change before the old page exits");
state = apply(requestNavigation(state, target("article")));
state = apply(requestNavigation(state, target("search")));
assert.equal(state.pending.key, "search");
assert.equal(detailRequests, 0, "superseded article requests must never commit");
state = apply(finishExit(state));
assert.equal(state.phase, "entering");
assert.equal(state.currentKey, "search");
assert.equal(filters, "search");

state = apply(requestNavigation(state, target("history")));
state = apply(requestNavigation(state, target("account")));
assert.equal(state.phase, "entering");
assert.equal(state.currentKey, "search", "queued navigation must not interrupt the entering page");
assert.equal(filters, "search");
state = apply(finishEnter(state));
assert.equal(state.phase, "exiting");
assert.equal(state.pending.key, "account");
state = apply(finishExit(state));
state = apply(finishEnter(state));
assert.equal(state.currentKey, "account");
assert.equal(state.phase, "idle");
assert.equal(state.pending, null);
assert.equal(requestNavigation(state, target("account")).state, state, "same-page idle clicks are no-ops");

state = apply(requestNavigation(initial(), target("topic")));
state = apply(requestNavigation(state, target("home")));
const cancelled = finishExit(state);
assert.equal(cancelled.commit, undefined, "returning to the departing page must not reset its data");
assert.equal(cancelled.state.phase, "entering", "a faded-out page must still fade back in");
assert.equal(cancelled.state.currentKey, "home");
state = apply(finishEnter(cancelled.state));
assert.equal(state.phase, "idle");

state = apply(finishExit(requestNavigation(initial(), target("search")).state));
state = apply(requestNavigation(state, target("topic")));
state = apply(requestNavigation(state, target("search")));
assert.equal(finishEnter(state).state.phase, "idle", "clicking the entering page cancels a queued destination");

for (const phase of ["idle", "exiting", "entering"]) {
  state = apply(requestNavigation({ ...initial(), phase, pending: target("topic") }, target("article"), true));
  assert.equal(state.phase, "idle");
  assert.equal(state.currentKey, "article");
  assert.equal(state.pending, null);
}
assert.equal(detailRequests, 3);
assert.equal(finishExit(initial()).state.phase, "idle");
assert.equal(finishEnter(initial()).state.phase, "idle");
console.log("home navigation phase checks passed");
