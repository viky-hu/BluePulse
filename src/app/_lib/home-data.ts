export type FeaturedSlot = "p0" | "p1" | "p2" | "p3" | "p4" | "p5";
export type ArticlePeriod = "24h" | "7d" | "30d";
export type ArticleSort = "recent" | "importance";
export type ArticleRegion = "domestic" | "foreign";

export interface Source {
  id: string;
  name: string;
  slug: string;
  region: ArticleRegion | null;
  country_code: string | null;
  language: string;
  source_type: string;
  topics: string[];
}

export interface Topic {
  id: string;
  slug: string;
  name_zh: string;
  name_en: string;
  parent_id: string | null;
}

export interface MediaPreview {
  kind: "image" | "video" | "audio" | string;
  url: string;
  thumbnail_url: string | null;
  alt_text: string | null;
  caption?: string | null;
}

export interface ArticleMedia extends MediaPreview {
  position?: number;
  status?: string;
}

export interface ArticleCard {
  id: string;
  title: string;
  source_title: string;
  published_at: string | null;
  first_seen_at?: string | null;
  language: string;
  region: ArticleRegion | null;
  country_code: string | null;
  url: string;
  source: Source;
  importance_score: number;
  processing_status: string;
  parse_status: string;
  topics?: string[];
  summary?: string | null;
  media_preview?: MediaPreview | null;
}

export interface FeaturedItem {
  slot: FeaturedSlot;
  article: ArticleCard;
  importance_score?: number;
}

export interface FeaturedResponse {
  generated_at: string | null;
  window_policy: string;
  items: FeaturedItem[];
}

export interface ArticleListResponse {
  items: ArticleCard[];
  next_cursor: string | null;
  limit: number;
}

export interface ArticleDetail extends ArticleCard {
  source_body: string | null;
  zh_body: string | null;
  author: string | null;
  fetched_at: string | null;
  quality_status: string;
  media: ArticleMedia[];
  comments: {
    available: boolean;
    count: number;
    items: unknown[];
  };
}

export interface ItemsResponse<T> {
  items: T[];
}

export interface HomeDataBundle {
  featured: ArticleCard[];
  articles: ArticleCard[];
  taxonomy: Topic[];
  sources: Source[];
  status?: "loading" | "ready" | "empty" | "error";
  error?: string;
}

/** Fetch helpers intentionally preserve backend failures; mock content is opt-in. */
export async function fetchHomeFeatured(
  signal?: AbortSignal,
): Promise<FeaturedResponse> {
  return fetchJson<FeaturedResponse>("/api/bluepulse/home/featured", signal);
}

export async function fetchHomeArticles(
  searchParams: URLSearchParams,
  signal?: AbortSignal,
): Promise<ArticleListResponse> {
  const query = searchParams.toString();
  return fetchJson<ArticleListResponse>(
    `/api/bluepulse/articles${query ? `?${query}` : ""}`,
    signal,
  );
}

export async function fetchArticleDetail(
  id: string,
  signal?: AbortSignal,
): Promise<ArticleDetail> {
  return fetchJson<ArticleDetail>(
    `/api/bluepulse/articles/${encodeURIComponent(id)}`,
    signal,
  );
}

export async function fetchTaxonomy(
  signal?: AbortSignal,
): Promise<ItemsResponse<Topic>> {
  return fetchJson<ItemsResponse<Topic>>("/api/bluepulse/taxonomy", signal);
}

export async function fetchSources(
  signal?: AbortSignal,
): Promise<ItemsResponse<Source>> {
  return fetchJson<ItemsResponse<Source>>("/api/bluepulse/sources", signal);
}

async function fetchJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, {
    cache: "no-store",
    ...(signal ? { signal } : {}),
  });
  if (!response.ok) {
    const requestId = response.headers.get("x-request-id");
    throw new Error(
      requestId
        ? `数据请求失败（${response.status}，请求编号 ${requestId}）`
        : `数据请求失败（${response.status}）`,
    );
  }
  return (await response.json()) as T;
}
