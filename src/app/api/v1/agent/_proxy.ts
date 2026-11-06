import { randomUUID } from 'node:crypto';

export async function proxyAgent(request: Request, suffix: '' | '/latest' | '/search', apiBase: string, fetcher: typeof fetch = fetch): Promise<Response> {
  const requestId = randomUUID();
  const fail = (status: number, code: string, message: string) => Response.json({ error: { code, message, request_id: requestId } }, { status, headers: { 'Cache-Control': 'no-store', 'X-Request-ID': requestId } });
  let url: URL;
  try {
    url = new URL(`${apiBase.trim().replace(/\/+$/, '')}/api/v1/agent${suffix}`);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw Error('invalid base');
    url.search = new URL(request.url).search;
  } catch { return fail(500, 'invalid_api_base', '数据服务地址配置无效。'); }
  try {
    const upstream = await fetcher(url, { method: 'GET', cache: 'no-store', redirect: 'manual', signal: AbortSignal.any([request.signal, AbortSignal.timeout(6_000)]), headers: { Accept: suffix ? 'application/json' : 'text/markdown', 'X-Request-ID': requestId } });
    const headers = new Headers({ 'Cache-Control': 'no-store', 'X-Request-ID': requestId });
    for (const name of ['content-type', 'retry-after', 'x-request-id']) {
      const value = upstream.headers.get(name); if (value !== null) headers.set(name, value);
    }
    return new Response([204, 205, 304].includes(upstream.status) ? null : upstream.body, { status: upstream.status, headers });
  } catch (error) {
    return error instanceof Error && error.name === 'TimeoutError'
      ? fail(504, 'upstream_timeout', '数据服务响应超时，请稍后重试。')
      : fail(503, 'upstream_unavailable', '数据服务暂时不可用，请稍后重试。');
  }
}
