import assert from 'node:assert/strict';
import { test } from 'node:test';
const contract = await import('../src/app/agent/_contract.ts').catch(() => null);
const proxy = await import('../src/app/api/v1/agent/_proxy.ts').catch(() => null);

test('configured origin is fixed, credential-free and never inferred from Host', () => {
  assert.ok(contract, 'Agent contract exists');
  for (const value of [undefined, '', 'https://u:p@pulse.example', 'https://pulse.example/path', 'https://pulse.example/a/..', 'https://pulse.example\\path', 'javascript:alert(1)', 'https://pulse.example?q=1', 'https://pulse.example/#x']) assert.equal(contract.siteOrigin(value), null);
  assert.equal(contract.siteOrigin('http://127.0.0.1:3000/'), 'http://127.0.0.1:3000');
  assert.equal(contract.siteOrigin('https://pulse.example'), 'https://pulse.example');
});

test('proxy preserves Markdown bytes, errors, query encoding, no-store and request IDs without forwarding credentials', async () => {
  assert.ok(proxy, 'Agent proxy exists');
  const request = new Request('http://local/api/v1/agent/search?q=%E8%AD%A6%E5%8A%A1&window=all&limit=10', { headers: { cookie: 'private=1', authorization: 'Bearer private', host: 'attacker.example' } });
  const response = await proxy.proxyAgent(request, '/search', 'http://upstream', async (url, init) => {
    assert.equal(String(url), 'http://upstream/api/v1/agent/search?q=%E8%AD%A6%E5%8A%A1&window=all&limit=10');
    assert.equal(init.cache, 'no-store');
    const headers = new Headers(init.headers);
    assert.equal(headers.has('cookie'), false); assert.equal(headers.has('authorization'), false); assert.equal(headers.has('host'), false);
    return new Response('稍后再试', {status: 429, headers: { 'Content-Type': 'text/markdown; charset=utf-8', 'Retry-After': '60', 'X-Request-ID': 'backend-1', 'Cache-Control': 'public, max-age=600' }});
  });
  assert.equal(response.status, 429); assert.equal(await response.text(), '稍后再试');
  assert.match(response.headers.get('content-type'), /text\/markdown/);
  assert.equal(response.headers.get('retry-after'), '60'); assert.equal(response.headers.get('x-request-id'), 'backend-1'); assert.equal(response.headers.get('cache-control'), 'no-store');
});

test('proxy distinguishes bad configuration, disconnect and timeout from empty results', async () => {
  assert.ok(proxy);
  const request = new Request('http://local/api/v1/agent');
  for (const [error, status, code] of [[new Error('disconnect'), 503, 'upstream_unavailable'], [new DOMException('late', 'TimeoutError'), 504, 'upstream_timeout']]) {
    const response = await proxy.proxyAgent(request, '', 'http://upstream', async () => { throw error; });
    assert.equal(response.status, status); assert.equal((await response.json()).error.code, code); assert.equal(response.headers.get('cache-control'), 'no-store');
  }
  assert.equal((await proxy.proxyAgent(request, '', 'invalid', async () => { throw Error('not reached'); })).status, 500);
});

test('JSON probe accepts a real empty response but rejects an unrelated health response', () => {
  assert.ok(contract);
  assert.equal(contract.isAgentList({ schema_version: 1, query: {kind: 'latest', window: '7d', limit: 10, q: null, sort_basis: 'source_publication_then_first_seen'}, items: [] }, 'latest'), true);
  assert.equal(contract.isAgentList({status: 'ok'}, 'latest'), false);
  assert.equal(contract.isAgentList({schema_version: 1, query: {kind: 'search'}, items: []}, 'latest'), false);
});
