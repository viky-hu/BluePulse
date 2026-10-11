"use client";
import { useEffect } from "react";
import { useBrowserState } from "../../_lib/use-browser-state";
import type { ArticleCard } from "../../_lib/home-data";
import { useMainShell } from "./MainShell";
import styles from "./home.module.css";

export type ArticleSnapshotInput = {
  id: string; title: string; summary?: string | null; published_at: string | null;
  importance_score: number; source: { name: string }; source_title?: string; url?: string;
  language?: string; region?: string | null; first_seen_at?: string | null;
};
export function ArticleActions({ article, recordRead = false }: { article: ArticleSnapshotInput; recordRead?: boolean }) {
  const { mock } = useMainShell();
  const { state, store } = useBrowserState(mock);
  const starred = state.starred.some(item => item.id === article.id);
  useEffect(() => {
    if (!recordRead) return;
    store.recordRead({
      id: article.id, title: article.title, summary: article.summary ?? null,
      published_at: article.published_at, first_seen_at: article.first_seen_at ?? null, importance_score: article.importance_score,
      source_title: article.source_title ?? article.title, url: article.url ?? "",
      language: article.language ?? "zh", region: article.region === "domestic" || article.region === "foreign" ? article.region : null,
      country_code: null, processing_status: "processed", parse_status: "parsed",
      source: { id: "", name: article.source.name, slug: "", region: null, country_code: null, language: "zh", source_type: "", topics: [] },
    } as ArticleCard);
  }, [article, recordRead, store]);
  return <button type="button" className={styles.starButton} data-star-id={article.id} aria-label={starred ? "取消收藏" : "收藏文章"} aria-pressed={starred} onClick={() => store.toggleStar({ id: article.id, title: article.title, summary: article.summary ?? null, sourceName: article.source.name, publishedAt: article.published_at, score: Number.isFinite(article.importance_score) ? article.importance_score : null })}>{starred ? "★ 已收藏" : "☆ 收藏"}</button>;
}
