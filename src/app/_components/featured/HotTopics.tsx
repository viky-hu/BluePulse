"use client";
// Direct port of AIHOT features/feed/HotTopics.tsx (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import Link from "next/link";
import type { HotStripEntry } from "../../_lib/feed-types";
import { useMainShell } from "../home/MainShell";
import { Faces } from "../feed/Faces";
import { hotHref } from "./_data";
import styles from "./featured.module.css";

function TrendMark({ trend }: { trend: HotStripEntry["trend"] }) {
  if (trend === "unknown") return null;
  if (trend === "new") return <span className={styles.newMark}>新</span>;
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" role="img" aria-label={trend === "up" ? "热度上升" : trend === "down" ? "热度回落" : "热度持平"} className={trend === "up" ? styles.trendUp : undefined}>{trend === "up" ? <><path d="M3 17l6-6 4 4 8-8" /><path d="M15 7h6v6" /></> : trend === "down" ? <><path d="M3 7l6 6 4-4 8 8" /><path d="M15 17h6v-6" /></> : <path d="M5 12h14" />}</svg>;
}
export function HotTopics({ entries }: { entries: HotStripEntry[] }) {
  const shell = useMainShell();
  if (!entries.length) return null;
  return <section className={styles.hot} aria-labelledby="hot-topics">
    <div className={styles.hotHeader}><h2 id="hot-topics"><span className={styles.live} aria-hidden="true"><i /><b /></span>当前热点</h2><Link href={shell.href("/hot")}>完整榜单<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg></Link></div>
    <ol>{entries.slice(0, 5).map((entry, index) => <li key={entry.rank} data-hot-extra={index >= 3}>
      <Link className={styles.hotRow} href={shell.href(hotHref(entry))}>
        <span className={styles.rank} data-rank={index + 1}>{entry.rank}</span><span className={styles.hotTitle}>{entry.title}</span>
        <span className={styles.faces}><Faces participants={entry.participants} total={entry.participantCount} size={20} interactive={false} /></span>
        <span className={styles.heatAndTrend}><span className={styles.heat} title="热度指数"><strong>{Math.round(entry.heat)}</strong> 热度</span><span className={styles.trend}><TrendMark trend={entry.trend} /></span></span>
      </Link>
    </li>)}</ol>
  </section>;
}
