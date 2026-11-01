// AIHOT report page-reuse adapted to the Pulse shared deadline lifecycle (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import { createTimedPageCache } from "../_lib/page-cache.ts";
import { responseDeadline } from "../_lib/http-cache.ts";
import { canonicalHref } from "../_components/home/home-routes.ts";
import { dailyRoute, isDailyMonth } from "./_route.ts";
import { parseReportDetail, parseReportLatest, parseReportIndex, parseReportNavigation } from "./_data.ts";
import { mockDailyBundle, MOCK_REPORT_INDEX } from "./_mock.ts";
import type { ReportDetail, ReportNavigationEntry, ReportNavigationResponse } from "./_types";
export interface DailyData { key: string; status: "loading" | "ready" | "unavailable" | "error" | "not-found"; report: ReportDetail | null; index: ReportNavigationEntry[]; today: string; expiresAt: number; error: string | null }
type MonthData = ReportNavigationResponse & { expiresAt: number };
type Cached = { type: "page"; value: DailyData } | { type: "month"; value: MonthData };
const pages = createTimedPageCache<Cached>(120_000, 16);
const prefix = (mock: boolean) => mock ? "mock" : "live";
const cacheKey = (key: string, mock: boolean) => `page:${prefix(mock)}:${canonicalHref(key)}`;
const base = "/api/bluepulse/site/reports/daily";
const beijingToday = () => new Date(Date.now() + 8 * 3600_000).toISOString().slice(0, 10);
export const emptyDailyData = (key: string): DailyData => ({ key: canonicalHref(key), status: "loading", report: null, index: [], today: beijingToday(), expiresAt: 0, error: null });
export function getCachedDailyPage(key: string, mock: boolean): DailyData | null { const hit = pages.get(cacheKey(key, mock)); return hit?.type === "page" ? hit.value : null; }
export const invalidateDailyPage = (key: string, mock: boolean) => pages.invalidate(cacheKey(key, mock));
export function dailyDeadline(headers: Headers, capMs: number, now = Date.now()) { return responseDeadline(headers, now, capMs); }
class ReadFailure extends Error {
  status: number; endpoint: string;
  constructor(status: number, endpoint: string) { super(`日报读取失败（${status}）。`); this.status = status; this.endpoint = endpoint; }
}
async function read<T>(endpoint: string, parse: (value: unknown) => T, capMs: number) {
  const response = await fetch(`${base}${endpoint}`, { cache: "no-store", signal: AbortSignal.timeout(12_000) });
  if (!response.ok) throw new ReadFailure(response.status, endpoint);
  const value = parse(await response.json());
  return { value, expiresAt: dailyDeadline(response.headers, capMs) };
}
export async function loadDailyPage(key: string, mock: boolean, force = false): Promise<DailyData> {
  const result = await pages.load(cacheKey(key, mock), async (): Promise<Cached> => {
    const data = emptyDailyData(key), route = dailyRoute(new URL(data.key, "https://pulse.local").pathname);
    if (!route) { data.status = "not-found"; return { type: "page", value: data }; }
    try {
      if (mock) {
        const bundle = mockDailyBundle(route);
        if (!bundle) { data.status = "not-found"; return { type: "page", value: data }; }
        Object.assign(data, bundle); data.expiresAt = Date.now() + (route.kind === "detail" ? 120_000 : 60_000);
      } else if (route.kind === "latest") {
        const result = await read("/latest-page", parseReportLatest, 60_000);
        Object.assign(data, result.value); data.expiresAt = result.expiresAt;
      } else if (route.kind === "archive") {
        const result = await read("", parseReportIndex, 60_000); data.index = result.value.items; data.expiresAt = result.expiresAt;
      } else {
        const [reportRead, indexRead] = await Promise.allSettled([read(`/${route.key}`, parseReportDetail, 120_000), read(`/navigation/${route.key}`, parseReportNavigation, 60_000)]);
        // A detail 404 means a missing edition only after the report service's
        // navigation succeeded. Absent endpoints must not race to claim a quiet/missing day.
        if (indexRead.status === "rejected") throw indexRead.reason;
        if (reportRead.status === "rejected") throw reportRead.reason;
        const report = reportRead.value, index = indexRead.value;
        if (report.value.key !== route.key) throw new Error("日报数据格式异常，请稍后重试。");
        data.report = report.value; data.index = index.value.items; data.expiresAt = Math.min(report.expiresAt, index.expiresAt);
      }
      data.status = "ready";
    } catch (error) {
      data.report = null; data.index = []; data.expiresAt = 0;
      data.status = error instanceof ReadFailure && error.status === 404 ? (route.kind === "detail" && error.endpoint === `/${route.key}` ? "not-found" : "unavailable") : "error";
      data.error = data.status === "unavailable" ? "日报服务尚未接入。" : data.status === "not-found" ? "这一天没有已发布的日报。" : error instanceof Error && error.message === "日报数据格式异常，请稍后重试。" ? error.message : "日报暂时无法载入，请稍后重试。";
    }
    return { type: "page", value: data };
  }, { force, shouldCache: r => r.type === "page" && r.value.status === "ready", expiresAt: r => r.value.expiresAt });
  if (result.type !== "page") throw new Error("Unexpected report cache entry");
  return result.value;
}
export async function loadDailyMonth(month: string, mock: boolean, force = false): Promise<MonthData> {
  if (!isDailyMonth(month)) throw new Error("无效日报月份");
  const result = await pages.load(`month:${prefix(mock)}:${month}`, async (): Promise<Cached> => {
    if (mock) return { type: "month", value: { items: MOCK_REPORT_INDEX.filter(e => e.key.startsWith(month)), expiresAt: Date.now() + 60_000 } };
    const readResult = await read(`/months/${month}`, parseReportNavigation, 60_000);
    if (readResult.value.items.some(e => !e.key.startsWith(`${month}-`))) throw new Error("日报月份不一致");
    return { type: "month", value: { ...readResult.value, expiresAt: readResult.expiresAt } };
  }, { force, expiresAt: r => r.value.expiresAt });
  if (result.type !== "month") throw new Error("Unexpected report cache entry");
  return result.value;
}
