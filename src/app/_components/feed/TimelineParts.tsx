"use client";
// AIHOT features/feed/Timeline.tsx (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import type { ReactNode } from "react";
import { articleMoment, dayHeading } from "../../all/_data";
import { FeedIcon } from "./FeedIcons";
import styles from "./feed.module.css";

export function DayHeader({ day, count = null, collapsed = false, onToggle }: { day: string | null; count?: number | null; collapsed?: boolean; onToggle?: () => void }) {
  const heading = dayHeading(day);
  const date = day ? <time dateTime={day}>{heading.label}</time> : <span>{heading.label}</span>;
  const icon = <span className={styles.dayChevron} data-collapsed={collapsed}><FeedIcon name="down" /></span>;
  const phoneRow = <><span className={styles.dayDate}>{heading.label}</span><span>{heading.weekday.replace("星期", "周")}</span><span className={styles.dayAside}>{count !== null && <span><span className={styles.number}>{count}</span> 条</span>}{onToggle && icon}</span></>;
  return <div className={styles.dayHeader} data-collapsible={!!onToggle}>
    {onToggle ? <button type="button" className={styles.mobileDayHeader} aria-expanded={!collapsed} aria-label={`${collapsed ? "展开" : "收起"}${heading.label}`} onClick={onToggle}>{phoneRow}</button> : <div className={styles.mobileDayHeader}>{phoneRow}</div>}
    <div className={styles.desktopDayHeader}>
      {onToggle ? <button className={styles.dayToggle} type="button" aria-expanded={!collapsed} onClick={onToggle}>{date}</button> : <span className={styles.dayDate}>{date}</span>}
      {onToggle && <button className={styles.desktopDayChevron} type="button" aria-expanded={!collapsed} aria-label={`${collapsed ? "展开" : "收起"}${heading.label}`} onClick={onToggle}>{icon}</button>}
      <span>{heading.weekday}{count !== null && <> · <span className={styles.number}>{count}</span> 条</>}</span>
    </div>
  </div>;
}

export function TimelineSlot({ at, children, dataKey, discovered = false, fresh = false, delay = 0 }: { at: string | null; children: ReactNode; dataKey?: string; discovered?: boolean; fresh?: boolean; delay?: number }) {
  const moment = articleMoment({ id: "", published_at: at });
  return <li className={`${styles.slot}${fresh ? ` ${styles.fresh}` : ""}`} data-card-key={dataKey} style={fresh ? { animationDelay: `${delay}ms` } : undefined}>
    <time className={styles.timeRail} dateTime={at ?? undefined} title={discovered ? `原文日期待核，发现于 ${at}` : undefined}>{discovered ? "待核" : moment.time ?? "待核"}</time>
    <span className={styles.rail} aria-hidden="true"><i /></span>{children}
  </li>;
}
