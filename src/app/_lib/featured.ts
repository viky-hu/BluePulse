import {
  MOCK_WHITE_PAPER_ARTICLES,
  type WhitePaperArticle,
} from "../_components/intro/white-paper-data";

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

const WHITE_PAPER_IDS = ["p0", "p1", "p2", "p3", "p4", "p5"] as const;

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
    if (!response.ok) return MOCK_WHITE_PAPER_ARTICLES;

    const payload = (await response.json()) as FeaturedResponse;
    if (!Array.isArray(payload.items) || payload.items.length === 0) {
      return MOCK_WHITE_PAPER_ARTICLES;
    }

    const articles = new Map(
      MOCK_WHITE_PAPER_ARTICLES.map((article) => [article.id, article]),
    );

    for (const item of payload.items) {
      if (
        typeof item.slot !== "string" ||
        !WHITE_PAPER_IDS.includes(item.slot as (typeof WHITE_PAPER_IDS)[number]) ||
        !item.article
      ) {
        continue;
      }

      const id = item.slot as WhitePaperArticle["id"];
      const fallback = articles.get(id)!;
      const article: WhitePaperArticle = {
        id,
        date: formatDate(item.article.published_at) ?? fallback.date,
        title:
          typeof item.article.title === "string" && item.article.title.trim()
            ? item.article.title.trim()
            : fallback.title,
      };
      if (isSafeHttpUrl(item.article.url)) article.url = item.article.url;
      articles.set(id, article);
    }

    return WHITE_PAPER_IDS.map((id) => articles.get(id)!);
  } catch {
    return MOCK_WHITE_PAPER_ARTICLES;
  }
}
