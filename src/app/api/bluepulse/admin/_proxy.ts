import { randomUUID } from "node:crypto";

const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const routes = {
  GET: [
    /^(session|sources|content|feedback|runs|models|evaluations|daily|audit)$/,
    new RegExp(`^sources/${UUID}(?:/runs)?$`),
    new RegExp(`^content/${UUID}$`),
    /^feedback\/[1-9][0-9]*(?:\/screenshot)?$/,
    /^evaluations\/[1-9][0-9]*$/,
  ],
  POST: [
    /^(login|logout|stories\/merge|feedback-bans|evaluations)$/,
    new RegExp(`^content/${UUID}/(visibility|override|membership|rerun)$`),
    new RegExp(`^runs/${UUID}/requeue$`),
    /^feedback\/[1-9][0-9]*\/erase$/,
    /^receipts\/[a-f0-9]{64}\/release$/,
    /^models\/(prefilter|score|structure|understand|summarize|group|groupReview|digest|translate)$/,
    /^daily\/\d{4}-\d{2}-\d{2}\/correct$/,
  ],
  PATCH: [new RegExp(`^sources/${UUID}$`), /^feedback\/[1-9][0-9]*$/],
  DELETE: [/^feedback-bans\/[a-f0-9]{64}$/],
} satisfies Record<string, RegExp[]>;

const SESSION_COOKIE = "bluepulse_admin";
const BODY_LIMIT = 4 * 1024 * 1024;

async function readBody(request: Request): Promise<string> {
  if (!request.body) return "";
  const reader = request.body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let length = 0;
  let result = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) return result + decoder.decode();
      length += value.byteLength;
      if (length > BODY_LIMIT) {
        await reader.cancel();
        throw new RangeError("request_too_large");
      }
      result += decoder.decode(value, { stream: true });
    }
  } finally {
    reader.releaseLock();
  }
}

type Config = { origin?: string; apiBase: string; trustProxy?: boolean };

export async function proxyAdmin(request: Request, parts: string[], config: Config, fetcher: typeof fetch = fetch) {
  const requestId = randomUUID();
  const error = (status: number, code: string, message: string) => Response.json(
    { error: { code, message, request_id: requestId } },
    { status, headers: { "Cache-Control": "no-store", "X-Request-ID": requestId } },
  );
  const path = parts.join("/");
  const method = request.method as keyof typeof routes;
  if (parts.some(part => part.includes("/")) || !routes[method]?.some(pattern => pattern.test(path))) {
    return error(404, "not_found", "管理接口不存在。");
  }
  const writes = method !== "GET";
  const origin = request.headers.get("origin");
  if (writes && (!config.origin || origin !== config.origin)) {
    return error(403, "forbidden", "请从本站管理页操作。");
  }
  let upstream: URL;
  try {
    upstream = new URL(`${config.apiBase.trim().replace(/\/+$/, "")}/api/v1/admin/${path}`);
    if (!["http:", "https:"].includes(upstream.protocol) || upstream.username || upstream.password || upstream.hash || upstream.search) throw Error();
    upstream.search = new URL(request.url).search;
  } catch {
    return error(500, "invalid_api_base", "管理服务地址配置无效。");
  }
  let body: string | undefined;
  if (writes && request.body) {
    const length = request.headers.get("content-length");
    if (length && (!/^\d+$/.test(length) || Number(length) > BODY_LIMIT)) {
      return error(413, "request_too_large", "管理请求过大。");
    }
    try {
      const received = await readBody(request);
      if (received) {
        if (!/^application\/json(?:;|$)/i.test(request.headers.get("content-type") ?? "")) {
          return error(415, "invalid_request", "管理请求须为 JSON。");
        }
        body = received;
      }
    } catch (cause) {
      return cause instanceof RangeError ? error(413, "request_too_large", "管理请求过大。")
        : error(400, "invalid_request", "管理请求格式无效。");
    }
  }
  const headers = new Headers({ "X-Request-ID": requestId });
  const cookie = request.headers.get("cookie")?.split(/;\s*/).find(item => item.startsWith(SESSION_COOKIE + "="));
  if (cookie && new RegExp(`^${SESSION_COOKIE}=[A-Za-z0-9_-]{43}$`).test(cookie)) headers.set("Cookie", cookie);
  if (writes && origin) headers.set("Origin", origin);
  if (body !== undefined) headers.set("Content-Type", "application/json");
  const csrf = request.headers.get("x-csrf-token");
  if (writes && csrf) headers.set("X-CSRF-Token", csrf);
  const address = config.trustProxy ? request.headers.get("x-real-ip") : null;
  if (address) headers.set("X-Real-IP", address);
  try {
    const response = await fetcher(upstream, {
      method, headers, body, redirect: "manual", cache: "no-store",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(15_000)]),
    });
    const result = new Headers({ "Cache-Control": "no-store", "X-Request-ID": requestId, "X-Content-Type-Options": "nosniff" });
    for (const header of ["content-type", "retry-after", "x-request-id"]) {
      const value = response.headers.get(header);
      if (value) result.set(header, value);
    }
    const setCookie = response.headers.get("set-cookie");
    if ((path === "login" || path === "logout") && setCookie?.startsWith(SESSION_COOKIE + "=")) result.set("Set-Cookie", setCookie);
    return new Response([204, 205, 304].includes(response.status) ? null : response.body,
      { status: response.status, headers: result });
  } catch (cause) {
    return cause instanceof Error && cause.name === "TimeoutError"
      ? error(504, "admin_timeout", "管理请求超时，请刷新确认结果。")
      : error(503, "admin_unavailable", "管理服务暂时不可用。");
  }
}
