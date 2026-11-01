// Original AIHOT report DTOs retained at Pulse's anonymous HTTP boundary (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import { isDailyDate } from "./_route.ts";
import type { ReportCitation, ReportDetail, ReportLatestPage, ReportIndexResponse, ReportNavigationEntry, ReportNavigationResponse } from "./_types";
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === "string";
const nullableText = (v: unknown) => v === null || text(v);
const number = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const count = (v: unknown): v is number => number(v) && Number.isInteger(v) && v >= 0;
const uuid = (v: unknown) => text(v) && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(v);
const timestamp = (v: unknown) => text(v) && /^\d{4}-\d{2}-\d{2}T/.test(v) && Number.isFinite(Date.parse(v));
const sourceUrl = (v: unknown) => text(v) && (v === "" || (/^https?:\/\//i.test(v) && !/[\u0000-\u0020\\]/.test(v)));
const imageUrl = (v: unknown) => text(v) && !/[\u0000-\u0020\\]/.test(v) && (/^https?:\/\//i.test(v) || /^\/(?!\/)/.test(v));
const dimension = (v: unknown) => v === null || (number(v) && v > 0);
const fail = (): never => { throw new Error("日报数据格式异常，请稍后重试。"); };
function citation(value: unknown, depth = 0): value is ReportCitation {
  if (depth > 8 || !object(value) || !(value.itemId === null || uuid(value.itemId)) || !text(value.title) || !nullableText(value.summary) || !text(value.sourceName) || !sourceUrl(value.sourceUrl) || !(value.sourceIconUrl === null || imageUrl(value.sourceIconUrl)) || !(value.sourceIconSrcSet === undefined || text(value.sourceIconSrcSet)) || typeof value.firstParty !== "boolean" || !(value.publishedAt === null || timestamp(value.publishedAt)) || typeof value.available !== "boolean" || !(value.otherSources === undefined || count(value.otherSources)) || !(value.followUp === undefined || isDailyDate(value.followUp))) return false;
  return value.related === undefined || (Array.isArray(value.related) && value.related.every(r => citation(r, depth + 1)));
}
function navigation(value: unknown): value is ReportNavigationEntry {
  return object(value) && isDailyDate(value.key) && count(value.issueNumber) && value.issueNumber > 0 && (value.title === undefined || nullableText(value.title)) && (value.count === undefined || count(value.count));
}
function uniqueDates(items: ReportNavigationEntry[]) { return new Set(items.map(e => e.key)).size === items.length; }
export function parseReportDetail(value: unknown): ReportDetail {
  if (!object(value) || value.kind !== "daily" || !isDailyDate(value.key) || !count(value.issueNumber) || value.issueNumber < 1 || !text(value.title) || !timestamp(value.generatedAt) || !(value.lead === null || (object(value.lead) && text(value.lead.title) && text(value.lead.leadParagraph))) || !(value.leadItemId === null || uuid(value.leadItemId)) || !nullableText(value.overview) || !Array.isArray(value.highlights) || !value.highlights.every(c => citation(c)) || !Array.isArray(value.sections) || !value.sections.every(s => object(s) && text(s.label) && nullableText(s.summary) && Array.isArray(s.items) && s.items.every(c => citation(c))) || !Array.isArray(value.flashes) || !value.flashes.every(c => citation(c)) || !object(value.metrics) || !Object.values(value.metrics).every(count) || !count(value.readingMinutes) || value.readingMinutes < 1 || !(value.prev === null || isDailyDate(value.prev)) || !(value.next === null || isDailyDate(value.next))) return fail();
  if (value.cover !== null && (!object(value.cover) || !imageUrl(value.cover.url) || !(value.cover.srcSet === undefined || text(value.cover.srcSet)) || !dimension(value.cover.width) || !dimension(value.cover.height) || !nullableText(value.cover.caption))) return fail();
  return value as unknown as ReportDetail;
}
export function parseReportNavigation(value: unknown): ReportNavigationResponse {
  if (!object(value) || !Array.isArray(value.items) || !value.items.every(navigation) || !uniqueDates(value.items)) return fail();
  return value as unknown as ReportNavigationResponse;
}
export function parseReportIndex(value: unknown): ReportIndexResponse {
  if (!object(value) || value.kind !== "daily" || !Array.isArray(value.items) || !value.items.every(e => navigation(e) && nullableText(e.title) && count(e.count)) || !uniqueDates(value.items)) return fail();
  return value as unknown as ReportIndexResponse;
}
export function parseReportLatest(value: unknown): ReportLatestPage {
  if (!object(value) || !Array.isArray(value.index) || !value.index.every(navigation) || !uniqueDates(value.index)) return fail();
  if (value.report !== null) parseReportDetail(value.report);
  return value as unknown as ReportLatestPage;
}
