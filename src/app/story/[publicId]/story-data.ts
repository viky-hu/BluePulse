// AIHOT packages/contracts/src/site.ts (MIT). Copyright (c) 2026 数字生命卡兹克.
export interface HeatPoint { hour: string; heat: number; participants: number }
export interface StoryReport {
  id: string;
  title: string;
  summary: string | null;
  source: { name: string; firstParty: boolean };
  publishedAt: string;
  selected: boolean;
}
export interface StoryDetail {
  publicId: string;
  title: string;
  status: "active" | "watching" | "settled";
  reportCount: number;
  sourceCount: number;
  firstReportAt: string;
  latestAt: string;
  digest: string | null;
  digestUpdatedAt: string | null;
  summary: string | null;
  excerpt: { text: string; sourceName: string } | null;
  latest: string | null;
  latestReport: { id: string } | null;
  whyHot: {
    participants48h: number;
    newParticipants6h: number;
    recentReports24h: number;
    observationComplete: boolean;
    rank: number | null;
  };
  developments: Array<{
    factId: string; title: string; firstReportAt: string; reportCount: number; representative: StoryReport;
  }>;
  officialReports: StoryReport[];
  timeline: StoryReport[];
  heat: HeatPoint[];
  related: Array<{ publicId: string; title: string; relation: "storyline" | "related" }>;
  topics: Array<{ slug: string; name: string }>;
}
