import { getCachedAboutStats, invalidateAboutStats, loadAboutStats } from "../../about/_cache";
import { hasCachedHomeFeed, invalidateHomeFeed, prefetchHomeRoute } from "./home-feed-cache";
import { getCachedAllFeed, invalidateAllFeed, loadAllFeed } from "../../all/_cache";

export function hasCachedRouteData(key: string, mock: boolean): boolean {
  if (new URL(key, "https://pulse.local").pathname === "/all") return getCachedAllFeed(key, mock) !== null;
  return new URL(key, "https://pulse.local").pathname === "/about"
    ? getCachedAboutStats(key, mock) !== null : hasCachedHomeFeed(key, mock);
}
export function invalidateRouteData(key: string, mock: boolean) {
  invalidateAllFeed(key, mock);
  invalidateHomeFeed(key, mock);
  invalidateAboutStats(key, mock);
}
export function prefetchRouteData(href: string): Promise<void> {
  const url = new URL(href, "https://pulse.local");
  if (url.pathname === "/all") return loadAllFeed(href, url.searchParams.get("mock") === "1").then(() => undefined);
  return url.pathname === "/about" ? loadAboutStats(href, url.searchParams.get("mock") === "1").then(() => undefined) : prefetchHomeRoute(href);
}
