// AIHOT ReportPaper.tsx: shared paper/outline projection, kept in original order (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import type { ReportCitation, ReportDetail } from "./_types";
export const pad = (n: number) => String(n).padStart(2, "0");
export const keyOf = (c: ReportCitation) => c.itemId ?? c.title;
export const anchorOf = (c: ReportCitation) => c.itemId ? `r-${c.itemId}` : null;
export interface ReportPage { id: string; label: string; summary: string | null; items: ReportCitation[] }
export interface OutlineEntry { id: string; text: string; level: number; mark?: string; note?: string }
export function leadStoryOf(report: ReportDetail): ReportCitation | null {
  if (!report.leadItemId) return null;
  return report.sections.flatMap(s => s.items).find(c => c.itemId === report.leadItemId && c.available) ?? null;
}
export function pagesOf(report: ReportDetail, leadStory: ReportCitation | null): ReportPage[] {
  const seen = new Set<string>(leadStory ? [keyOf(leadStory)] : []);
  return report.sections.map((s, i) => ({ id: `s-${i + 1}`, label: s.label, summary: s.summary, items: s.items.filter(c => {
    const key = keyOf(c); if (seen.has(key)) return false; seen.add(key); return true;
  }) })).filter(p => p.items.length > 0);
}
export function reportOutline(report: ReportDetail): OutlineEntry[] {
  const pages = pagesOf(report, leadStoryOf(report));
  if (pages.length === 0 && report.flashes.length === 0) return [];
  return [{ id: "report-start", text: "头版", level: 2, mark: "" }, ...pages.map((p, i) => ({ id: p.id, text: p.label, level: 2, mark: pad(i + 1), note: `${p.items.length} 件` })), ...(report.flashes.length > 0 ? [{ id: "s-flash", text: "快讯", level: 2, mark: pad(pages.length + 1), note: `${report.flashes.length} 条` }] : [])];
}
