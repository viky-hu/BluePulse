import { getCachedAboutStats, invalidateAboutStats, loadAboutStats } from "../../about/_cache";
import { hasCachedHomeFeed, invalidateHomeFeed, prefetchHomeRoute } from "./home-feed-cache";

export function hasCachedRouteData(key: string, mock: boolean): boolean {
  return new URL(key, "https://pulse.local").pathname === "/about"
    ? getCachedAboutStats(key, mock) !== null : hasCachedHomeFeed(key, mock);
}
export function invalidateRouteData(key: string, mock: boolean) {
  invalidateHomeFeed(key, mock);
  invalidateAboutStats(key, mock);
}
export function prefetchRouteData(href: string): Promise<void> {
  const url = new URL(href, "https://pulse.local");
  return url.pathname === "/about" ? loadAboutStats(href, url.searchParams.get("mock") === "1").then(() => undefined) : prefetchHomeRoute(href);
}
