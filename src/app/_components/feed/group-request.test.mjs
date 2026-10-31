import assert from "node:assert/strict";
import { createServer } from "node:http";
import { test } from "node:test";
const api = await import("./group-request.ts").catch(() => null);

test("group reports use filter scope and revalidation removes withdrawn reports", async () => {
  assert.ok(api, "group request adapter is available");
  assert.equal(api.groupReportsUrl("fact /?", { region: "foreign", topic: "paper" }), "/api/bluepulse/site/groups/fact%20%2F%3F/reports?region=foreign&topic=paper");
  const server = createServer((request, response) => {
    assert.equal(request.headers["cache-control"], "no-cache");
    if (request.url === "/bad-list") return response.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify({ factId: "fact", reports: {} }));
    if (request.url === "/bad-row") return response.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify({ factId: "fact", reports: [{ id: "a", title: "Headline", timelineAt: "2026-10-30T00:00:00Z", originalUrl: "https://example.com", source: null }] }));
    response.writeHead(404).end();
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  try {
    const url = `http://127.0.0.1:${server.address().port}/reports`;
    assert.deepEqual(await api.requestGroupReports(url, new AbortController().signal, true), []);
    await assert.rejects(api.requestGroupReports(url, new AbortController().signal), /404/);
    await assert.rejects(api.requestGroupReports(url.replace("/reports", "/bad-list"), new AbortController().signal), /Invalid group reports/);
    await assert.rejects(api.requestGroupReports(url.replace("/reports", "/bad-row"), new AbortController().signal), /Invalid group reports/);
    const controller = new AbortController(); controller.abort();
    await assert.rejects(api.requestGroupReports(url, controller.signal), { name: "AbortError" });
  } finally { await new Promise(resolve => server.close(resolve)); }
});
