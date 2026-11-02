// AIHOT item loader/meta, adapted to Next.js server boundaries and the existing Pulse API.
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import { cache } from "react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ArticlePage } from "./ArticlePage";
import { ARTICLE_ID_PATTERN, emptyArticlePage, normalizeArticle } from "./data";
import type { ArticlePageData } from "./types";
import { responseDeadline } from "../../_lib/http-cache";

export type ArticleRouteProps = { params: Promise<{ id: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> };
type Language = "zh" | "original";

// React cache deduplicates page and metadata work within the request; it does not extend freshness.
const serverArticle = cache(async (id: string, language: Language, mock: boolean): Promise<ArticlePageData> => {
  const result = emptyArticlePage(`/articles/${id}${language === "original" ? "/original" : ""}${mock ? "?mock=1" : ""}`);
  if (!ARTICLE_ID_PATTERN.test(id)) return { ...result, status: "not-found" };
  try {
    if (mock) {
      const { mockReaderArticle, mockReaderTaxonomy } = await import("./mock");
      const raw = mockReaderArticle(id, language);
      if (!raw) return { ...result, status: "not-found" };
      return { ...result, status: "ready", item: normalizeArticle(raw, language), taxonomy: mockReaderTaxonomy, expiresAt: Date.now() + 60_000 };
    }
    const base = (process.env.BLUEPULSE_API_URL ?? "http://127.0.0.1:8000").trim().replace(/\/+$/, "");
    const response = await fetch(`${base}/api/v1/articles/${id}?body_language=${language}`, { cache: "no-store", signal: AbortSignal.timeout(6000) });
    if (!response.ok) return { ...result, status: response.status === 404 ? "not-found" : "error", error: `文章暂时无法载入（${response.status}）。` };
    const item = normalizeArticle(await response.json(), language);
    let taxonomy: ArticlePageData["taxonomy"] = [], expiresAt = responseDeadline(response.headers);
    try {
      const taxonomyResponse = await fetch(`${base}/api/v1/taxonomy`, { cache: "no-store", signal: AbortSignal.timeout(6000) });
      const body = taxonomyResponse.ok ? await taxonomyResponse.json() : null;
      if (body && Array.isArray(body.items) && body.items.every((entry: { slug?: unknown; name_zh?: unknown }) => typeof entry?.slug === "string" && typeof entry.name_zh === "string")) { taxonomy = body.items; expiresAt = Math.min(expiresAt, responseDeadline(taxonomyResponse.headers)); }
      else expiresAt = 0;
    } catch { expiresAt = 0; }
    return { ...result, status: "ready", item, taxonomy, expiresAt };
  } catch { return { ...result, status: "error", error: "数据服务暂时不可用，请稍后重试。" }; }
});

export async function articleMetadata(props: ArticleRouteProps, language: Language): Promise<Metadata> {
  const [{ id }, search] = await Promise.all([props.params, props.searchParams]);
  const data = await serverArticle(id, language, search.mock === "1");
  if (!data.item) return { title: data.status === "not-found" ? "内容不存在 · Blue Pulse" : "暂时无法加载 · Blue Pulse", robots: { index: false, follow: false } };
  const item = data.item, article = item.article, canonical = `/articles/${id}`;
  const configuredOrigin = process.env.BLUEPULSE_SITE_ORIGIN;
  let metadataBase: URL | undefined;
  try { if (configuredOrigin) metadataBase = new URL(configuredOrigin); } catch { /* deployment configuration remains unset */ }
  return {
    ...(metadataBase ? { metadataBase } : {}), title: `${article.title} · Blue Pulse`, description: article.summary ?? undefined,
    alternates: { canonical }, robots: { index: search.mock !== "1" && item.indexable, follow: search.mock !== "1" },
    openGraph: { title: article.title, description: article.summary ?? undefined, type: "article", url: canonical, ...(article.published_at ? { publishedTime: article.published_at } : {}), ...(item.indexable && search.mock !== "1" ? { images: [`/api/bluepulse/articles/${id}/og.png`] } : {}) },
  };
}

export async function renderArticle(props: ArticleRouteProps, language: Language) {
  const [{ id }, search] = await Promise.all([props.params, props.searchParams]);
  if (!ARTICLE_ID_PATTERN.test(id)) notFound();
  const data = await serverArticle(id, language, search.mock === "1");
  if (data.status === "not-found") notFound();
  const query = new URLSearchParams();
  for (const [name, value] of Object.entries(search)) { if (Array.isArray(value)) value.forEach(entry => query.append(name, entry)); else if (value !== undefined) query.set(name, value); }
  query.sort();
  const key = `/articles/${id}${language === "original" ? "/original" : ""}${query.size ? `?${query}` : ""}`;
  const jsonLd = data.item?.indexable && search.mock !== "1" ? { "@context": "https://schema.org", "@type": "NewsArticle", headline: data.item.article.title, description: data.item.article.summary, datePublished: data.item.article.published_at ?? undefined, isBasedOn: data.item.article.url } : null;
  return <>{jsonLd && <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }} />}<ArticlePage initial={{ ...data, key }} /></>;
}
