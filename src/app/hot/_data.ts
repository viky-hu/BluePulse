// AIHOT site hot contract adapted to the existing Pulse HTTP boundary (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import type { HotResponse } from "./_types";

const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === "string";
const nullableText = (v: unknown) => v === null || text(v);
const number = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const count = (v: unknown): v is number => number(v) && Number.isInteger(v) && v >= 0;
const publicId = /^[a-zA-Z0-9_-]{1,80}$/;
const imageUrl = (v: unknown) => text(v) && (/^https?:\/\//i.test(v) || /^\/(?!\/)/.test(v));
const dimension = (v: unknown) => v === null || (number(v) && v > 0);

/** Reject broken payloads; never fill missing fields with fabricated values or empty results. */
export function parseHot(value: unknown): HotResponse {
  const fail = () => { throw Error("热点榜数据格式异常，请稍后重试。"); };
  if (!object(value) || !(value.computedAt === null || (text(value.computedAt) && Number.isFinite(Date.parse(value.computedAt)))) || !number(value.windowHours) || value.windowHours <= 0 || !Array.isArray(value.entries) || value.entries.length > 10) return fail();
  const stories = new Set<string>(), ranks = new Set<number>();
  for (const e of value.entries) {
    if (!object(e) || !count(e.rank) || e.rank < 1 || e.rank > 10 || !object(e.story) || !text(e.story.publicId) || !publicId.test(e.story.publicId) || !text(e.story.title) || !e.story.title.trim() || !number(e.heat) || e.heat < 0 || (!text(e.trend) || !["up", "down", "flat", "new", "unknown"].includes(e.trend)) || !(e.trendPct === null || number(e.trendPct)) || !Array.isArray(e.badges) || !e.badges.every((b: unknown) => text(b) && ["surge", "new", "rising"].includes(b)) || !count(e.participantCount) || !count(e.sourceCount) || !Array.isArray(e.sourceNames) || !e.sourceNames.every(text) || !Array.isArray(e.participants) || !Array.isArray(e.spark) || !e.spark.every((n: unknown) => n === null || (number(n) && n >= 0)) || !nullableText(e.summary) || !nullableText(e.latest)) return fail();
    if (stories.has(e.story.publicId) || ranks.has(e.rank)) return fail();
    stories.add(e.story.publicId); ranks.add(e.rank);
    const names = new Set<string>();
    for (const p of e.participants) {
      if (!object(p) || !text(p.name) || !p.name.trim() || names.has(p.name) || (!text(p.kind) || !["editorial", "signal"].includes(p.kind)) || !(p.iconUrl === undefined || p.iconUrl === null || imageUrl(p.iconUrl)) || !(p.iconSrcSet === undefined || text(p.iconSrcSet))) return fail();
      names.add(p.name);
    }
    if (e.cover !== null && (!object(e.cover) || !imageUrl(e.cover.url) || !(e.cover.srcSet === undefined || text(e.cover.srcSet)) || !dimension(e.cover.width) || !dimension(e.cover.height))) return fail();
  }
  return value as unknown as HotResponse;
}

const date = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
export function monthDayTime(iso: string) {
  const parts = date.formatToParts(new Date(iso));
  const get = (name: Intl.DateTimeFormatPartTypes) => parts.find(p => p.type === name)?.value ?? "";
  return `${get("month")}月${get("day")}日 ${get("hour")}:${get("minute")}`;
}
