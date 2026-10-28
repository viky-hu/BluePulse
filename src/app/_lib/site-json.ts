import { createHash } from "node:crypto";
/** AIHOT sendJsonWithEtag adaptation for the two file-backed site GET endpoints. */
export function siteJson(request: Request, value: unknown, seconds: number): Response {
  const body = JSON.stringify(value), tag = `"${createHash("sha256").update(body).digest("hex")}"`;
  const headers = { "Content-Type": "application/json; charset=utf-8", "Cache-Control": `public, max-age=${seconds}, s-maxage=${seconds}`, ETag: tag };
  const matches = (request.headers.get("if-none-match") ?? "").split(",").map(v => v.trim().replace(/^W\//, ""));
  return new Response(matches.includes(tag) || matches.includes("*") ? null : body, { status: matches.includes(tag) || matches.includes("*") ? 304 : 200, headers });
}
