"use client";
// AIHOT DayList / TimelineSlot / FeedItem / ScoreLabel / StarButton (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import Link from "next/link";
import { useMemo, useState } from "react";
import type { ArticleCard, Topic } from "../_lib/home-data";
import { useBrowserState } from "../_lib/use-browser-state";
import { useMainShell } from "../_components/home/MainShell";
import { ARTICLE_TOPIC_LABELS } from "../_components/home/article-topic-labels";
import { CONTENT_FILTERS, articleMoment, dayHeading, groupAllItems } from "./_data";
import { IntentLink } from "./IntentLink";
import { FeedIcon } from "./FeedIcons";
import styles from "./all.module.css";

function ScoreLabel({ score, compact = false }: { score: number; compact?: boolean }) {
  if (!Number.isFinite(score)) return null;
  const value = Math.round(score);
  return <span className={styles.score} data-tier={value >= 85 ? "hot" : value >= 70 ? "accent" : "quiet"} title={`AI 评分 ${value}/100`} aria-label={`AI 评分 ${value} 分`}>
    {!compact && <><span className={styles.scoreCaption}>AI 评分</span><span className={styles.scoreDivider} aria-hidden="true" /></>}
    <span className={styles.scoreValue}>{value}</span>
  </span>;
}
function FeedItem({ article, taxonomy }: { article: ArticleCard; taxonomy: Topic[] }) {
  const shell = useMainShell();
  const { state, store } = useBrowserState(shell.mock);
  const [pulse, setPulse] = useState(0);
  const read = ("readIds" in state && Array.isArray(state.readIds) ? state.readIds : state.history.map(item => item.article.id)).includes(article.id);
  const starred = state.starred.some(item => item.id === article.id);
  const moment = articleMoment(article);
  const topics = article.topics?.filter(topic => typeof topic === "string").slice(0, 3) ?? [];
  return <article className={styles.card} data-read={read} data-item-id={article.id}>
    <header className={styles.cardMeta}>
      <span className={styles.source} title={article.source.name}>{article.source.name}</span>
      <time dateTime={moment.at ?? undefined} className={styles.inlineTime} title={moment.discovered ? `原文日期待核，发现于 ${moment.at}` : undefined}>· {moment.discovered ? "待核" : moment.time ?? "待核"}</time>
      <span className={styles.cardActions}>
        <span className={styles.desktopScore}><ScoreLabel score={article.importance_score} /></span>
        <span className={styles.mobileScore}><ScoreLabel score={article.importance_score} compact /></span>
        <span className={styles.bookmarkWrap}><button type="button" className={styles.bookmark} aria-label={starred ? "取消收藏" : "收藏"} aria-pressed={starred} title={starred ? "取消收藏" : "收藏"} onClick={() => {
          const adding = !store.getSnapshot().starred.some(item => item.id === article.id);
          store.toggleStar({ id: article.id, title: article.title, summary: article.summary ?? null, sourceName: article.source.name, publishedAt: article.published_at, score: article.importance_score });
          if (adding) setPulse(value => value + 1);
        }}><span key={pulse} className={pulse ? styles.bump : undefined}><FeedIcon name="bookmark" filled={starred} /></span></button></span>
      </span>
    </header>
    <h3><IntentLink className={styles.articleLink} href={shell.href(`/articles/${article.id}`)} onClick={() => store.recordRead(article)}>{article.title || article.source_title}</IntentLink></h3>
    {article.summary && <p className={styles.summary}>{article.summary}</p>}
    {!!topics.length && <div className={styles.topicLinks}>{topics.map(topic => <Link key={topic} href={shell.href(`/all?topic=${encodeURIComponent(topic)}`)}>{CONTENT_FILTERS.find(item => item.key === topic)?.label ?? taxonomy.find(item => item.slug === topic)?.name_zh ?? ARTICLE_TOPIC_LABELS[topic] ?? topic}</Link>)}</div>}
    {article.featured_reason && <div className={styles.reason}><p>推荐理由：{article.featured_reason}</p></div>}
  </article>;
}
export function DayList({ articles, taxonomy }: { articles: ArticleCard[]; taxonomy: Topic[] }) {
  const groups = useMemo(() => groupAllItems(articles), [articles]);
  return <div className={styles.days}>{groups.map(group => {
    const heading = dayHeading(group.day);
    return <section key={group.key} aria-label={group.day ?? "日期待核"}>
      <div className={styles.dayHeader}>{group.day ? <time dateTime={group.day}>{heading.label}</time> : <span>{heading.label}</span>}<span className={styles.weekday}>{heading.weekday}</span><span className={styles.shortWeekday}>{heading.weekday.replace("星期", "周")}</span></div>
      <ol className={styles.slots}>{group.items.map(article => {
        const moment = articleMoment(article);
        return <li key={article.id} className={styles.slot} data-card-key={article.id}>
          <time className={styles.timeRail} dateTime={moment.at ?? undefined} title={moment.discovered ? `原文日期待核，发现于 ${moment.at}` : undefined}>{moment.discovered ? "待核" : moment.time ?? "待核"}</time>
          <span className={styles.rail} aria-hidden="true"><i /></span><FeedItem article={article} taxonomy={taxonomy} />
        </li>;
      })}</ol>
    </section>;
  })}</div>;
}
