import { fetchHomeArticles, fetchTaxonomy, type ArticleCard, type ArticleListResponse, type Topic } from "../_lib/home-data";
import { createTimedPageCache } from "../_lib/page-cache";
import { PAGE_REUSE_MS } from "../_lib/http-cache";
import { invalidateSessionSnapshot } from "../_lib/session-restore";
import { canonicalHref, parseHomeRoute } from "../_components/home/home-routes";
import { allArticleParams, categorySupported, isContentFilter } from "./_data";
import { ALL_MOCK_TAXONOMY, mockAllFeed } from "./_mock";

export type AllFeedData = { key: string; expiresAt: number; status: "loading" | "ready" | "category-unavailable" | "error"; articles: ArticleCard[]; taxonomy: Topic[]; next: string | null; error: string | null };
const pages = createTimedPageCache<AllFeedData>(PAGE_REUSE_MS, 16);
const taxonomies = createTimedPageCache<{ items: Topic[]; expiresAt: number }>(PAGE_REUSE_MS, 1);
const cacheKey = (key: string, mock: boolean) => `${mock ? "mock" : "live"}:${canonicalHref(key)}`;
export const emptyAllFeed = (key: string): AllFeedData => ({ key, expiresAt: 0, status: "loading", articles: [], taxonomy: [], next: null, error: null });
export function getCachedAllFeed(key: string, mock: boolean) { return pages.get(cacheKey(key, mock)) ?? null; }
export function invalidateAllFeed(key: string, mock: boolean) {
  pages.invalidate(cacheKey(key, mock));
  invalidateSessionSnapshot(`all-feed:${canonicalHref(key)}`, mock);
}
export function validAllSnapshot(value: AllFeedData | null, key: string): value is AllFeedData {
  return !!value && value.key === key && Number.isFinite(value.expiresAt) && value.expiresAt > Date.now() && (value.status === "ready" || value.status === "category-unavailable") && Array.isArray(value.articles) && Array.isArray(value.taxonomy) && value.articles.every(item => item && typeof item.id === "string" && typeof item.title === "string" && typeof item.source?.name === "string");
}
export function loadAllFeed(key: string, mock: boolean, force = false) {
  return pages.load(cacheKey(key, mock), () => requestAllFeed(key, mock, force), { force, shouldCache: data => data.status === "ready" || data.status === "category-unavailable", expiresAt: data => data.expiresAt });
}
async function requestAllFeed(key: string, mock: boolean, force: boolean): Promise<AllFeedData> {
  const data = emptyAllFeed(key);
  data.expiresAt = Date.now() + PAGE_REUSE_MS;
  const deadline = (at: number) => { data.expiresAt = Math.min(data.expiresAt, at); };
  const url = new URL(key, "https://pulse.local");
  const { filters, cursor } = parseHomeRoute("/all", url.searchParams);
  try {
    const signal = AbortSignal.timeout(12_000);
    const taxonomy = mock ? Promise.resolve({ items: ALL_MOCK_TAXONOMY, expiresAt: data.expiresAt }) : taxonomies.load("live", async () => {
      let expiresAt = Date.now() + PAGE_REUSE_MS;
      const result = await fetchTaxonomy(signal, at => { expiresAt = Math.min(expiresAt, at); });
      if (!Array.isArray(result.items) || !result.items.every(item => item && typeof item.slug === "string" && typeof item.name_zh === "string")) throw Error("分类数据格式异常，请稍后重试。");
      return { items: result.items, expiresAt };
    }, { force, expiresAt: result => result.expiresAt });
    const fetchList = () => mock ? Promise.resolve(mockAllFeed(filters, cursor)) : fetchHomeArticles(allArticleParams(filters, cursor), signal, deadline);
    // Exact new categories must be registered before an empty article list can mean "no results".
    const list = isContentFilter(filters.topic) ? taxonomy.then(result => categorySupported(filters.topic, result.items) ? fetchList() : null) : fetchList();
    const [topics, articles] = await Promise.allSettled([taxonomy, list]);
    if (topics.status === "fulfilled") { data.taxonomy = topics.value.items; deadline(topics.value.expiresAt); }
    if (topics.status === "rejected" && isContentFilter(filters.topic)) throw topics.reason;
    if (articles.status === "rejected") throw articles.reason;
    if (articles.value === null) { data.status = "category-unavailable"; return data; }
    const response: ArticleListResponse = articles.value;
    if (!Array.isArray(response.items) || !response.items.every(item => item && typeof item.id === "string" && typeof item.title === "string" && typeof item.source?.name === "string") || (response.next_cursor !== null && typeof response.next_cursor !== "string")) throw Error("资讯数据格式异常，请稍后重试。");
    data.articles = response.items;
    data.next = response.next_cursor;
    data.status = "ready";
  } catch (error) {
    data.status = "error";
    data.error = error instanceof Error ? error.message : "资讯暂时无法载入。";
  }
  return data;
}
