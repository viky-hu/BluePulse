// AIHOT publication/timeline.ts and features/feed/Timeline.tsx adaptation (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import type { HotStripEntry, TimedTimeline, TimelineCard, TimelineFilters, TimelineListState, TimelineResponse } from "../../_lib/feed-types";

const dayFormat = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" });
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export const PUBLIC_ID = /^[a-zA-Z0-9_-]{1,80}$/;
export function timelineFilters(key: string): TimelineFilters {
  const params = new URL(key, "https://pulse.local").searchParams;
  return { region: params.get("region") === "domestic" ? "domestic" : params.get("region") === "foreign" ? "foreign" : "", topic: params.get("topic") ?? "" };
}
export function timelineParams(filters: TimelineFilters, cursor?: string | null) {
  const params = new URLSearchParams();
  if (filters.region) params.set("region", filters.region);
  if (filters.topic) params.set("topic", filters.topic);
  if (cursor) params.set("cursor", cursor);
  params.set("limit", "20");
  return params;
}
export function timelineUrl(filters: TimelineFilters, cursor?: string | null) { return `/api/bluepulse/site/timeline?${timelineParams(filters, cursor)}`; }
export function hotHref(entry: Pick<HotStripEntry, "storyPublicId" | "itemId">) {
  return entry.storyPublicId ? `/story/${encodeURIComponent(entry.storyPublicId)}` : entry.itemId ? `/articles/${encodeURIComponent(entry.itemId)}` : "/hot";
}
export function groupTimeline(cards: TimelineCard[]) {
  const days: { day: string; cards: TimelineCard[] }[] = [];
  for (const card of cards) {
    const day = dayFormat.format(new Date(card.anchorAt)), last = days.at(-1);
    if (last?.day === day) last.cards.push(card); else days.push({ day, cards: [card] });
  }
  return days;
}
export function fromTimeline(data: TimedTimeline): TimelineListState { return { ...data, batches: 1, collapsed: [] }; }
export function appendTimeline(state: TimelineListState, page: TimedTimeline): TimelineListState {
  const seen = new Set(state.cards.map(card => card.key));
  const added = page.cards.filter(card => { if (seen.has(card.key)) return false; seen.add(card.key); return true; });
  return { ...state, cards: [...state.cards, ...added], nextCursor: page.nextCursor, dayCounts: { ...state.dayCounts, ...page.dayCounts }, expiresAt: Math.min(state.expiresAt, page.expiresAt), batches: state.batches + 1 };
}
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);
const date = (value: unknown) => typeof value === "string" && Number.isFinite(Date.parse(value));
const count = (value: unknown) => Number.isInteger(value) && Number(value) >= 0;
export function parseTimeline(value: unknown, filters: TimelineFilters): TimelineResponse {
  const invalid = () => { throw Error("精选数据格式异常，请稍后重试。"); };
  if (!record(value) || !record(value.filters) || value.filters.region !== filters.region || value.filters.topic !== filters.topic || !Array.isArray(value.cards) || (value.nextCursor !== null && typeof value.nextCursor !== "string") || !record(value.dayCounts) || !Object.entries(value.dayCounts).every(([key, n]) => /^\d{4}-\d{2}-\d{2}$/.test(key) && count(n))) return invalid();
  for (const card of value.cards) {
    if (!record(card) || typeof card.key !== "string" || !PUBLIC_ID.test(card.key) || !date(card.anchorAt) || !record(card.item) || typeof card.item.id !== "string" || !uuid.test(card.item.id) || typeof card.item.title !== "string" || typeof card.item.url !== "string" || !record(card.item.source) || typeof card.item.source.name !== "string" || typeof card.item.selected !== "boolean") return invalid();
    const group = card.group;
    if (group !== null && (!record(group) || typeof group.factId !== "string" || !PUBLIC_ID.test(group.factId) || !count(group.reportCount) || !count(group.additionalSourceCount))) return invalid();
    if (!count(value.dayCounts[dayFormat.format(new Date(card.anchorAt as string))])) return invalid();
    const item = card.item;
    if (item.sameEvent != null && (!record(item.sameEvent) || typeof item.sameEvent.id !== "string" || !uuid.test(item.sameEvent.id) || typeof item.sameEvent.title !== "string")) return invalid();
    if (item.channel !== undefined && item.channel !== "news" && item.channel !== "x") return invalid();
    if (item.channel === "x") {
      const post = item.x;
      if (!record(post) || typeof post.authorName !== "string" || typeof post.handle !== "string" || !Array.isArray(post.media) || !post.media.every(media => record(media) && ["image", "video"].includes(String(media.kind)) && typeof media.url === "string")) return invalid();
      if (post.quoted != null && (!record(post.quoted) || typeof post.quoted.authorName !== "string" || typeof post.quoted.handle !== "string" || typeof post.quoted.text !== "string" || (post.quoted.translation !== null && typeof post.quoted.translation !== "string"))) return invalid();
    }
  }
  if (new Set(value.cards.map(card => card.key)).size !== value.cards.length) return invalid();
  if (value.hot !== null) {
    if (!Array.isArray(value.hot)) return invalid();
    for (const entry of value.hot) {
      if (!record(entry) || !count(entry.rank) || Number(entry.rank) < 1 || typeof entry.title !== "string" || typeof entry.heat !== "number" || !Number.isFinite(entry.heat) || !["up", "down", "flat", "new", "unknown"].includes(String(entry.trend)) || (entry.storyPublicId !== null && (typeof entry.storyPublicId !== "string" || !PUBLIC_ID.test(entry.storyPublicId))) || (entry.itemId !== null && (typeof entry.itemId !== "string" || !uuid.test(entry.itemId))) || !count(entry.participantCount) || !Array.isArray(entry.participants) || !entry.participants.every(p => record(p) && typeof p.name === "string" && ["editorial", "signal"].includes(String(p.kind)))) return invalid();
    }
  }
  return value as unknown as TimelineResponse;
}
