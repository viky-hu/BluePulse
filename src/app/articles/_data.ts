export interface SourceInfo {
  id: string;
  name: string;
  slug: string;
  source_type: string;
}

export interface ArticleCard {
  id: string;
  title: string;
  source_title: string;
  published_at: string | null;
  first_seen_at?: string | null;
  language: string;
  region: string | null;
  url: string;
  source: SourceInfo;
  importance_score: number;
  parse_status: string;
  body_status: "full_text" | "abstract_only" | "summary_only" | "metadata_only" | "partial_text";
  translation_status: "not_required" | "available" | "pending" | "failed" | "source_unavailable" | "too_long";
  summary?: string | null;
  topics?: string[];
  entities: Array<{ slug: string; name: string; entity_type: string }>;
}

export interface ArticleDetail extends ArticleCard {
  source_body: string | null;
  zh_body: string | null;
  summary: string | null;
  author: string | null;
  first_seen_at: string | null;
  quality_status: string;
  topics: string[];
  media: Array<{
    kind: string;
    url: string;
    thumbnail_url: string | null;
    caption: string | null;
    alt_text: string | null;
  }>;
}

export interface ArticleListResponse {
  items: ArticleCard[];
  next_cursor: string | null;
}

export interface TopicInfo {
  slug: string;
  name_zh: string;
}

export interface EntityInfo {
  slug: string;
  name: string;
  entity_type: string;
  region: string | null;
  article_count: number;
}

function apiBase(): string {
  return (process.env.BLUEPULSE_API_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
}

export async function readApi<T>(path: string): Promise<{ status: number; data: T | null }> {
  try {
    const response = await fetch(`${apiBase()}/api/v1${path}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(6000),
    });
    if (!response.ok) return { status: response.status, data: null };
    return { status: response.status, data: (await response.json()) as T };
  } catch {
    return { status: 0, data: null };
  }
}

export function formatArticleDate(value: string | null | undefined): string {
  if (!value) return "时间待核";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间待核";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(date);
}

export function formatArticleTimeline(article: Pick<ArticleCard, "published_at" | "first_seen_at">): string {
  if (article.published_at) return formatArticleDate(article.published_at);
  return article.first_seen_at ? `发现于 ${formatArticleDate(article.first_seen_at)}` : "时间待核";
}

export function formatRegion(value: string | null | undefined): string {
  return value === "domestic" ? "国内" : value === "foreign" ? "国外" : "地区待核";
}

export function safeSourceUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : null;
  } catch {
    return null;
  }
}
