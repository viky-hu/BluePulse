import assert from "node:assert/strict";
import { TOPIC_MENU_GROUPS, buildTopicMenuGroups } from "../src/app/_components/home/topic-menu-config.ts";

const topics = [
  { id: "1", slug: "research", name_zh: "研究成果", name_en: "Research", parent_id: null },
  { id: "2", slug: "policing", name_zh: "警务应用", name_en: "Policing", parent_id: null },
  { id: "3", slug: "unlisted", name_zh: "不应出现", name_en: "Hidden", parent_id: null },
  { id: "4", slug: "artificial-intelligence", name_zh: "AI 与大模型", name_en: "AI & LLMs", parent_id: null },
];

const groups = buildTopicMenuGroups(topics);

assert.deepEqual(
  groups.map((group) => [group.label, group.topics.map((topic) => topic.slug)]),
  [
    ["应用与场景", ["policing", "public-safety-tech"]],
    ["技术与基础", ["artificial-intelligence", "cybersecurity", "research"]],
    ["规范与建设", ["policy-standards", "procurement-projects"]],
  ],
  "groups should keep the fixed three-group and seven-topic order",
);

assert.equal(groups[0].topics[1].available, false, "missing topics should keep a disabled slot");
assert.equal(groups[1].topics[0].topic?.name_zh, "AI 与大模型");
assert.equal(groups.flatMap((group) => group.topics).some((topic) => topic.topic?.slug === "unlisted"), false);
assert.equal(TOPIC_MENU_GROUPS.length, 3);

console.log("topic menu configuration checks passed");
