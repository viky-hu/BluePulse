import type { WhitePaperArticle } from "../_components/intro/white-paper-data";

interface FeaturedArticle {
  title?: unknown;
  published_at?: unknown;
  url?: unknown;
}

interface FeaturedItem {
  slot?: unknown;
  article?: FeaturedArticle;
}

interface FeaturedResponse {
  items?: FeaturedItem[];
}

function formatDate(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const date = value.slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(date) ? date.replaceAll("-", ".") : undefined;
}

function isSafeHttpUrl(value: unknown): value is string {
  if (typeof value !== "string") return false;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

export async function getFeaturedWhitePapers(): Promise<WhitePaperArticle[]> {
  const apiBase = (
    process.env.BLUEPULSE_API_URL ?? "http://127.0.0.1:8000"
  ).replace(/\/+$/, "");

  try {
    const response = await fetch(`${apiBase}/api/v1/home/featured`, {
      cache: "no-store",
      signal: AbortSignal.timeout(2000),
    });
    if (!response.ok) return [];

    const payload = (await response.json()) as FeaturedResponse;
    if (!Array.isArray(payload.items)) return [];
    const articles: WhitePaperArticle[] = [];

    for (const item of payload.items) {
      if (
        typeof item.slot !== "string" ||
        !/^p[0-5]$/.test(item.slot) ||
        !item.article
      ) {
        continue;
      }

      const id = item.slot as WhitePaperArticle["id"];
      const title = typeof item.article.title === "string" ? item.article.title.trim() : "";
      if (!title) continue;
      const article: WhitePaperArticle = {
        id,
        date: formatDate(item.article.published_at) ?? "日期待补",
        title,
      };
      if (isSafeHttpUrl(item.article.url)) article.url = item.article.url;
      articles.push(article);
    }

    return articles;
  } catch {
    return [];
  }
}
