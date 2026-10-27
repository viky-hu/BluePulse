"use client";

import { BranchedTopicMenu } from "./BranchedTopicMenu";
import { RouteReady, useMainShell } from "./MainShell";
import styles from "./section-page.module.css";

export function TopicsDirectory() {
  const shell = useMainShell();
  return <div className={styles.page}>
    <RouteReady />
    <header className={styles.header}><h1>主题</h1><p>从警务应用、技术研究与规范建设出发，浏览你关心的资讯。</p></header>
    <div className={styles.directory}>
      <BranchedTopicMenu topics={shell.topics} activeSlug="" status={shell.topicStatus} hrefForTopic={slug => shell.href(`/topics/${slug}`)} />
    </div>
  </div>;
}
