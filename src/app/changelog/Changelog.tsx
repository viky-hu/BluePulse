"use client";
// Adapted from AIHOT routes/changelog.tsx and features/changelog/text.tsx (MIT).
import { useEffect, useLayoutEffect, useState, type MouseEvent } from "react";
import Link from "next/link";
import { RouteReady, useMainShell } from "../_components/home/MainShell";
import { ReadingAsideCard, ReadingLayout } from "../_components/reading/ReadingLayout";
import { readSessionSnapshot, saveSessionSnapshot } from "../_lib/session-restore";
import { useSiteState } from "../_lib/use-site-state";
import { dateHeading, groupReleases, KINDS, monthIndex, type ChangelogRelease, type ChangelogResponse, type ReleaseKind } from "./_data";
import styles from "./changelog.module.css";

const kindClass = { 更新: styles.update, 优化: styles.improve, 公告: styles.notice, 下线: styles.retired };
function Inline({ text }: { text: string }) { return <>{text.split(/\*\*(.+?)\*\*/g).map((part, i) => i % 2 ? <b key={i}>{part}</b> : part)}</>; }
function ReleaseBody({ lines }: { lines: string[] }) {
  const blocks: (string | string[])[] = [];
  for (const line of lines) {
    const last = blocks.at(-1);
    if (!line.startsWith("- ")) blocks.push(line);
    else if (Array.isArray(last)) last.push(line.slice(2));
    else blocks.push([line.slice(2)]);
  }
  return <div className={styles.body}>{blocks.map((block, i) => Array.isArray(block) ? <ul key={i}>{block.map((text, j) => <li key={j}><Inline text={text} /></li>)}</ul> : <p key={i}><Inline text={block} /></p>)}</div>;
}
function Day({ date, releases }: { date: string; releases: ChangelogRelease[] }) {
  const heading = dateHeading(date);
  return <section id={`d-${date}`} className={styles.day} data-card-key={`d-${date}`}>
    <h2 className={styles.date}><time dateTime={date}>{heading.label}</time><span>{heading.weekday}</span></h2>
    <ol className={styles.releases}>{releases.map(release => <li key={`${release.time}-${release.title}`} className={styles.release} data-urgent={release.urgent || undefined}>
      <div className={styles.stamp}><time dateTime={`${date}T${release.time}+08:00`}>{release.time}</time><span className={styles.kind}><i className={kindClass[release.kind]} aria-hidden="true" />{release.kind}</span></div>
      <article className={styles.note}>{release.urgent && <span className={styles.urgent}>重要</span>}<h3>{release.title}</h3><ReleaseBody lines={release.body} /></article>
    </li>)}</ol>
  </section>;
}
export function Changelog({ data }: { data: ChangelogResponse }) {
  const { mock, href, restore, active, routeKey } = useMainShell();
  const { store } = useSiteState(mock);
  const [kind, setKind] = useState<ReleaseKind | null>(null);
  const [initialized, setInitialized] = useState(false);
  useLayoutEffect(() => {
    const saved = restore ? readSessionSnapshot<{ kind: ReleaseKind | null }>("changelog:filter", mock) : null;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- restore matching rows before shell scroll restoration
    setKind(saved && KINDS.includes(saved.kind as ReleaseKind) ? saved.kind : null);
    setInitialized(true);
  }, [mock, restore, routeKey]);
  useEffect(() => { if (active && initialized) store.markSeen(data.latestVersion); }, [active, initialized, data.latestVersion, store]);
  const groups = groupReleases(data.releases, kind), months = monthIndex(groups);
  const changeKind = (next: ReleaseKind | null) => {
    setKind(next); saveSessionSnapshot("changelog:filter", { kind: next }, mock);
    history.replaceState(history.state, "", `${location.pathname}${location.search}`);
    document.querySelector<HTMLElement>("[data-p0-scroller]")?.scrollTo({ top: 0 });
  };
  const jump = (event: MouseEvent<HTMLAnchorElement>, first: string) => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    history.replaceState(history.state, "", `${location.pathname}${location.search}#d-${first}`);
    document.getElementById(`d-${first}`)?.scrollIntoView({ block: "start", behavior: "auto" });
  };
  const typeControls = <div className={styles.types}>{[null, ...KINDS].map(value => <button key={value ?? "all"} type="button" aria-pressed={kind === value} onClick={() => changeKind(value)}><i className={value ? kindClass[value] : styles.all} aria-hidden="true" /><span>{value ?? "全部"}</span><small>{value ? data.releases.filter(release => release.kind === value).length : data.releases.length}</small></button>)}</div>;
  const monthControls = <nav aria-label="按月份" className={styles.months}>{months.map(month => <a key={month.month} href={`#d-${month.first}`} onClick={event => jump(event, month.first)}><span>{month.month.slice(0, 4)} 年 {Number(month.month.slice(5))} 月</span><small>{month.count} 条</small></a>)}{!months.length && <p className={styles.muted}>暂无对应月份</p>}</nav>;
  const contact = <ReadingAsideCard title="有想法或遇到问题"><p>想要的功能、用着不顺的地方，都可以在反馈页告诉我们。</p><Link href={href("/feedback?from=%2Fchangelog")} className={styles.feedback}>去反馈 <span aria-hidden="true">›</span></Link></ReadingAsideCard>;
  return <ReadingLayout className={styles.page} aside={<><ReadingAsideCard title="按类型看" className={styles.desktop}>{typeControls}</ReadingAsideCard><ReadingAsideCard title="按月份看" className={styles.desktop}>{monthControls}</ReadingAsideCard>{contact}</>}>
    <RouteReady ready={initialized} />
    <header className={styles.header}><h1>更新日志</h1><p>新功能、调整、下线，都写在这里。</p></header>
    <div className={styles.mobileControls}><details open><summary>按类型看</summary>{typeControls}</details><details><summary>按月份看</summary>{monthControls}</details></div>
    <div className={styles.days} aria-live="polite">{[...groups].map(([date, releases]) => <Day key={date} date={date} releases={releases} />)}{!groups.size && <p className={styles.empty}>暂时没有“{kind}”记录。<button type="button" onClick={() => changeKind(null)}>查看全部更新</button></p>}</div>
    <p className={styles.footnote}>按开发记录整理，时间为北京时间。历史日期不代表正式上线时间。</p>
  </ReadingLayout>;
}
