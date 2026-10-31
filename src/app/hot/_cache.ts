// AIHOT page-reuse adapted to Pulse's existing public cache (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import { createTimedPageCache } from "../_lib/page-cache.ts";
import { responseDeadline } from "../_lib/http-cache.ts";
import { canonicalHref } from "../_components/home/home-routes.ts";
import { parseHot } from "./_data.ts";
import { MOCK_HOT } from "./_mock.ts";
import type { HotResponse } from "./_types";

export interface HotData { key: string; status: "loading" | "ready" | "unavailable" | "error"; hot: HotResponse | null; expiresAt: number; error: string | null }
const pages = createTimedPageCache<HotData>(30_000, 16);
const cacheKey = (key: string, mock: boolean) => `${mock ? "mock" : "live"}:${canonicalHref(key)}`;
export const emptyHotData = (key: string): HotData => ({ key: canonicalHref(key), status: "loading", hot: null, expiresAt: 0, error: null });
export const getCachedHot = (key: string, mock: boolean) => pages.get(cacheKey(key, mock)) ?? null;
export const invalidateHot = (key: string, mock: boolean) => pages.invalidate(cacheKey(key, mock));
export function hotDeadline(headers: Headers, now = Date.now()) { return Math.min(now + 30_000, responseDeadline(headers, now)); }
export function loadHot(key: string, mock: boolean, force = false) {
  return pages.load(cacheKey(key, mock), async () => {
    const data = emptyHotData(key);
    try {
      if (mock) { data.hot = MOCK_HOT; data.expiresAt = Date.now() + 30_000; }
      else {
        const response = await fetch("/api/bluepulse/site/hot", { cache: "no-store", signal: AbortSignal.timeout(12_000) });
        if (!response.ok) {
          data.status = response.status === 404 ? "unavailable" : "error";
          data.error = response.status === 404 ? "热点榜服务尚未接入。" : `热点榜暂时无法载入（${response.status}）。`;
          return data;
        }
        data.hot = parseHot(await response.json());
        data.expiresAt = hotDeadline(response.headers);
      }
      data.status = "ready";
    } catch (error) {
      data.status = "error";
      data.error = error instanceof Error && error.message === "热点榜数据格式异常，请稍后重试。" ? error.message : "热点榜暂时无法载入，请稍后重试。";
    }
    return data;
  }, { force, shouldCache: value => value.status === "ready", expiresAt: value => value.expiresAt });
}
