/** AIHOT api.server.ts/page-reuse.ts adaptation: revisiting never renews upstream freshness. */
export const PAGE_REUSE_MS = 60_000;

export function responseDeadline(headers: Headers, now = Date.now()): number {
  const policy = headers.get("cache-control") ?? "";
  if (/(?:^|,)\s*(?:no-store|no-cache)(?:\s*(?:=|,|$))/i.test(policy)) return 0;
  let deadline = now + PAGE_REUSE_MS;
  const absolute = headers.get("x-accel-expires");
  if (absolute !== null) {
    if (!/^@\d+(?:\.\d+)?$/.test(absolute)) return 0;
    deadline = Math.min(deadline, Number(absolute.slice(1)) * 1000);
  }
  const maxAge = policy.match(/(?:^|,)\s*max-age\s*=\s*"?(\d+)"?(?:\s*(?:,|$))/i);
  if (maxAge) {
    const date = Date.parse(headers.get("date") ?? "");
    const age = Number(headers.get("age") ?? 0) * 1000;
    const consumed = Math.max(Number.isFinite(date) ? now - date : 0, Number.isFinite(age) ? age : 0, 0);
    deadline = Math.min(deadline, now + Number(maxAge[1]) * 1000 - consumed);
  }
  return Number.isFinite(deadline) && deadline > now ? deadline : 0;
}
