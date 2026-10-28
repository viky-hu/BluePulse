import { randomUUID } from "node:crypto";
type Config = { enabled: boolean; apiBase: string; trustProxy?: boolean; publicOrigin?: string };
const MAX_BODY = 12 * 1024 * 1024;
/** Exact anonymous multipart write boundary; FastAPI owns durable receipt and image validation. */
export async function proxyFeedback(request: Request, config: Config, fetcher: typeof fetch = fetch): Promise<Response> {
  const requestId = randomUUID();
  const error = (status: number, code: string, message: string) => Response.json({ error: { code, message, request_id: requestId } }, { status, headers: { "Cache-Control": "no-store", "X-Request-ID": requestId } });
  if (!config.enabled) return error(503, "feedback_not_connected", "反馈接收服务尚未接入，请保留草稿或联系网站负责人。");
  const origin = request.headers.get("origin");
  let publicOrigin: string;
  try {
    const url = new URL(request.url), host = request.headers.get("host");
    // Next can construct request.url from its internal listener. Host handles direct aliases;
    // an explicit public origin handles TLS termination without trusting arbitrary forwarded headers.
    if (host && !/^[a-z\d.\-:[\]]+$/i.test(host)) throw Error();
    const publicUrl = new URL(config.publicOrigin || (host ? `${url.protocol}//${host}` : url.origin));
    if (!["http:", "https:"].includes(publicUrl.protocol) || publicUrl.username || publicUrl.password || publicUrl.pathname !== "/" || publicUrl.search || publicUrl.hash) throw Error();
    publicOrigin = publicUrl.origin;
  } catch { return error(500, "invalid_public_origin", "本站公开地址配置无效。"); }
  if (origin && origin !== publicOrigin) return error(403, "forbidden", "请从本站反馈页提交。");
  const contentType = request.headers.get("content-type") ?? "";
  if (!/^multipart\/form-data\b/i.test(contentType) || !/boundary=/i.test(contentType)) return error(400, "invalid_request", "请使用反馈表单提交文字和截图。");
  const length = request.headers.get("content-length");
  if (length && (!/^\d+$/.test(length) || Number(length) > MAX_BODY)) return error(413, "request_too_large", "反馈请求过大，请缩小截图后重试。");
  let upstream: URL;
  try {
    upstream = new URL(`${config.apiBase.trim().replace(/\/+$/, "")}/api/v1/site/feedback`);
    if (!["http:", "https:"].includes(upstream.protocol) || upstream.username || upstream.password || upstream.search || upstream.hash) throw Error();
  } catch { return error(500, "invalid_api_base", "反馈服务地址配置无效。"); }
  const reader = request.body?.getReader(), chunks: Uint8Array[] = [];
  let size = 0;
  try {
    if (reader) for (;;) {
      const next = await reader.read(); if (next.done) break;
      size += next.value.byteLength;
      if (size > MAX_BODY) { await reader.cancel(); return error(413, "request_too_large", "反馈请求过大，请缩小截图后重试。"); }
      chunks.push(next.value);
    }
  } catch { return error(400, "invalid_request", "反馈上传中断，请重试。"); }
  finally { reader?.releaseLock(); }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  const headers = new Headers({ "Content-Type": contentType, Accept: "application/json", "X-Request-ID": requestId });
  const agent = request.headers.get("user-agent"); if (agent) headers.set("User-Agent", agent);
  // Only enable behind an edge that strips client-supplied forwarding headers and writes x-real-ip.
  if (config.trustProxy) { const ip = request.headers.get("x-real-ip"); if (ip) headers.set("X-Real-IP", ip); }
  try {
    const response = await fetcher(upstream, { method: "POST", headers, body: bytes, cache: "no-store", redirect: "manual", signal: AbortSignal.any([request.signal, AbortSignal.timeout(15_000)]) });
    const responseHeaders = new Headers({ "Cache-Control": "no-store", "X-Request-ID": requestId });
    for (const name of ["content-type", "retry-after", "x-request-id"]) { const value = response.headers.get(name); if (value) responseHeaders.set(name, value); }
    return new Response(response.body, { status: response.status, headers: responseHeaders });
  } catch (cause) {
    return error(cause instanceof Error && cause.name === "TimeoutError" ? 504 : 503, "feedback_result_unknown", "暂时无法确认提交结果，请保留草稿，避免连续重复发送。");
  }
}
