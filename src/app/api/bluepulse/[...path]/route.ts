import { randomUUID } from "node:crypto";

export const dynamic = "force-dynamic";

const UPSTREAM_TIMEOUT_MS = 6_000;
const ARTICLE_ID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

function isAllowedPath(path: string[]): boolean {
  if (path.length === 2 && path[0] === "home" && path[1] === "featured") {
    return true;
  }

  if (path.length === 1 && (path[0] === "taxonomy" || path[0] === "sources")) {
    return true;
  }

  return (
    (path.length === 1 && path[0] === "articles") ||
    (path.length === 2 &&
      path[0] === "articles" &&
      ARTICLE_ID_PATTERN.test(path[1]))
  );
}

function jsonError(
  status: number,
  code: string,
  message: string,
  requestId: string,
): Response {
  return Response.json(
    { error: { code, message, request_id: requestId } },
    { status, headers: { "X-Request-ID": requestId } },
  );
}

export async function GET(request: Request, context: RouteContext) {
  const requestId = randomUUID();
  const { path } = await context.params;

  if (!isAllowedPath(path)) {
    return jsonError(404, "not_found", "请求的 API 路径不存在。", requestId);
  }

  const apiBase = (process.env.BLUEPULSE_API_URL ?? "http://127.0.0.1:8000")
    .trim()
    .replace(/\/+$/, "");

  let upstreamUrl: URL;
  try {
    upstreamUrl = new URL(`${apiBase}/api/v1/${path.join("/")}`);
    upstreamUrl.search = new URL(request.url).search;
  } catch {
    return jsonError(
      500,
      "invalid_api_base",
      "数据服务地址配置无效。",
      requestId,
    );
  }

  try {
    const upstream = await fetch(upstreamUrl, {
      method: "GET",
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
      headers: {
        Accept: request.headers.get("accept") ?? "application/json",
        "X-Request-ID": request.headers.get("x-request-id") ?? requestId,
      },
    });

    const headers = new Headers();
    for (const name of [
      "content-type",
      "cache-control",
      "retry-after",
      "location",
      "x-request-id",
    ]) {
      const value = upstream.headers.get(name);
      if (value !== null) headers.set(name, value);
    }
    if (!headers.has("x-request-id")) headers.set("x-request-id", requestId);

    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers,
    });
  } catch (error) {
    if (error instanceof Error && error.name === "TimeoutError") {
      return jsonError(
        504,
        "upstream_timeout",
        "数据服务响应超时，请稍后重试。",
        requestId,
      );
    }

    return jsonError(
      503,
      "upstream_unavailable",
      "数据服务暂时不可用，请稍后重试。",
      requestId,
    );
  }
}
