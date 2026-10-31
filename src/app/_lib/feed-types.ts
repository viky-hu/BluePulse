// AIHOT packages/contracts/src/site.ts, adapted to Pulse UUID article cards (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import type { ArticleCard, ArticleRegion } from "./home-data";

export interface TimelineFilters { region: ArticleRegion | ""; topic: string }
export interface MediaView {
  kind: "image" | "video"; url: string; fullUrl?: string; width: number | null; height: number | null;
  alt: string | null; poster: string | null; srcSet?: string;
}
export interface XPostView {
  authorName: string; handle: string; avatarUrl: string | null; avatarSrcSet?: string;
  media: MediaView[];
  quoted: { authorName: string; handle: string; text: string; translation: string | null } | null;
}
export interface FeedArticle extends ArticleCard {
  selected?: boolean;
  sameEvent?: { id: string; title: string } | null;
  channel?: "news" | "x";
  x?: XPostView | null;
}
export interface GroupInfo { factId: string; additionalSourceCount: number; reportCount: number }
export interface GroupReport { id: string; title: string; source: { name: string }; timelineAt: string; originalUrl: string }
export interface GroupReportsResponse { factId: string; reports: GroupReport[] }
export interface TimelineCard { key: string; anchorAt: string; item: FeedArticle; group: GroupInfo | null }
export interface HotParticipant { name: string; kind: "editorial" | "signal"; iconUrl?: string | null; iconSrcSet?: string }
export interface HotStripEntry {
  rank: number; title: string; heat: number; trend: "up" | "down" | "flat" | "new" | "unknown";
  storyPublicId: string | null; itemId: string | null; participants: HotParticipant[]; participantCount: number;
}
export interface TimelineResponse {
  filters: TimelineFilters; cards: TimelineCard[]; nextCursor: string | null;
  hot: HotStripEntry[] | null; dayCounts: Record<string, number>;
}
export interface TimedTimeline extends TimelineResponse { expiresAt: number }
export interface TimelineListState extends TimedTimeline { batches: number; collapsed: string[] }
