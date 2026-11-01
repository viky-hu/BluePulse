import { getCachedAboutStats, invalidateAboutStats, loadAboutStats } from "../../about/_cache";
import { hasCachedHomeFeed, invalidateHomeFeed, prefetchHomeRoute } from "./home-feed-cache";
import { getCachedAllFeed, invalidateAllFeed, loadAllFeed } from "../../all/_cache";
import { getCachedFeaturedFeed, invalidateFeaturedFeed, loadFeaturedFeed } from "../featured/_cache";
import { getCachedHot, invalidateHot, loadHot } from "../../hot/_cache";
import { getCachedDailyPage, invalidateDailyPage, loadDailyPage } from "../../daily/_cache";
import { dailyRoute } from "../../daily/_route";

export function hasCachedRouteData(key: string, mock: boolean): boolean {
  if (dailyRoute(new URL(key, "https://pulse.local").pathname)) return getCachedDailyPage(key, mock) !== null;
  if (new URL(key, "https://pulse.local").pathname === "/hot") return getCachedHot(key, mock) !== null;
  if (new URL(key, "https://pulse.local").pathname === "/") return getCachedFeaturedFeed(key, mock) !== null;
  if (new URL(key, "https://pulse.local").pathname === "/all") return getCachedAllFeed(key, mock) !== null;
  return new URL(key, "https://pulse.local").pathname === "/about"
    ? getCachedAboutStats(key, mock) !== null : hasCachedHomeFeed(key, mock);
}
export function invalidateRouteData(key: string, mock: boolean) {
  invalidateDailyPage(key, mock);
  invalidateHot(key, mock);
  invalidateFeaturedFeed(key, mock);
  invalidateAllFeed(key, mock);
  invalidateHomeFeed(key, mock);
  invalidateAboutStats(key, mock);
}
export function prefetchRouteData(href: string): Promise<void> {
  const url = new URL(href, "https://pulse.local");
  if (dailyRoute(url.pathname)) return loadDailyPage(href, url.searchParams.get("mock") === "1").then(() => undefined);
  if (url.pathname === "/hot") return loadHot(href, url.searchParams.get("mock") === "1").then(() => undefined);
  if (url.pathname === "/") return loadFeaturedFeed(href, url.searchParams.get("mock") === "1").then(() => undefined);
  if (url.pathname === "/all") return loadAllFeed(href, url.searchParams.get("mock") === "1").then(() => undefined);
  return url.pathname === "/about" ? loadAboutStats(href, url.searchParams.get("mock") === "1").then(() => undefined) : prefetchHomeRoute(href);
}
