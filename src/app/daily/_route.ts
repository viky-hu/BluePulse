export function isDailyDate(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const time = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value;
}
export function isDailyMonth(value: unknown): value is string { return typeof value === "string" && /^\d{4}-(0[1-9]|1[0-2])$/.test(value); }
export type DailyRoute = { kind: "latest" } | { kind: "archive" } | { kind: "detail"; key: string };
export function dailyRoute(pathname: string): DailyRoute | null {
  if (pathname === "/daily") return { kind: "latest" };
  if (pathname === "/daily/archive") return { kind: "archive" };
  const key = pathname.startsWith("/daily/") ? pathname.slice(7) : "";
  return isDailyDate(key) ? { kind: "detail", key } : null;
}
