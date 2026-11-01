// Explicit display fixtures only. Real pages never fall back to these editions.
import { MOCK_SOURCES } from "../_lib/home-mock.ts";
import type { DailyRoute } from "./_route";
import type { ReportCitation, ReportDetail, ReportIndexEntry, ReportNavigationEntry } from "./_types";
export const DAILY_SECTIONS = ["产品发布与更新", "警务实战应用", "论文研究进展", "法制政策动态", "具身智能装备", "舆情治理观察", "低空警务应用"] as const;
// The same seven public-demo subjects as /all; IDs open the existing demo article reader.
const examples = [
  ["多模态检索工具增加警务知识引用核查能力", "工具将检索结果与公开材料逐条关联，便于人工回溯出处。产品功能不等同于经过验证的实战效果。"],
  ["基层接处警试点探索智能辅助与人工复核协同", "试点围绕信息整理、重复警情提示和人工确认展开，阶段性记录关注工作负荷与误报处置。"],
  ["研究比较公共安全视频分析中的跨场景泛化误差", "论文报告了不同场景下的评测条件、误差范围和限制，结论仍需结合实际部署环境理解。"],
  ["公共安全数据使用规范讨论留存期限与访问审计", "公开材料围绕数据最小化、使用边界和审计责任展开，具体要求应回到正式法规原文核查。"],
  ["巡检机器人测试面向复杂现场的移动感知协同", "测试关注遮挡、低照度和不平整路面的识别能力，仍处于验证阶段，尚不能据此推断规模化部署效果。"],
  ["公开舆情分析研究聚焦突发事件中的来源核验", "方法将时间、信源和可验证证据分开呈现，避免将传播热度直接当作事实可信度。"],
  ["低空应急巡查方案测试多机协同与飞行安全边界", "方案围绕航线调度、风险提示及现场信息回传展开，飞行许可与实测条件需单独确认。"],
];
function cite(index: number): ReportCitation {
  const source = MOCK_SOURCES.items[index % MOCK_SOURCES.items.length], [title, summary] = examples[index % 7];
  return { itemId: `a1100000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`, title: `${title}${index >= 7 ? ` · 观察 ${Math.floor(index / 7) + 1}` : ""}`, summary, sourceName: source.name, sourceUrl: "https://example.com/pulse-demo", sourceIconUrl: null, firstParty: index % 3 === 0, publishedAt: "2026-11-01T00:00:00Z", available: true };
}
const entries = Array.from({ length: 8 }, (_, i) => ({ ...cite(i), otherSources: i % 4 + 1, ...(i === 1 ? { followUp: "2026-10-29" } : {}) }));
entries[0] = { ...entries[0], related: [cite(14), cite(21)] } as typeof entries[number];
export const MOCK_REPORT: ReportDetail = {
  kind: "daily", key: "2026-11-01", issueNumber: 401, title: "AI日报 · 2026-11-01", generatedAt: "2026-11-01T00:00:00Z",
  lead: { title: entries[0].title, leadParagraph: entries[0].summary! }, leadItemId: entries[0].itemId, overview: null,
  highlights: entries.slice(1, 4), sections: DAILY_SECTIONS.map((label, i) => ({ label, summary: null, items: entries.filter((_, n) => n % 7 === i) })),
  flashes: [cite(28), { ...cite(29), followUp: "2026-10-30" }, cite(30)], cover: null,
  metrics: { totalEvents: 8, sourcesCount: 5, firstPartyEvents: 3 }, readingMinutes: 5, prev: "2026-10-31", next: null,
};
export const MOCK_REPORT_INDEX: ReportIndexEntry[] = ["2026-11-01", "2026-10-31", "2026-10-30", "2026-10-29", "2026-10-28", "2026-10-02", "2026-10-01", "2026-09-30", "2026-09-29"].map((key, i) => ({ key, issueNumber: 401 - i, title: examples[i % 7][0], count: 8 }));
export function mockDailyNavigation(key: string): ReportNavigationEntry[] {
  const at = MOCK_REPORT_INDEX.findIndex(e => e.key === key);
  return MOCK_REPORT_INDEX.map((e, n) => ({ key: e.key, issueNumber: e.issueNumber, ...(e.key.slice(0, 7) === key.slice(0, 7) || n < 3 || Math.abs(n - at) <= 1 ? { title: e.title } : {}) }));
}
export function mockDailyBundle(route: DailyRoute) {
  if (route.kind === "archive") return { report: null, index: structuredClone(MOCK_REPORT_INDEX) };
  const key = route.kind === "latest" ? MOCK_REPORT.key : route.key;
  const at = MOCK_REPORT_INDEX.findIndex(e => e.key === key);
  if (at < 0) return null;
  const report = structuredClone(MOCK_REPORT);
  Object.assign(report, { key, issueNumber: MOCK_REPORT_INDEX[at].issueNumber, title: `AI日报 · ${key}`, generatedAt: `${key}T00:00:00Z`, prev: MOCK_REPORT_INDEX[at + 1]?.key ?? null, next: MOCK_REPORT_INDEX[at - 1]?.key ?? null });
  return { report, index: mockDailyNavigation(key) };
}
