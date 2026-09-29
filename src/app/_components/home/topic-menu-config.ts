import type { Topic } from "../../_lib/home-data";

export const TOPIC_MENU_GROUPS = [
  {
    id: "application-scenarios",
    label: "应用与场景",
    slugs: ["policing", "public-safety-tech"],
  },
  {
    id: "technology-foundation",
    label: "技术与基础",
    slugs: ["artificial-intelligence", "cybersecurity", "research"],
  },
  {
    id: "governance-delivery",
    label: "规范与建设",
    slugs: ["policy-standards", "procurement-projects"],
  },
] as const;

export const TOPIC_MENU_SLUGS: ReadonlySet<string> = new Set(TOPIC_MENU_GROUPS.flatMap((group) => group.slugs));

export const TOPIC_MENU_LABELS: Record<string, string> = {
  policing: "警务应用",
  "public-safety-tech": "公共安全技术装备",
  "artificial-intelligence": "AI 与大模型",
  cybersecurity: "网络与数据安全",
  research: "研究成果",
  "policy-standards": "政策与标准",
  "procurement-projects": "采购与项目",
};

export type TopicMenuEntry = {
  slug: string;
  topic: Topic | null;
  available: boolean;
};

export type TopicMenuGroup = {
  id: string;
  label: string;
  topics: TopicMenuEntry[];
};

export function buildTopicMenuGroups(topics: Topic[]): TopicMenuGroup[] {
  const bySlug = new Map(topics.map((topic) => [topic.slug, topic]));
  return TOPIC_MENU_GROUPS.map((group) => ({
    id: group.id,
    label: group.label,
    topics: group.slugs.map((slug) => ({
      slug,
      topic: bySlug.get(slug) ?? null,
      available: bySlug.has(slug),
    })),
  }));
}
