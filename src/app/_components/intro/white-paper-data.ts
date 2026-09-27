export interface WhitePaperArticle {
  id: "p0" | "p1" | "p2" | "p3" | "p4" | "p5";
  date: string;
  title: string;
}

export const MOCK_WHITE_PAPER_ARTICLES: WhitePaperArticle[] = [
  {
    id: "p0",
    date: "2026.09.20",
    title: "湖北天门：筹建公安大模型智能运算体系",
  },
  {
    id: "p1",
    date: "2026.09.12",
    title: "浙江丽水：“丽警星系”形成大规模警务 AI Agent 生态",
  },
  {
    id: "p2",
    date: "2026.09.11",
    title: "上海浦东：建设基于大模型的执法监督平台",
  },
  {
    id: "p3",
    date: "2026.08.27",
    title: "宝鸡公安展示 AI 智能体实战应用",
  },
  {
    id: "p4",
    date: "2026.08.06",
    title: "公安部交通管理科学研究所采购大模型微调训练服务器",
  },
  {
    id: "p5",
    date: "2026.01.01",
    title: "无锡：855.51 万元建设警务大模型综合应用项目",
  },
];
