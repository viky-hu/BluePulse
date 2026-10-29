import { MOCK_ARTICLE_DETAILS, MOCK_HOME_ARTICLES, MOCK_SOURCES, MOCK_TAXONOMY } from "../_lib/home-mock";
import type { ArticleCard, ArticleDetail, ArticleListResponse } from "./_data";
import { mockAllDetail } from "../all/_mock";

/** Explicit demo fixtures only; this never participates in live-service recovery. */
export function mockArticle(id: string): ArticleDetail | null {
  const fixture = MOCK_ARTICLE_DETAILS[id] ?? mockAllDetail(id);
  return fixture ? {
    ...fixture,
    body_status: fixture.body_status ?? "metadata_only",
    translation_status: fixture.translation_status ?? "source_unavailable",
    summary: fixture.summary ?? null,
    first_seen_at: fixture.first_seen_at ?? null,
    topics: fixture.topics ?? [],
    entities: [],
    media: fixture.media.map((media) => ({ ...media, caption: media.caption ?? null })),
  } : null;
}

export function mockArticles(values: Record<string, string>, cursor: string, now = Date.now()): ArticleListResponse {
  const query = (values.q ?? "").toLocaleLowerCase();
  const days = { "24h": 1, "7d": 7, "30d": 30 }[values.period];
  const cutoff = days ? now - days * 86400000 : -Infinity;
  const articles = MOCK_HOME_ARTICLES.items.map((item) => mockArticle(item.id)!).filter((article) =>
    (!values.topic || article.topics.includes(values.topic)) &&
    (!values.region || article.region === values.region) &&
    (!values.source || article.source.id === values.source) &&
    (!values.source_type || article.source.source_type === values.source_type) &&
    (!values.entity || article.entities.some((entity) => entity.slug === values.entity)) &&
    (!days || Boolean(article.published_at && new Date(article.published_at).getTime() >= cutoff)) &&
    (!query || `${article.title} ${article.source_title} ${article.summary ?? ""}`.toLocaleLowerCase().includes(query))
  ).sort((a: ArticleCard, b: ArticleCard) => values.sort === "importance"
    ? b.importance_score - a.importance_score || a.id.localeCompare(b.id)
    : (b.published_at ?? "").localeCompare(a.published_at ?? "") || a.id.localeCompare(b.id));
  const requestedOffset = /^mock-\d+$/.test(cursor) ? Number(cursor.slice(5)) : 0;
  const offset = Number.isSafeInteger(requestedOffset) ? requestedOffset : 0;
  const pageSize = 8;
  return { items: articles.slice(offset, offset + pageSize), next_cursor: offset + pageSize < articles.length ? `mock-${offset + pageSize}` : null };
}

export { MOCK_SOURCES, MOCK_TAXONOMY };
