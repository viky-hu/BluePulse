// AIHOT features/feed/ReadingGroup.tsx request contract (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import type { GroupReport, TimelineFilters } from "../../_lib/feed-types";

export function groupReportsUrl(factId: string, filters?: TimelineFilters): string {
  const params = new URLSearchParams();
  if (filters?.region) params.set("region", filters.region);
  if (filters?.topic) params.set("topic", filters.topic);
  return `/api/bluepulse/site/groups/${encodeURIComponent(factId)}/reports${params.size ? `?${params}` : ""}`;
}
export async function requestGroupReports(url: string, signal: AbortSignal, again = false): Promise<GroupReport[]> {
  const response = await fetch(url, { cache: "no-store", signal: AbortSignal.any([signal, AbortSignal.timeout(12000)]) });
  if (again && response.status === 404) return [];
  if (!response.ok) throw new Error(String(response.status));
  const payload: unknown = await response.json();
  if (!payload || typeof payload !== "object" || !("factId" in payload) || typeof payload.factId !== "string" || !("reports" in payload) || !Array.isArray(payload.reports)) throw new Error("Invalid group reports");
  for (const report of payload.reports) {
    if (!report || typeof report !== "object" || typeof report.id !== "string" || typeof report.title !== "string" || typeof report.timelineAt !== "string" || typeof report.originalUrl !== "string" || !report.source || typeof report.source !== "object" || typeof report.source.name !== "string") throw new Error("Invalid group reports");
  }
  return payload.reports as GroupReport[];
}
