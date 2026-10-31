// AIHOT page-reuse / Timeline adapter; successful reads retain their upstream deadline (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import { fetchTaxonomy, type Topic } from "../../_lib/home-data";
import type { TimedTimeline, TimelineFilters } from "../../_lib/feed-types";
import { PAGE_REUSE_MS, responseDeadline } from "../../_lib/http-cache";
import { createTimedPageCache } from "../../_lib/page-cache";
import { invalidateSessionSnapshot } from "../../_lib/session-restore";
import { canonicalHref } from "../home/home-routes";
import { categorySupported, isContentFilter } from "../../all/_data";
import { FEATURED_MOCK_TAXONOMY, mockTimeline } from "./_mock";
import { parseTimeline, timelineFilters, timelineUrl } from "./_data";

export interface FeaturedFeedData {
  key: string; expiresAt: number; status: "loading" | "ready" | "unavailable" | "category-unavailable" | "error";
  timeline: TimedTimeline | null; taxonomy: Topic[]; error: string | null;
}
export class TimelineRequestError extends Error { constructor(public status: number, message: string) { super(message); } }
const pages = createTimedPageCache<FeaturedFeedData>(PAGE_REUSE_MS, 16);
const taxonomies = createTimedPageCache<{ items: Topic[]; expiresAt: number }>(PAGE_REUSE_MS, 1);
const cacheKey = (key: string, mock: boolean) => `${mock ? "mock" : "live"}:${canonicalHref(key)}`;
export const emptyFeaturedFeed = (key: string): FeaturedFeedData => ({ key, expiresAt: 0, status: "loading", timeline: null, taxonomy: [], error: null });
export function getCachedFeaturedFeed(key: string, mock: boolean) { return pages.get(cacheKey(key, mock)) ?? null; }
export function invalidateFeaturedFeed(key: string, mock: boolean) {
  pages.invalidate(cacheKey(key, mock));
  invalidateSessionSnapshot(`featured-list:${canonicalHref(key)}`, mock);
}
export async function requestTimeline(filters: TimelineFilters, cursor: string | null, mock: boolean, signal: AbortSignal): Promise<TimedTimeline> {
  if (mock) return { ...mockTimeline(filters, cursor), expiresAt: Date.now() + PAGE_REUSE_MS };
  const response = await fetch(timelineUrl(filters, cursor), { cache: "no-store", signal });
  if (!response.ok) throw new TimelineRequestError(response.status, response.status === 404 ? "精选服务尚未接入。" : `精选暂时无法载入（${response.status}）。`);
  return { ...parseTimeline(await response.json(), filters), expiresAt: responseDeadline(response.headers) };
}
export function loadFeaturedFeed(key: string, mock: boolean, force = false) {
  return pages.load(cacheKey(key, mock), async () => {
    const feed = emptyFeaturedFeed(key), filters = timelineFilters(key);
    const signal = AbortSignal.timeout(12_000);
    try {
      const taxonomy = mock ? Promise.resolve({ items: FEATURED_MOCK_TAXONOMY, expiresAt: Date.now() + PAGE_REUSE_MS }) : taxonomies.load("live", async () => {
        let expiresAt = Date.now() + PAGE_REUSE_MS;
        const data = await fetchTaxonomy(signal, at => { expiresAt = Math.min(expiresAt, at); });
        if (!Array.isArray(data.items) || !data.items.every(item => item && typeof item.slug === "string" && typeof item.name_zh === "string")) throw Error("分类数据格式异常，请稍后重试。");
        return { items: data.items, expiresAt };
      }, { force, expiresAt: value => value.expiresAt });
      const timeline = isContentFilter(filters.topic) ? taxonomy.then(value => categorySupported(filters.topic, value.items) ? requestTimeline(filters, null, mock, signal) : null) : requestTimeline(filters, null, mock, signal);
      const [topics, result] = await Promise.allSettled([taxonomy, timeline]);
      if (topics.status === "rejected" && isContentFilter(filters.topic)) throw topics.reason;
      if (topics.status === "fulfilled") feed.taxonomy = topics.value.items;
      if (result.status === "rejected") throw result.reason;
      if (result.value === null) { feed.status = "category-unavailable"; return feed; }
      feed.timeline = result.value;
      feed.expiresAt = Math.min(result.value.expiresAt, topics.status === "fulfilled" ? topics.value.expiresAt : result.value.expiresAt);
      feed.timeline.expiresAt = feed.expiresAt;
      feed.status = "ready";
    } catch (error) {
      feed.status = error instanceof TimelineRequestError && error.status === 404 ? "unavailable" : "error";
      feed.error = error instanceof Error ? error.message : "精选暂时无法载入。";
    }
    return feed;
  }, { force, shouldCache: feed => feed.status === "ready", expiresAt: feed => feed.expiresAt });
}
