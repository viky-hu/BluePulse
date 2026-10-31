"use client";
// AIHOT DayList / TimelineSlot (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import { useMemo } from "react";
import type { ArticleCard, Topic } from "../_lib/home-data";
import { FeedItem } from "../_components/feed/FeedItem";
import { DayHeader, TimelineSlot } from "../_components/feed/TimelineParts";
import { articleMoment, groupAllItems } from "./_data";
import styles from "../_components/feed/feed.module.css";

export function DayList({ articles, taxonomy }: { articles: ArticleCard[]; taxonomy: Topic[] }) {
  const groups = useMemo(() => groupAllItems(articles), [articles]);
  return <div className={styles.days}>{groups.map(group => <section key={group.key} aria-label={group.day ?? "日期待核"}>
    <DayHeader day={group.day} />
    <ol className={styles.slots}>{group.items.map(article => {
      const moment = articleMoment(article);
      return <TimelineSlot key={article.id} at={moment.at} dataKey={article.id} discovered={moment.discovered}><FeedItem article={article} taxonomy={taxonomy} showTags /></TimelineSlot>;
    })}</ol>
  </section>)}</div>;
}
