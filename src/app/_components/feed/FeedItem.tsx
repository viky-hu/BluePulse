"use client";
// AIHOT features/feed/FeedItem.tsx and features/item/QuotedPost.tsx (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import Link from "next/link";
import { memo } from "react";
import type { FeedArticle, GroupInfo, TimelineFilters } from "../../_lib/feed-types";
import type { Topic } from "../../_lib/home-data";
import { useBrowserState } from "../../_lib/use-browser-state";
import { ARTICLE_TOPIC_LABELS } from "../home/article-topic-labels";
import { useMainShell } from "../home/MainShell";
import { articleMoment, CONTENT_FILTERS } from "../../all/_data";
import { SameEventBadge, SelectedBadge } from "./Badge";
import { IntentLink } from "./IntentLink";
import { MediaThumbs, ScoreLabel, SourceLine, StarButton } from "./parts";
import { GroupButton, GroupSources } from "./ReadingGroup";
import styles from "./feed.module.css";

export const FeedItem = memo(function FeedItem({ article, taxonomy, showTags = false, at, group, filters }: { article: FeedArticle; taxonomy: Topic[]; showTags?: boolean; at?: string; group?: GroupInfo | null; filters?: TimelineFilters }) {
  const shell = useMainShell();
  const { state, store } = useBrowserState(shell.mock);
  const read = state.readIds.includes(article.id);
  const isX = article.channel === "x" && !!article.x;
  const moment = at ? articleMoment({ id: article.id, published_at: at }) : articleMoment(article);
  const showSources = !!group && (group.reportCount > 1 || group.additionalSourceCount > 0);
  const topics = showTags ? article.topics?.slice(0, 3) ?? [] : [];
  const quoted = isX ? article.x?.quoted : null;
  const open = () => store.recordRead(article);
  return <article className={styles.card} data-read={read} data-item-id={article.id}>
    <header className={styles.cardMeta}>
      <SourceLine article={article} />
      <time dateTime={moment.at ?? undefined} className={styles.inlineTime} title={moment.discovered ? `原文日期待核，发现于 ${moment.at}` : undefined}>· {moment.discovered ? "待核" : moment.time ?? "待核"}</time>
      {article.selected && <span className={styles.selectedMark}>{article.sameEvent ? <SameEventBadge /> : <SelectedBadge />}</span>}
      <span className={styles.cardActions}><span className={styles.desktopScore}><ScoreLabel score={article.importance_score} /></span><span className={styles.mobileScore}><ScoreLabel score={article.importance_score} compact /></span><span className={styles.bookmarkWrap}><StarButton article={article} /></span></span>
    </header>
    {isX ? article.summary ? <p className={styles.xText}><IntentLink className={styles.articleLink} href={shell.href(`/articles/${article.id}`)} onClick={open}>{article.summary}</IntentLink></p> : <IntentLink className={styles.emptyXLink} href={shell.href(`/articles/${article.id}`)} aria-label={`查看 ${article.x!.authorName} 的帖子`} onClick={open} /> : <>
      <h3><IntentLink className={styles.articleLink} href={shell.href(`/articles/${article.id}`)} onClick={open}>{article.title || article.source_title}</IntentLink></h3>
      {article.summary && <p className={styles.summary}>{article.summary}</p>}
    </>}
    {isX && !!article.x!.media.length && <MediaThumbs media={article.x!.media} />}
    {quoted?.text && <div className={styles.quoted}><div><span>引用</span><strong>{quoted.authorName || `@${quoted.handle}`}</strong>{quoted.authorName && quoted.handle && <span>@{quoted.handle}</span>}</div><p>{quoted.translation ?? quoted.text}</p></div>}
    {!!topics.length && <div className={styles.topicLinks}>{topics.map(topic => <Link key={topic} href={shell.href(`/all?topic=${encodeURIComponent(topic)}`)}>{CONTENT_FILTERS.find(item => item.key === topic)?.label ?? taxonomy.find(item => item.slug === topic)?.name_zh ?? ARTICLE_TOPIC_LABELS[topic] ?? topic}</Link>)}</div>}
    {article.sameEvent && <p className={styles.sameEvent}>同一新闻，精选展示<Link href={shell.href(`/articles/${article.sameEvent.id}`)}>《{article.sameEvent.title}》</Link></p>}
    {group && showSources && <div className={styles.desktopGroup}><GroupSources key={`${group.factId}:${filters?.region}:${filters?.topic}`} group={group} filters={filters} parentId={article.id} /></div>}
    {article.featured_reason && <div className={styles.reason}><p>推荐理由：{article.featured_reason}</p></div>}
    {group && showSources && <GroupButton group={group} filters={filters} parentId={article.id} />}
  </article>;
});
