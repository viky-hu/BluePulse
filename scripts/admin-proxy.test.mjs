import assert from "node:assert/strict";
import { test } from "node:test";
import { proxyAdmin } from "../src/app/api/bluepulse/admin/_proxy.ts";

const origin = "https://pulse.example.test";
const config = { origin, apiBase: "http://127.0.0.1:8000" };
const token = "A".repeat(43);

test("only proxies exact same-site admin operations and the admin cookie", async () => {
  const request = new Request(origin + "/api/bluepulse/admin/logout", {
    method: "POST",
    headers: { Origin: origin, Cookie: "other=private; bluepulse_admin=" + token, "X-CSRF-Token": "csrf" },
  });
  const response = await proxyAdmin(request, ["logout"], config, async (url, init) => {
    assert.equal(String(url), "http://127.0.0.1:8000/api/v1/admin/logout");
    assert.equal(init.headers.get("Cookie"), "bluepulse_admin=" + token);
    assert.equal(init.headers.get("X-CSRF-Token"), "csrf");
    return new Response(null, { status: 204, headers: { "Set-Cookie": "bluepulse_admin=; Max-Age=0" } });
  });
  assert.equal(response.status, 204);
  assert.equal(response.headers.get("Cache-Control"), "no-store");
  assert.match(response.headers.get("Set-Cookie"), /Max-Age=0/);
  const shouldNotFetch = () => assert.fail("unexpected upstream call");
  assert.equal((await proxyAdmin(request, ["private"], config, shouldNotFetch)).status, 404);
  const crossSite = new Request(request.url, { method: "POST", headers: { Origin: "https://evil.example.test" } });
  assert.equal((await proxyAdmin(crossSite, ["logout"], config, shouldNotFetch)).status, 403);
});

test("browser logout can arrive as an empty body stream without a content type", async () => {
  const request = new Request(origin + "/api/bluepulse/admin/logout", {
    method: "POST", body: new Uint8Array(),
    headers: { Origin: origin, Cookie: "bluepulse_admin=" + token, "X-CSRF-Token": "csrf" },
  });
  const response = await proxyAdmin(request, ["logout"], config, async (_url, init) => {
    assert.equal(init.body, undefined);
    return new Response(null, { status: 204 });
  });
  assert.equal(response.status, 204);
});
