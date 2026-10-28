import { fetchHomeArticles, fetchHomeFeatured, fetchRecentlyCollected, fetchSources, type ArticleCard, type Source } from "../../_lib/home-data";
import { MOCK_HOME_DATA, MOCK_SOURCES } from "../../_lib/home-mock";
import { createTimedPageCache } from "../../_lib/page-cache";
import { PAGE_REUSE_MS } from "../../_lib/http-cache";
import { invalidateSessionSnapshot } from "../../_lib/session-restore";
import { canonicalHref, parseHomeRoute, type HomeFilters } from "./home-routes";

export type HomeFeed = {
  expiresAt: number;
  key: string;
  status: "loading" | "ready" | "error";
  articles: ArticleCard[];
  featured: ArticleCard[];
  collected: ArticleCard[];
  next: string | null;
  error: string | null;
};

type FeedRequest = {
  key: string;
  pathname: string;
  filters: HomeFilters;
  cursor: string | null;
  mock: boolean;
};

const homeFeeds = createTimedPageCache<HomeFeed>(PAGE_REUSE_MS, 16);
const sourceLists = createTimedPageCache<{ items: Source[]; expiresAt: number }>(PAGE_REUSE_MS, 2);

export function emptyHomeFeed(key: string): HomeFeed {
  return { key, expiresAt: 0, status: "loading", articles: [], featured: [], collected: [], next: null, error: null };
}

function cacheKey(key: string, mock: boolean) {
  return `${mock ? "mock" : "live"}:${canonicalHref(key)}`;
}

export function getCachedHomeFeed(key: string, mock: boolean): HomeFeed | null {
  return homeFeeds.get(cacheKey(key, mock)) ?? null;
}

export function hasCachedHomeFeed(key: string, mock: boolean): boolean {
  return getCachedHomeFeed(key, mock) !== null;
}

export function invalidateHomeFeed(key: string, mock: boolean) {
  homeFeeds.invalidate(cacheKey(key, mock));
  invalidateSessionSnapshot(`feed:${canonicalHref(key)}`, mock);
}

export function loadHomeFeed(request: FeedRequest, options: { force?: boolean } = {}): Promise<HomeFeed> {
  return homeFeeds.load(
    cacheKey(request.key, request.mock),
    () => requestHomeFeed(request),
    { force: options.force, shouldCache: feed => feed.status === "ready", expiresAt: feed => feed.expiresAt },
  );
}

export function getCachedHomeSources(mock: boolean): Source[] | null {
  return mock ? MOCK_SOURCES.items : sourceLists.get("live")?.items ?? null;
}

export function loadHomeSources(mock: boolean): Promise<Source[]> {
  if (mock) return Promise.resolve(MOCK_SOURCES.items);
  return sourceLists.load("live", async () => {
    let expiresAt = 0;
    const { items } = await fetchSources(AbortSignal.timeout(12_000), deadline => { expiresAt = deadline; });
    return { items, expiresAt };
  }, { expiresAt: value => value.expiresAt }).then(value => value.items);
}

/** Starts the route and data work when a reader signals intent from the menu. */
export function prefetchHomeRoute(href: string): Promise<void> {
  const url = new URL(href, "https://pulse.local");
  const route = parseHomeRoute(url.pathname, url.searchParams);
  if (!route.valid || !["home", "all", "search"].includes(route.kind)) return Promise.resolve();

  const request: FeedRequest = {
    key: canonicalHref(`${url.pathname}${url.search}`),
    pathname: url.pathname,
    filters: route.filters,
    cursor: route.cursor,
    mock: url.searchParams.get("mock") === "1",
  };
  const work = [loadHomeFeed(request).then(() => undefined)];
  if (route.kind === "all" || route.kind === "search") work.push(loadHomeSources(request.mock).then(() => undefined));
  return Promise.all(work).then(() => undefined);
}

async function requestHomeFeed({ key, pathname, filters, cursor, mock }: FeedRequest): Promise<HomeFeed> {
  const next = emptyHomeFeed(key);
  next.expiresAt = Date.now() + PAGE_REUSE_MS;
  const useDeadline = (deadline: number) => { next.expiresAt = Math.min(next.expiresAt, deadline); };
  try {
    if (mock) {
      const query = filters.q.toLocaleLowerCase();
      const rows = MOCK_HOME_DATA.articles
        .filter(article => (!filters.topic || article.topics?.includes(filters.topic))
          && (!filters.region || article.region === filters.region)
          && (!filters.source || article.source.id === filters.source)
          && (!filters.sourceType || article.source.source_type === filters.sourceType)
          && (!query || `${article.title} ${article.source_title} ${article.summary ?? ""}`.toLocaleLowerCase().includes(query)))
        .sort((a, b) => filters.sort === "importance" ? b.importance_score - a.importance_score : (b.published_at ?? "").localeCompare(a.published_at ?? ""));
      const offset = /^mock-\d+$/.test(cursor ?? "") ? Number(cursor!.slice(5)) : 0;
      next.articles = rows.slice(offset, offset + 8);
      next.next = offset + 8 < rows.length ? `mock-${offset + 8}` : null;
      next.featured = pathname === "/" ? MOCK_HOME_DATA.featured.slice(0, 6) : [];
    } else {
      const params = new URLSearchParams({ period: filters.period, sort: filters.sort, limit: "20" });
      for (const [name, value] of Object.entries({ q: filters.q, topic: filters.topic, region: filters.region, source: filters.source, source_type: filters.sourceType, entity: filters.entity, cursor })) {
        if (value) params.set(name, value);
      }
      const signal = AbortSignal.timeout(12_000);
      const [list, featured] = await Promise.allSettled([
        fetchHomeArticles(params, signal, useDeadline),
        pathname === "/" ? fetchHomeFeatured(signal, useDeadline) : Promise.resolve({ items: [] }),
      ]);
      if (list.status === "fulfilled") {
        next.articles = list.value.items;
        next.next = list.value.next_cursor;
      } else next.error = list.reason instanceof Error ? list.reason.message : "资讯暂时无法载入";
      if (featured.status === "fulfilled") next.featured = featured.value.items.map(item => item.article);
      else next.error = `${next.error ? `${next.error}；` : ""}精选暂时无法载入`;
      if (pathname === "/" && !next.error && !next.articles.length && !next.featured.length) {
        next.collected = (await fetchRecentlyCollected(signal, useDeadline)).items;
      }
    }
    next.status = next.error ? "error" : "ready";
  } catch (error) {
    next.status = "error";
    next.error = error instanceof Error ? error.message : "资讯暂时无法载入";
  }
  return next;
}
