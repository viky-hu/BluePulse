// AIHOT packages/contracts/src/site.ts report contracts (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
export type ReportKind = "daily" | "weekly" | "monthly";
export interface ReportCitation {
  itemId: string | null;
  title: string;
  summary: string | null;
  sourceName: string;
  sourceUrl: string;
  sourceIconUrl: string | null;
  sourceIconSrcSet?: string;
  firstParty: boolean;
  publishedAt: string | null;
  available: boolean;
  otherSources?: number;
  related?: ReportCitation[];
  followUp?: string;
}
export interface ReportDetail {
  kind: ReportKind;
  key: string;
  issueNumber: number;
  title: string;
  generatedAt: string;
  lead: { title: string; leadParagraph: string } | null;
  leadItemId: string | null;
  overview: string | null;
  highlights: ReportCitation[];
  sections: Array<{ label: string; summary: string | null; items: ReportCitation[] }>;
  flashes: ReportCitation[];
  cover: { url: string; srcSet?: string; width: number | null; height: number | null; caption: string | null } | null;
  metrics: Record<string, number>;
  readingMinutes: number;
  prev: string | null;
  next: string | null;
}
export interface ReportIndexEntry { key: string; issueNumber: number; title: string | null; count: number }
export interface ReportIndexResponse { kind: ReportKind; items: ReportIndexEntry[] }
export interface ReportNavigationEntry { key: string; issueNumber: number; title?: string | null; count?: number }
export interface ReportLatestPage { index: ReportNavigationEntry[]; report: ReportDetail | null }
export interface ReportNavigationResponse { items: ReportNavigationEntry[] }
