import type { RiverSource } from "./_river-drawing";
import { responseDeadline } from "../_lib/http-cache.ts";

/** AIHOT SiteStats shape; null means the backend cannot yet measure this figure. */
export interface SiteStats {
  sources: number | null;
  sourceKinds: Record<string, number>;
  items: number | null;
  selected: number | null;
  dailies: number | null;
  day: { collected: number | null; selected: number | null };
  sampleSources: RiverSource[];
  latest: Array<{ id: string; title: string; source: string }>;
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw Error("统计数据格式无效");
  return value as Record<string, unknown>;
}

function count(value: unknown): number | null {
  if (value === null) return null;
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) throw Error("统计数字无效");
  return value;
}

function text(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) throw Error("统计文本无效");
  return value;
}

export function parseSiteStats(value: unknown): SiteStats {
  const data = record(value), day = record(data.day), kinds = record(data.sourceKinds);
  if (!Array.isArray(data.sampleSources) || !Array.isArray(data.latest)) throw Error("统计样本无效");
  if (data.sampleSources.length > 180 || data.latest.length > 8) throw Error("统计样本超出约定数量");
  return {
    sources: count(data.sources), items: count(data.items), selected: count(data.selected), dailies: count(data.dailies),
    sourceKinds: Object.fromEntries(Object.entries(kinds).map(([kind, value]) => {
      const n = count(value);
      if (n === null) throw Error("信源类型数量无效");
      return [kind, n];
    })),
    day: { collected: count(day.collected), selected: count(day.selected) },
    sampleSources: data.sampleSources.map(value => {
      const source = record(value);
      if (typeof source.heatOnly !== "boolean") throw Error("信源参与方式无效");
      return { name: text(source.name), kind: text(source.kind), heatOnly: source.heatOnly };
    }),
    latest: data.latest.map(value => {
      const item = record(value), id = text(item.id);
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id)) throw Error("文章标识无效");
      return { id, title: text(item.title), source: text(item.source) };
    }),
  };
}

export class SiteStatsError extends Error {
  readonly status: number;
  constructor(status: number) { super(`统计请求失败（${status}）`); this.status = status; }
}

export async function fetchSiteStats(signal: AbortSignal, onDeadline?: (expiresAt: number) => void): Promise<SiteStats> {
  const response = await fetch("/api/bluepulse/site/stats", { cache: "no-store", signal });
  if (!response.ok) throw new SiteStatsError(response.status);
  onDeadline?.(responseDeadline(response.headers));
  return parseSiteStats(await response.json());
}
