/** AIHOT supplies UI patterns; only README's explicit selection supplies Pulse's menu items. */
export type MenuIcon = "bolt" | "list" | "flame" | "doc" | "plug" | "heart" | "history" | "message" | "bookmark";
export type MenuItem = { href: string; label: string; icon: MenuIcon };

export const MENU_SECTIONS: readonly { title: string; items: readonly MenuItem[] }[] = [
  { title: "内容", items: [
    { href: "/", label: "精选", icon: "bolt" },
    { href: "/all", label: "全部动态", icon: "list" },
    { href: "/hot", label: "热点榜", icon: "flame" },
    { href: "/daily", label: "AI日报", icon: "doc" },
    { href: "/starred", label: "收藏", icon: "bookmark" },
  ] },
  { title: "更多", items: [
    { href: "/agent", label: "Agent 接入", icon: "plug" },
    { href: "/about", label: "关于", icon: "heart" },
    { href: "/changelog", label: "更新日志", icon: "history" },
    { href: "/feedback", label: "反馈", icon: "message" },
  ] },
];

export const SECTION_PAGES = {
  "/hot": { title: "热点榜", description: "追踪国内外警务科技领域正在受到关注的事件。", status: "热点榜正在建设中，事件热度服务尚未接入。" },
  "/daily": { title: "AI日报", description: "按刊期阅读警务科技资讯与重要进展。", status: "日报正在建设中，暂未发布正式刊期。" },
  "/agent": { title: "Agent 接入", description: "为智能体提供警务科技资讯的阅读入口。", status: "Agent 接入正在建设中，MCP、RSS 与 API 接入说明将在相应服务就绪后提供。" },
  "/about": { title: "关于 Pulse", description: "国内外警务科技情报系统。", status: "" },
  "/changelog": { title: "更新日志", description: "记录 Pulse 的功能改进与更新。", status: "" },
  "/feedback": { title: "反馈", description: "帮助 Pulse 改进内容与阅读体验。", status: "反馈渠道正在建设中。" },
} as const;

export type SectionPath = keyof typeof SECTION_PAGES;
export function isSectionPath(pathname: string): pathname is SectionPath {
  return Object.hasOwn(SECTION_PAGES, pathname);
}

export function isMenuItemActive(href: string, pathname: string): boolean {
  if (href === "/hot" && pathname.startsWith("/story/")) return true;
  if (href === "/") return pathname === "/";
  if (href === "/all" && pathname === "/articles") return true;
  return pathname === href || pathname.startsWith(`${href}/`);
}
