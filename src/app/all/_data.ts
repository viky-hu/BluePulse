// Adapted from AIHOT all.tsx, Filters.tsx and DayList.tsx (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import type { HomeFilters } from "../_components/home/home-routes";

export const CONTENT_FILTERS = [
  { key: "product", label: "产品" },
  { key: "practice", label: "实战" },
  { key: "paper", label: "论文" },
  { key: "law", label: "法制" },
  { key: "embodied", label: "具身" },
  { key: "public-opinion", label: "舆情" },
  { key: "low-altitude", label: "低空" },
] as const;
export const ALL_FILTERS = [{ key: "all", label: "全部" }, { key: "domestic", label: "国内" }, { key: "foreign", label: "国外" }, ...CONTENT_FILTERS];
export const isContentFilter = (key: string) => CONTENT_FILTERS.some(item => item.key === key);
export function activeAllFilter(filters: HomeFilters) {
  if (filters.region && filters.topic) return "custom";
  return filters.region || (isContentFilter(filters.topic) ? filters.topic : filters.topic ? "custom" : "all");
}
export function selectAllFilter(filters: HomeFilters, key: string): HomeFilters {
  return { ...filters, topic: isContentFilter(key) ? key : "", region: key === "domestic" || key === "foreign" ? key : "" };
}
export function categorySupported(topic: string, taxonomy: { slug: string }[]) {
  return !isContentFilter(topic) || taxonomy.some(item => item.slug === topic);
}
export function allArticleParams(filters: HomeFilters, cursor: string | null) {
  const params = new URLSearchParams({ period: filters.period, sort: filters.sort, limit: "40" });
  for (const [key, value] of Object.entries({ q: filters.q, topic: filters.topic, region: filters.region, source: filters.source, source_type: filters.sourceType, entity: filters.entity, cursor })) if (value) params.set(key, value);
  return params;
}

type DatedItem = { id: string; published_at?: string | null; first_seen_at?: string | null };
const dayFormat = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" });
const timeFormat = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Shanghai", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const validDate = (date?: string | null) => !!date && Number.isFinite(Date.parse(date));
export function beijingDay(at: string | number) { return dayFormat.format(new Date(at)); }
export function articleMoment(item: DatedItem) {
  const published = validDate(item.published_at);
  const at = published ? item.published_at! : validDate(item.first_seen_at) ? item.first_seen_at! : null;
  return { day: at ? beijingDay(at) : null, time: at ? timeFormat.format(new Date(at)) : null, at, discovered: !published && !!at };
}
export function groupAllItems<T extends DatedItem>(items: T[]) {
  const groups: { key: string; day: string | null; items: T[] }[] = [];
  // Keep server ranking intact, including legacy importance sorting and repeated days.
  for (const item of items) {
    const day = articleMoment(item).day;
    const last = groups.at(-1);
    if (last && last.day === day) last.items.push(item);
    else groups.push({ key: `${day ?? "unknown"}:${item.id}`, day, items: [item] });
  }
  return groups;
}
export function dayHeading(day: string | null) {
  if (!day) return { label: "日期待核", weekday: "" };
  const [, month, date] = day.split("-");
  const short = `${Number(month)}月${Number(date)}日`;
  return { label: short, weekday: new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", weekday: "long" }).format(new Date(`${day}T12:00:00+08:00`)) };
}
