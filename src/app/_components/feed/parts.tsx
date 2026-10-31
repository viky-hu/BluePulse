"use client";
// AIHOT features/feed/parts.tsx (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
/* eslint-disable @next/next/no-img-element -- source-sized media uses supplied URL/srcSet without an image proxy */
import { useState } from "react";
import type { FeedArticle, MediaView } from "../../_lib/feed-types";
import { useBrowserState } from "../../_lib/use-browser-state";
import { useMainShell } from "../home/MainShell";
import { FeedIcon } from "./FeedIcons";
import { Lightbox } from "./Lightbox";
import { SourceAvatar } from "./SourceAvatar";
import styles from "./feed.module.css";

export function SourceLine({ article }: { article: Pick<FeedArticle, "source" | "channel" | "x"> }) {
  if (article.channel === "x" && article.x) return <span className={styles.xSource}><SourceAvatar name={article.x.authorName} avatarUrl={article.x.avatarUrl} avatarSrcSet={article.x.avatarSrcSet} size={16} /><span className={styles.source}>{article.x.authorName}</span><span className={styles.xHandle}>@{article.x.handle}</span></span>;
  return <span className={styles.source} title={article.source.name}>{article.source.name}</span>;
}
export function ScoreLabel({ score, compact = false }: { score: number; compact?: boolean }) {
  if (!Number.isFinite(score)) return null;
  const value = Math.round(score);
  return <span className={styles.score} data-tier={value >= 85 ? "hot" : value >= 70 ? "accent" : "quiet"} title={`AI 评分 ${value}/100`} aria-label={`AI 评分 ${value} 分`}>
    {!compact && <><span className={styles.scoreCaption}>AI 评分</span><span className={styles.scoreDivider} aria-hidden="true" /></>}<span className={styles.scoreValue}>{value}</span>
  </span>;
}
export function StarButton({ article }: { article: FeedArticle }) {
  const shell = useMainShell();
  const { state, store } = useBrowserState(shell.mock);
  const [pulse, setPulse] = useState(0);
  const on = state.starred.some(item => item.id === article.id);
  return <button type="button" className={styles.bookmark} aria-label={on ? "取消收藏" : "收藏"} aria-pressed={on} title={on ? "取消收藏" : "收藏"} onClick={event => {
    event.preventDefault(); event.stopPropagation();
    const adding = !store.getSnapshot().starred.some(item => item.id === article.id);
    store.toggleStar({ id: article.id, title: article.title, summary: article.summary ?? null, sourceName: article.source.name, publishedAt: article.published_at, score: article.importance_score });
    if (adding) setPulse(value => value + 1);
  }}><span key={pulse} className={pulse ? styles.bump : undefined}><FeedIcon name="bookmark" filled={on} /></span></button>;
}
export function MediaThumbs({ media }: { media: MediaView[] }) {
  const [index, setIndex] = useState<number | null>(null);
  const images = media.filter(item => item.kind === "image").map(item => ({ src: item.fullUrl ?? item.url, alt: item.alt }));
  const shown = media.slice(0, 4);
  if (!shown.length) return null;
  return <><div className={styles.mediaThumbs}>{shown.map(item => {
    const Wrapper = item.kind === "image" ? "button" : "span";
    return <Wrapper key={item.url} {...(item.kind === "image" ? { type: "button" as const, "aria-label": `查看图片${item.alt ? `：${item.alt}` : ""}`, onClick: (event: React.MouseEvent) => { event.preventDefault(); event.stopPropagation(); setIndex(images.findIndex(image => image.src === (item.fullUrl ?? item.url))); } } : {})} className={styles.mediaThumb} data-single={shown.length === 1} data-image={item.kind === "image"}>
      <img src={item.poster ?? item.url} srcSet={item.srcSet} sizes={shown.length === 1 ? `${item.width && item.height ? Math.min(240, Math.ceil(112 * item.width / item.height)) : 240}px` : "112px"} width={item.width ?? undefined} height={item.height ?? undefined} alt={item.alt ?? ""} loading="lazy" decoding="async" />
      {item.kind === "video" && <span className={styles.videoPlay} aria-hidden="true"><span><svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M7 4.5v15a1 1 0 001.5.87l13-7.5a1 1 0 000-1.74l-13-7.5A1 1 0 007 4.5z" /></svg></span></span>}
    </Wrapper>;
  })}</div><Lightbox images={images} index={index} onIndex={setIndex} onClose={() => setIndex(null)} /></>;
}
