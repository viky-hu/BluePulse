// Explicit, isolated frontend demo. Never used as a fallback for the live ranking.
import type { HotResponse } from "./_types";

const titles = ["警务大模型试点公布人工复核与数据使用边界", "低空警务装备开展跨场景公开测试", "公共安全多模态研究发布评测方法", "执法辅助产品更新证据引用机制", "具身智能巡检明确适用场景与人工接管条件", "反诈技术研究讨论风险预警的解释方式", "移动警务终端升级现场信息核验流程", "隐私保护计算用于跨部门协作研究", "应急通信装备公布复杂环境测试结果", "智慧警务实践交流聚焦系统运行评估"];
const names = ["公共安全研究", "警务技术观察", "装备实验室", "实践研究站", "法治观察", "低空研究组", "技术社区", "应用研究机构"];
export const MOCK_HOT: HotResponse = {
  computedAt: "2026-10-31T04:20:00Z", windowHours: 48,
  entries: titles.map((title, i) => ({
    rank: i + 1, story: { publicId: `demo-event-${i + 1}`, title }, heat: 137.4 - i * 11.2,
    trend: (["up", "new", "flat", "down", "unknown"] as const)[i % 5], trendPct: i % 5 === 1 || i % 5 === 4 ? null : [32.5, 0, 2, -18.4, 0][i % 5],
    badges: i === 0 ? ["surge"] : i === 1 ? ["new"] : i === 2 ? ["rising"] : [],
    participantCount: 11 - Math.floor(i / 2), sourceCount: 7 - Math.floor(i / 3), sourceNames: names.slice(i % 2, 5),
    participants: names.slice(0, 8 - Math.floor(i / 4)).map((name, j) => ({ name, kind: j < 6 ? "editorial" : "signal" })),
    spark: Array.from({ length: 25 }, (_, h) => i % 5 === 4 || (i === 2 && h > 9 && h < 14) ? null : Math.round((15 + h * (2.5 - i * .14) + Math.sin(h / 2) * 5) * 10) / 10),
    summary: i === 0 ? "围绕检索引用、数据使用范围和人工审核环节展开试点，关注大模型辅助警务工作的适用边界与公开评估方法。" : "围绕具体应用、公开测试和实施条件展开讨论，关注可验证的技术进展与实践反馈。",
    latest: i === 0 ? "试点说明补充了人工复核流程和数据授权要求。" : null, cover: null,
  })),
};
