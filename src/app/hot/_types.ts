// AIHOT packages/contracts/src/site.ts (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import type { HotParticipant } from "../_lib/feed-types";
export interface HotEntryView {
  rank: number;
  story: { publicId: string; title: string };
  heat: number;
  trend: "up" | "down" | "flat" | "new" | "unknown";
  trendPct: number | null;
  badges: Array<"surge" | "new" | "rising">;
  participantCount: number;
  sourceCount: number;
  sourceNames: string[];
  participants: HotParticipant[];
  spark: Array<number | null>;
  summary: string | null;
  latest: string | null;
  cover: { url: string; srcSet?: string; width: number | null; height: number | null } | null;
}
export interface HotResponse { computedAt: string | null; windowHours: number; entries: HotEntryView[] }
