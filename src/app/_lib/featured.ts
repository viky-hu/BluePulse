import type { WhitePaperArticle } from "../_components/intro/white-paper-data";

interface FeaturedArticle {
  id?: unknown;
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
const EMPTY_WHITE_PAPERS: WhitePaperArticle[] = WHITE_PAPER_IDS.map((id) => ({
  id,
  date: "—",
  title: "暂无更多已审核情报",
}));

function emptyWhitePapers(firstTitle: string): WhitePaperArticle[] {
  return EMPTY_WHITE_PAPERS.map((article, index) =>
    index === 0 ? { ...article, title: firstTitle } : { ...article },
  );
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

function formatDate(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const date = value.slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(date) ? date.replaceAll("-", ".") : undefined;
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
    if (!response.ok) return emptyWhitePapers("精选资讯暂时无法载入");

    const payload = (await response.json()) as FeaturedResponse;
    if (!Array.isArray(payload.items) || payload.items.length === 0) {
      return emptyWhitePapers("近 7 天暂无符合条件的精选资讯");
    }

    const articles = new Map(
      EMPTY_WHITE_PAPERS.map((article) => [article.id, article]),
    );

    for (const item of payload.items) {
      if (
        typeof item.slot !== "string" ||
        !/^p[0-5]$/.test(item.slot) ||
        !item.article
      ) {
        continue;
      }

      const id = item.slot as WhitePaperArticle["id"];
      const title =
        typeof item.article.title === "string" ? item.article.title.trim() : "";
      if (!title) continue;
      const fallback = articles.get(id)!;
      const article: WhitePaperArticle = {
        id,
        date: formatDate(item.article.published_at) ?? fallback.date,
        title,
      };
      if (typeof item.article.id === "string" && /^[0-9a-f-]{36}$/i.test(item.article.id)) {
        article.url = `/articles/${item.article.id}`;
      } else if (isSafeHttpUrl(item.article.url)) {
        article.url = item.article.url;
      }
      articles.set(id, article);
    }

    return WHITE_PAPER_IDS.map((id) => articles.get(id)!);
  } catch {
    return emptyWhitePapers("精选资讯暂时无法载入");
  }
}
