"use client";

// Adapted from AIHOT routes/more.tsx, MIT. Copyright (c) 2026 数字生命卡兹克.
// Pulse keeps the grouped rows, local counts and changelog marker. See THIRD_PARTY_NOTICES.md.
import type { ReactNode } from "react";
import { IntentLink } from "../_components/feed/IntentLink";
import { RouteReady, useMainShell } from "../_components/home/MainShell";
import { MenuIcon } from "../_components/home/menu/MenuIcon";
import { PhoneBar } from "../_components/home/mobile/MobileChrome";
import { useBrowserState } from "../_lib/use-browser-state";
import { useSiteState } from "../_lib/use-site-state";
import styles from "./more.module.css";

function Group({ title, children }: { title: string; children: ReactNode }) {
  return <section className={styles.group}><h2>{title}</h2><ul>{children}</ul></section>;
}

function Row({ href, label, icon, detail, unread }: {
  href: string; label: string; icon: Parameters<typeof MenuIcon>[0]["name"]; detail?: ReactNode; unread?: boolean;
}) {
  const shell = useMainShell();
  return <li><IntentLink href={shell.href(href)} className={styles.row}>
    <span className={styles.icon}><MenuIcon name={icon} /></span>
    <span className={styles.label}>{label}{unread && <span className={styles.dot} aria-label="有新的更新" />}</span>
    {detail !== undefined && <span className={styles.detail}>{detail}</span>}
    <svg className={styles.chevron} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m9 5 7 7-7 7" /></svg>
  </IntentLink></li>;
}

export function MorePage({ changelogVersion }: { changelogVersion: string }) {
  const shell = useMainShell();
  const { state: browser } = useBrowserState(shell.mock);
  const { state: site } = useSiteState(shell.mock);
  const unread = site.ready && (!site.seen || site.seen < changelogVersion);
  return <div className={styles.page} data-more-page>
    <RouteReady />
    <PhoneBar title="更多" />
    <h1 className={styles.heading}>更多</h1>
    <div className={styles.groups}>
      <Group title="本机阅读">
        <Row href="/starred" label="收藏" icon="bookmark" detail={browser.ready ? browser.starred.length : undefined} />
        <Row href="/history" label="浏览历史" icon="history" detail={browser.ready ? browser.history.length : undefined} />
        <Row href="/search" label="搜索" icon="search" />
      </Group>
      <Group title="工具与入口"><Row href="/agent" label="Agent 接入" icon="plug" detail="HTTP API" /></Group>
      <Group title="关于">
        <Row href="/about" label="关于 Pulse" icon="heart" />
        <Row href="/changelog" label="更新日志" icon="history" unread={unread} />
        <Row href="/feedback" label="意见反馈" icon="message" />
      </Group>
    </div>
    <p className={styles.note}>无需登录。收藏和最近阅读记录仅保存在当前浏览器，清除浏览器数据或更换设备后不会同步。</p>
  </div>;
}
