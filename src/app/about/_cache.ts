import { createTimedPageCache } from "../_lib/page-cache";
import { PAGE_REUSE_MS } from "../_lib/http-cache";
import { canonicalHref } from "../_components/home/home-routes";
import { fetchSiteStats, type SiteStats } from "./_data";
import { MOCK_SITE_STATS } from "./_mock";

type StatsPage = { stats: SiteStats; expiresAt: number };
const pages = createTimedPageCache<StatsPage>(PAGE_REUSE_MS, 16);
const cacheKey = (key: string, mock: boolean) => `${mock ? "mock" : "live"}:${canonicalHref(key)}`;

export function getCachedAboutStats(key: string, mock: boolean): StatsPage | null {
  return pages.get(cacheKey(key, mock)) ?? null;
}
export function invalidateAboutStats(key: string, mock: boolean) { pages.invalidate(cacheKey(key, mock)); }

export function loadAboutStats(key: string, mock: boolean, force = false): Promise<StatsPage> {
  return pages.load(cacheKey(key, mock), async () => {
    let expiresAt = Date.now() + PAGE_REUSE_MS;
    // The shared request owns its timeout; consumers only unsubscribe when they leave.
    const stats = mock ? MOCK_SITE_STATS : await fetchSiteStats(AbortSignal.timeout(8000), deadline => { expiresAt = deadline; });
    return { stats, expiresAt };
  }, { force, expiresAt: page => page.expiresAt });
}
