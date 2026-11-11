// Adapted from AIHOT components/shell/{nav,screens,TabBar}.ts(x), MIT.
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
export type MobileTabKey = "featured" | "all" | "hot" | "daily" | "more";
export const MOBILE_TABS: readonly { key: MobileTabKey; href: string; label: string; icon: "bolt" | "list" | "flame" | "doc" | "more" }[] = [
  { key: "featured", href: "/", label: "精选", icon: "bolt" },
  { key: "all", href: "/all", label: "全部", icon: "list" },
  { key: "hot", href: "/hot", label: "热点", icon: "flame" },
  { key: "daily", href: "/daily", label: "日报", icon: "doc" },
  { key: "more", href: "/more", label: "更多", icon: "more" },
];

export function mobileScreen(pathname: string): { tab?: MobileTabKey; fallback: MobileTabKey; title?: string; toolbar: boolean } {
  const toolbar = /^\/articles\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?:\/original)?$/i.test(pathname);
  const base = { fallback: "more" as const, toolbar };
  if (pathname === "/") return { ...base, tab: "featured", title: "精选" };
  if (pathname === "/all" || pathname === "/articles") return { ...base, tab: "all", title: "全部动态" };
  if (/^\/(hot|story)(\/|$)/.test(pathname)) return { ...base, tab: "hot", title: "热点榜" };
  if (/^\/daily(\/|$)/.test(pathname)) return { ...base, tab: "daily", title: "日报" };
  const titles: Record<string, string> = {
    "/more": "更多", "/starred": "收藏", "/history": "浏览历史", "/agent": "Agent 接入",
    "/about": "关于 Pulse", "/changelog": "更新日志", "/feedback": "反馈",
  };
  if (titles[pathname]) return { ...base, tab: "more", title: titles[pathname] };
  if (pathname === "/search") return { ...base, title: "搜索" };
  return base;
}

export function savedMobileTab(state: unknown): MobileTabKey | undefined {
  if (!state || typeof state !== "object") return undefined;
  const value = (state as { pulseMobileTab?: unknown }).pulseMobileTab;
  return MOBILE_TABS.some(tab => tab.key === value) ? value as MobileTabKey : undefined;
}

/** Keep Next's tree and navigation fields intact; no React Router history index is used. */
export function mobileTabState(state: unknown, tab: MobileTabKey): Record<string, unknown> {
  return { ...(state && typeof state === "object" ? state : {}), pulseMobileTab: tab };
}

export function canNoteMobileScreen(routeKey: string, browserHref: string): boolean {
  const canonical = (href: string) => {
    const url = new URL(href, "https://pulse.local");
    url.searchParams.delete("intro");
    url.searchParams.sort();
    return `${url.pathname}${url.search}`;
  };
  return canonical(routeKey) === canonical(browserHref);
}

export function mobileTabAction(target: MobileTabKey, active: MobileTabKey, pathname: string, scrollTop: number): "navigate" | "scroll" | "refresh" {
  if (target !== active || MOBILE_TABS.find(tab => tab.key === target)?.href !== pathname) return "navigate";
  return scrollTop > 0 ? "scroll" : "refresh";
}
