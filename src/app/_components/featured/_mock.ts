// Explicit frontend demo; never substitutes for a live unavailable API.
import { MOCK_HOME_DATA } from "../../_lib/home-mock";
import { ALL_MOCK_TAXONOMY } from "../../all/_mock";
import type { FeedArticle, GroupReportsResponse, HotStripEntry, TimelineCard, TimelineFilters, TimelineResponse } from "../../_lib/feed-types";
import { groupTimeline } from "./_data";

export { ALL_MOCK_TAXONOMY as FEATURED_MOCK_TAXONOMY };
const topics = ["product", "practice", "paper", "law", "embodied", "public-opinion", "low-altitude"];
export const FEATURED_MOCK_CARDS: TimelineCard[] = Array.from({ length: 74 }, (_, index) => {
  const original = MOCK_HOME_DATA.articles[index % MOCK_HOME_DATA.articles.length];
  const at = new Date(Date.UTC(2026, 9, 30, 7, 25) - index * 47 * 60000).toISOString();
  const article: FeedArticle = { ...original, id: `f3300000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`, published_at: at, first_seen_at: at, title: index < 8 ? original.title : `${original.title}：阶段进展 ${Math.floor(index / 8) + 1}`, importance_score: 90 - index % 35, topics: [topics[index % topics.length]], selected: true, channel: "news", x: null, media_preview: null, featured_reason: original.featured_reason ?? "关注具体应用边界、公开证据与人工复核机制。" };
  if (index === 3) article.sameEvent = { id: "f3300000-0000-4000-8000-000000000001", title: MOCK_HOME_DATA.articles[0].title };
  return { key: `fact-demo-${index + 1}`, anchorAt: at, item: article, group: index % 4 === 0 ? { factId: `demo-${index + 1}`, additionalSourceCount: 3, reportCount: 4 } : null };
});
export const FEATURED_MOCK_HOT: HotStripEntry[] = [
  "警务大模型试点公布人工复核与数据使用边界", "低空警务装备进入公开测试阶段", "公共安全多模态研究发布评测方法", "执法辅助产品更新证据引用机制", "具身智能巡检公布场景适用条件",
].map((title, index) => ({ rank: index + 1, title, heat: 137.4 - index * 22.1, trend: (["up", "new", "flat", "down", "unknown"] as const)[index], storyPublicId: index === 1 ? null : `demo-event-${index + 1}`, itemId: FEATURED_MOCK_CARDS[index].item.id, participantCount: 10 - index, participants: ["公共安全研究", "警务技术观察", "装备实验室", "实践研究站", "法治观察", "低空研究组", "技术社区"].map((name, i) => ({ name, kind: i < 6 ? "editorial" as const : "signal" as const })) }));
export function mockTimeline(filters: TimelineFilters, cursor?: string | null): TimelineResponse {
  const rows = FEATURED_MOCK_CARDS.filter(c => (!filters.region || c.item.region === filters.region) && (!filters.topic || c.item.topics?.includes(filters.topic)));
  const offset = /^featured-\d+$/.test(cursor ?? "") ? Number(cursor!.slice(9)) : 0;
  const dayCounts = Object.fromEntries(groupTimeline(rows).map(g => [g.day, g.cards.length]));
  return { filters, cards: rows.slice(offset, offset + 20), nextCursor: offset + 20 < rows.length ? `featured-${offset + 20}` : null, hot: !filters.region && !filters.topic && !cursor ? FEATURED_MOCK_HOT : null, dayCounts };
}
export function getMockGroupReports(factId: string, filters: TimelineFilters): GroupReportsResponse {
  const parent = FEATURED_MOCK_CARDS.find(c => c.group?.factId === factId);
  if (!parent) return { factId, reports: [] };
  const reports = [parent, ...FEATURED_MOCK_CARDS.filter(c => c !== parent).slice(0, 3)].filter(c => (!filters.region || c.item.region === filters.region) && (!filters.topic || c.item.topics?.includes(filters.topic))).map(c => ({ id: c.item.id, title: c.item.title, source: { name: c.item.source.name }, timelineAt: c.anchorAt, originalUrl: c.item.url }));
  return { factId, reports };
}
