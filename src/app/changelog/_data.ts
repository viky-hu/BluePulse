// AIHOT changelog types, grouping and date headings (MIT); see THIRD_PARTY_NOTICES.md.
export const KINDS = ["更新", "优化", "公告", "下线"] as const;
export type ReleaseKind = typeof KINDS[number];
export interface ChangelogRelease { date: string; time: string; kind: ReleaseKind; title: string; body: string[]; urgent?: true }
export interface ChangelogResponse { latestVersion: string; releases: ChangelogRelease[] }
const versionPattern = /^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d$/;
export function validVersion(value: unknown): value is string {
  if (typeof value !== "string" || !versionPattern.test(value)) return false;
  const date = new Date(`${value}Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 16) === value;
}
export function parseChangelog(value: unknown): ChangelogResponse {
  if (!value || typeof value !== "object") throw Error("Invalid changelog");
  const data = value as ChangelogResponse;
  if (!validVersion(data.latestVersion) || !Array.isArray(data.releases)) throw Error("Invalid changelog envelope");
  let previous = data.latestVersion;
  for (const r of data.releases) {
    if (!r || typeof r !== "object" || !validVersion(`${r.date}T${r.time}`) || !KINDS.includes(r.kind) || typeof r.title !== "string" || !r.title.trim() || !Array.isArray(r.body) || !r.body.every(line => typeof line === "string" && line.trim()) || (r.urgent !== undefined && r.urgent !== true)) throw Error("Invalid changelog release");
    const version = `${r.date}T${r.time}`;
    if (version > previous) throw Error("Changelog must be newest first");
    previous = version;
  }
  if (data.releases.length && `${data.releases[0].date}T${data.releases[0].time}` !== data.latestVersion) throw Error("Changelog version must match latest entry");
  return data;
}
export function groupReleases(releases: ChangelogRelease[], kind: ReleaseKind | null = null): Map<string, ChangelogRelease[]> {
  const groups = new Map<string, ChangelogRelease[]>();
  for (const release of releases) if (!kind || release.kind === kind) groups.set(release.date, [...(groups.get(release.date) ?? []), release]);
  return groups;
}
export function monthIndex(groups: Map<string, ChangelogRelease[]>) {
  const months = new Map<string, { month: string; first: string; count: number }>();
  for (const [date, releases] of groups) {
    const month = date.slice(0, 7), item = months.get(month) ?? { month, first: date, count: 0 };
    item.count += releases.length; months.set(month, item);
  }
  return [...months.values()];
}
export function dateHeading(date: string) {
  const [y, m, d] = date.split("-").map(Number);
  return { label: `${y} 年 ${m} 月 ${d} 日`, weekday: ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][new Date(`${date}T00:00:00Z`).getUTCDay()] };
}
