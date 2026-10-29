import { isSectionPath } from "./navigation-config.ts";
import type { ArticlePeriod, ArticleRegion, ArticleSort } from "../../_lib/home-data";

export type HomeFilters = {
  period: ArticlePeriod;
  q: string;
  topic: string;
  region: ArticleRegion | "";
  source: string;
  sourceType: string;
  entity: string;
  sort: ArticleSort;
};
export type HomeRoute = {
  kind: "home" | "search" | "all" | "section" | "history" | "starred" | "article" | "library" | "entities" | "unknown";
  filters: HomeFilters;
  cursor: string | null;
  articleId: string | null;
  valid: boolean;
};
export const ARTICLE_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function entryMode(pathname: string, completed: boolean): "intro" | "stable" {
  return pathname === "/" && !completed ? "intro" : "stable";
}

export function canonicalHref(href: string): string {
  const url = new URL(href, "https://pulse.local");
  url.searchParams.sort();
  return `${url.pathname}${url.search}`;
}

export function parseHomeRoute(pathname: string, search: string | { toString(): string }): HomeRoute {
  const params = new URLSearchParams(search.toString());
  const id = pathname.startsWith("/articles/") ? pathname.slice(10) : null;
  const kind: HomeRoute["kind"] = pathname === "/" ? "home"
    : pathname === "/search" ? "search"
    : pathname === "/all" ? "all"
    : isSectionPath(pathname) ? "section"
    : pathname === "/history" ? "history"
    : pathname === "/starred" ? "starred"
    : pathname === "/articles" ? "library"
    : pathname === "/entities" ? "entities"
    : id ? "article" : "unknown";
  const fallback = kind === "all" ? "all" : kind === "library" ? "30d" : "7d";
  const period = params.get("period");
  const region = params.get("region");
  const query = (params.get("q") ?? "").trim().slice(0, 200);
  return {
    kind,
    valid: kind !== "unknown" && (kind !== "article" || ARTICLE_ID_PATTERN.test(id ?? "")),
    articleId: id,
    cursor: kind === "all" && query && params.get("sort") === "importance" ? null : params.get("cursor") || null,
    filters: {
      period: period === "24h" || period === "7d" || period === "30d" || period === "all" ? period : fallback,
      q: query,
      topic: params.get("topic") ?? "",
      region: region === "domestic" || region === "foreign" ? region : "",
      source: params.get("source") ?? "",
      sourceType: params.get("source_type") ?? "",
      entity: params.get("entity") ?? "",
      sort: kind === "all" && query ? "recent" : params.get("sort") === "importance" ? "importance" : "recent",
    },
  };
}

export function buildHomeHref(pathname: string, filters?: HomeFilters, options: { cursor?: string | null; mock?: boolean } = {}): string {
  const params = new URLSearchParams();
  if (filters) {
    if (filters.period !== (pathname === "/all" ? "all" : pathname === "/articles" ? "30d" : "7d")) params.set("period", filters.period);
    if (filters.q) params.set("q", filters.q.trim().slice(0, 200));
    if (filters.topic) params.set("topic", filters.topic);
    if (filters.region) params.set("region", filters.region);
    if (filters.source) params.set("source", filters.source);
    if (filters.sourceType) params.set("source_type", filters.sourceType);
    if (filters.entity) params.set("entity", filters.entity);
    if (filters.sort !== "recent") params.set("sort", filters.sort);
  }
  if (options.cursor) params.set("cursor", options.cursor);
  if (options.mock) params.set("mock", "1");
  return `${pathname}${params.size ? `?${params}` : ""}`;
}
