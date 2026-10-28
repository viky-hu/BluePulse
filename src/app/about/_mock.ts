import { MOCK_HOME_ARTICLES } from "../_lib/home-mock";
import type { SiteStats } from "./_data";

const kinds = ["rss", "web_list", "json_list", "mp_account", "x_search"];
const subjects = ["警务应用", "公共安全装备", "执法规范", "网络安全", "交通科技", "应急通信", "数字取证", "研究成果", "政策标准", "采购项目"];
const channels = ["国内公开资讯", "海外技术观察", "机构发布", "研究资料", "行业观察", "地方实践", "学术动态", "项目公告", "标准动态", "社区讨论"];

/** Explicit about-page fixtures, never used to recover a failed live request. */
export const MOCK_SITE_STATS: SiteStats = {
  sources: 100,
  sourceKinds: Object.fromEntries(kinds.map(kind => [kind, 20])),
  items: 12864, selected: 386, dailies: 24,
  day: { collected: 218, selected: 12 },
  sampleSources: Array.from({ length: 100 }, (_, i) => ({
    name: `${channels[Math.floor(i / 10)]} · ${subjects[i % 10]}（演示）`,
    kind: kinds[i % kinds.length], heatOnly: i % 11 === 0,
  })),
  latest: MOCK_HOME_ARTICLES.items.slice(0, 8).map(item => ({ id: item.id, title: item.title, source: item.source.name })),
};
