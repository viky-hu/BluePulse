import assert from "node:assert/strict";
import { test } from "node:test";
import { responseDeadline } from "../src/app/_lib/http-cache.ts";

const now = Date.parse("2026-10-28T10:00:30Z");
test("a response's consumed cache age reduces its remaining browser reuse", () => {
  assert.equal(responseDeadline(new Headers({ "Cache-Control": "public, max-age=60", Date: "Wed, 28 Oct 2026 10:00:00 GMT", Age: "40" }), now), now + 20_000);
  assert.equal(responseDeadline(new Headers({ "Cache-Control": "max-age=60", Date: "Wed, 28 Oct 2026 09:59:00 GMT" }), now), 0);
});
test("absolute server deadlines and no-cache override the local fallback", () => {
  assert.equal(responseDeadline(new Headers({ "X-Accel-Expires": `@${(now + 12_000) / 1000}` }), now), now + 12_000);
  for (const policy of ["no-store", "public, no-cache", 'no-cache="Set-Cookie"', "max-age=0"]) {
    assert.equal(responseDeadline(new Headers({ "Cache-Control": policy }), now), 0);
  }
  assert.equal(responseDeadline(new Headers({ "X-Accel-Expires": "0" }), now), 0);
  assert.equal(responseDeadline(new Headers({ "X-Accel-Expires": "@NaN" }), now), 0);
  assert.equal(responseDeadline(new Headers(), now), now + 60_000);
});
