import type { ArticleCard, ArticleDetail, ArticleListResponse } from "../_lib/home-data";
import { MOCK_SOURCES, MOCK_TAXONOMY } from "../_lib/home-mock";
import { CONTENT_FILTERS } from "./_data";
import type { HomeFilters } from "../_components/home/home-routes";

// Explicit demonstrations, never used as recovery for live API errors.
export const ALL_MOCK_TAXONOMY = [...MOCK_TAXONOMY.items, ...CONTENT_FILTERS.map(item => ({ id: `demo-${item.key}`, slug: item.key, name_zh: item.label, name_en: item.key, parent_id: null }))];
const examples = [
  ["多模态检索工具增加警务知识引用核查能力", "工具将检索结果与公开材料逐条关联，便于人工回溯出处。产品功能不等同于经过验证的实战效果。"],
  ["基层接处警试点探索智能辅助与人工复核协同", "试点围绕信息整理、重复警情提示和人工确认展开，阶段性记录关注工作负荷与误报处置。"],
  ["研究比较公共安全视频分析中的跨场景泛化误差", "论文报告了不同场景下的评测条件、误差范围和限制，结论仍需结合实际部署环境理解。"],
  ["公共安全数据使用规范讨论留存期限与访问审计", "公开材料围绕数据最小化、使用边界和审计责任展开，具体要求应回到正式法规原文核查。"],
  ["巡检机器人测试面向复杂现场的移动感知协同", "测试关注遮挡、低照度和不平整路面的识别能力，仍处于验证阶段，尚不能据此推断规模化部署效果。"],
  ["公开舆情分析研究聚焦突发事件中的来源核验", "方法将时间、信源和可验证证据分开呈现，避免将传播热度直接当作事实可信度。"],
  ["低空应急巡查方案测试多机协同与飞行安全边界", "方案围绕航线调度、风险提示及现场信息回传展开，飞行许可与实测条件需单独确认。"],
];
export function makeAllMockItems(now = Date.now()): ArticleCard[] {
  return Array.from({ length: 48 }, (_, index) => {
    const [title, summary] = examples[index % examples.length];
    const at = new Date(now - index * 45 * 60_000).toISOString();
    const source = MOCK_SOURCES.items[index % MOCK_SOURCES.items.length];
    return { id: `a1100000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`, title: `${title}${index >= 7 ? ` · 观察 ${Math.floor(index / 7) + 1}` : ""}`, summary, source_title: title, source, published_at: index === 9 ? null : at, first_seen_at: at, language: source.language, region: source.region, country_code: source.country_code, url: "https://example.com/pulse-demo", importance_score: Math.max(30, 94 - index), processing_status: "complete", parse_status: "summary_only", body_status: "summary_only", translation_status: "source_unavailable", topics: [CONTENT_FILTERS[index % CONTENT_FILTERS.length].key, source.topics[0]], media_preview: null };
  });
}
const items = makeAllMockItems();
export function mockAllFeed(filters: HomeFilters, cursor: string | null): ArticleListResponse {
  const days = { "24h": 1, "7d": 7, "30d": 30, all: Infinity }[filters.period];
  const cutoff = Date.now() - days * 86400000;
  const q = filters.q.toLocaleLowerCase();
  const rows = items.filter(item => (!filters.topic || item.topics?.includes(filters.topic)) && (!filters.region || item.region === filters.region) && (!filters.source || item.source.id === filters.source) && (!filters.sourceType || item.source.source_type === filters.sourceType) && !filters.entity && Date.parse(item.published_at ?? item.first_seen_at!) >= cutoff && (!q || `${item.title} ${item.summary}`.toLocaleLowerCase().includes(q))).sort((a, b) => filters.sort === "importance" ? b.importance_score - a.importance_score : Date.parse(b.published_at ?? b.first_seen_at!) - Date.parse(a.published_at ?? a.first_seen_at!));
  const offset = /^mock-all-\d+$/.test(cursor ?? "") ? Number(cursor!.slice(9)) : 0;
  return { items: rows.slice(offset, offset + 40), limit: 40, next_cursor: rows.length > offset + 40 ? `mock-all-${offset + 40}` : null };
}
export function mockAllDetail(id: string): ArticleDetail | null {
  const item = items.find(item => item.id === id);
  return item ? { ...item, source_body: null, zh_body: null, author: null, fetched_at: item.first_seen_at ?? null, quality_status: "demo", media: [], comments: { available: false, count: 0, items: [] }, summary: `【演示数据】${item.summary} 本条用于展示 Pulse 页面交互，并非实际新闻。` } : null;
}
