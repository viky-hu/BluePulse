export const adminSections = {
  runs: "运行与回执",
  sources: "信源",
  content: "内容与事件",
  daily: "日报",
  feedback: "反馈",
  models: "模型",
  evaluations: "评测",
  audit: "审计",
} as const;

export type AdminSection = keyof typeof adminSections;
