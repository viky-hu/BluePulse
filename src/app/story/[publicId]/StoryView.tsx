"use client";
// AIHOT routes/story.tsx (MIT), adapted to Pulse's shared p0 shell.
// Copyright (c) 2026 数字生命卡兹克.
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { IntentLink } from "../../_components/feed/IntentLink";
import { IconArrowLeft } from "../../_components/feed/icons";
import { PillTabs } from "../../_components/feed/PillTabs";
import { RouteReady, useMainShell } from "../../_components/home/MainShell";
import { readSessionSnapshot, saveSessionSnapshot } from "../../_lib/session-restore";
import { monthDayTime } from "../../hot/_data";
import { HeatChart } from "./HeatChart";
import type { StoryDetail, StoryReport } from "./story-data";
import styles from "./story.module.css";

type Filter = "all" | "official" | "selected";
type Order = "desc" | "asc";
type Section = "overview" | "reports" | "heat";
const statusNames = { active: "持续更新", watching: "观察中", settled: "历史事件" };
const timeFormat = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const dayFormat = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", year: "numeric", month: "long", day: "numeric" });
const filterNames: Record<Filter, string> = { all: "全部报道", official: "官方一手", selected: "精选报道" };
const include = (row: StoryReport, filter: Filter) => filter === "all" || (filter === "official" ? row.source.firstParty : row.selected);

function Panel({ id, title, side, children }: { id?: Section; title: string; side?: ReactNode; children: ReactNode }) {
  return <section id={id ? `event-${id}` : undefined} className={styles.panel}>
    <header className={styles.panelHeader}><h2>{title}</h2>{side}</header>{children}
  </section>;
}

function TimelineRow({ report }: { report: StoryReport }) {
  const [open, setOpen] = useState(false);
  const [clamped, setClamped] = useState(false);
  const summary = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (!summary.current || open) return;
    const node = summary.current;
    const observer = new ResizeObserver(() => setClamped(node.scrollHeight > node.clientHeight + 1));
    observer.observe(node);
    return () => observer.disconnect();
  }, [open]);
  return <li className={styles.report}>
    <time dateTime={report.publishedAt}>{timeFormat.format(new Date(report.publishedAt))}</time>
    <div>
      <div className={styles.meta}>{report.source.name} {report.selected && <span className={styles.badge}>精选</span>}</div>
      <IntentLink className={styles.reportTitle} href={`/articles/${report.id}`}>{report.title}</IntentLink>
      {report.summary && <p ref={summary} className={styles.reportSummary} data-expanded={open}>{report.summary}</p>}
      {(clamped || open) && <button type="button" className={styles.quietButton} aria-expanded={open}
        onClick={() => setOpen(!open)}>{open ? "收起摘要" : "展开摘要"}</button>}
    </div>
  </li>;
}

function reportDays(timeline: StoryReport[], filter: Filter, order: Order) {
  const reports = timeline.filter(row => include(row, filter));
  if (order === "asc") reports.reverse();
  const days = new Map<string, StoryReport[]>();
  for (const row of reports) {
    const day = dayFormat.format(new Date(row.publishedAt));
    const existing = days.get(day);
    if (existing) existing.push(row);
    else days.set(day, [row]);
  }
  return days;
}

export function StoryView({ story }: { story: StoryDetail }) {
  const shell = useMainShell();
  const savedKey = `story-view:${story.publicId}`;
  const [view, setView] = useState<{ filter: Filter; order: Order }>({ filter: "all", order: "desc" });
  const [active, setActive] = useState<Section>("overview");
  const rail = useRef<HTMLElement>(null);
  const observed = story.status !== "settled" || story.heat.length > 0 || story.whyHot.participants48h > 0 || story.whyHot.rank !== null;
  useEffect(() => {
    if (!shell.restore) return;
    const saved = readSessionSnapshot<typeof view>(savedKey);
    if (saved && ["all", "official", "selected"].includes(saved.filter) && ["asc", "desc"].includes(saved.order)) {
      // Restoration comes from the previous visit's bounded session snapshot.
      const animation = requestAnimationFrame(() => setView(saved));
      return () => cancelAnimationFrame(animation);
    }
  }, [shell.restore, savedKey]);
  useEffect(() => {
    const scroller = rail.current?.closest("[data-p0-scroller]");
    if (!scroller) return;
    const sections: Section[] = observed ? ["overview", "reports", "heat"] : ["overview", "reports"];
    const update = () => {
      const boundary = (rail.current?.getBoundingClientRect().bottom ?? 0) + 28;
      let current: Section = "overview";
      for (const section of sections) {
        if ((document.getElementById(`event-${section}`)?.getBoundingClientRect().top ?? Infinity) <= boundary) current = section;
      }
      setActive(current);
    };
    scroller.addEventListener("scroll", update, { passive: true });
    return () => scroller.removeEventListener("scroll", update);
  }, [observed]);
  const moveTo = (section: Section) => {
    setActive(section);
    const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth";
    document.getElementById(`event-${section}`)?.scrollIntoView({ behavior, block: "start" });
  };
  const changeView = (change: Partial<typeof view>) => {
    const next = { ...view, ...change };
    setView(next);
    saveSessionSnapshot(savedKey, next);
  };
  const days = useMemo(() => reportDays(story.timeline, view.filter, view.order), [story.timeline, view]);
  const developments = view.order === "asc" ? [...story.developments].reverse() : story.developments;
  const sort = (label: string) => <select className={styles.sort} value={view.order} aria-label={label}
    onChange={event => changeView({ order: event.target.value as Order })}>
    <option value="desc">最新在前</option><option value="asc">最早在前</option>
  </select>;
  const overview = story.digest || story.summary || story.excerpt?.text;
  return <div className={styles.page} data-story-page>
    <RouteReady />
    <nav className={styles.back} aria-label="位置"><IntentLink href="/hot"><IconArrowLeft size={15} /> 热点榜</IntentLink><span>事件详情</span></nav>
    <header className={styles.hero}>
      <div className={styles.meta}>热点事件 <span className={styles.badge} data-status={story.status}>{statusNames[story.status]}</span></div>
      <h1 data-page-title>{story.title}</h1>
      <div className={styles.meta}><span><b>{story.reportCount}</b> 篇报道</span><span><b>{story.sourceCount}</b> 个报道来源</span><time dateTime={story.latestAt}>{monthDayTime(story.latestAt)} 更新</time></div>
    </header>
    <nav className={styles.sticky} ref={rail} aria-label="事件内容导航">
      <PillTabs size="sm" label="事件内容导航" active={active} onSelect={key => moveTo(key as Section)} items={[
        { key: "overview", label: "事件概览" },
        { key: "reports", label: `报道时间线 ${story.reportCount}` },
        ...(observed ? [{ key: "heat", label: "热度走势" }] : []),
      ]} />
    </nav>
    <div className={styles.columns}>
      <div className={styles.main}>
        <Panel id="overview" title="先了解这件事" side={overview && <span className={styles.meta}>{story.digest ? "AI 综述" : story.summary ? "事实说明" : "报道摘要"}</span>}>
          <p className={styles.overview}>{overview || "还没有综述，先看下面的报道时间线。"}</p>
          {!story.digest && !story.summary && story.excerpt && <p className={styles.meta}>摘自 {story.excerpt.sourceName}</p>}
          {story.latest && <div className={styles.latest}>
            <p className={styles.meta}><strong>最新进展</strong> <time dateTime={story.latestAt}>{monthDayTime(story.latestAt)}</time></p>
            {story.latestReport ? <IntentLink href={`/articles/${story.latestReport.id}`}>{story.latest}</IntentLink> : <p>{story.latest}</p>}
          </div>}
        </Panel>
        {developments.length > 1 && <Panel title={`事件进展 · ${developments.length}`} side={sort("事件进展排序")}>
          <ol className={styles.developments}>{developments.map(item => <li key={item.factId}>
            <p className={styles.meta}>{monthDayTime(item.firstReportAt)} · {item.reportCount} 篇报道</p>
            <IntentLink className={styles.reportTitle} href={`/articles/${item.representative.id}`}>{item.title}</IntentLink>
            <p className={styles.meta}>{item.representative.source.name} · {item.representative.title}</p>
          </li>)}</ol>
        </Panel>}
        <Panel id="reports" title="报道时间线" side={sort("报道时间线排序")}>
          <PillTabs size="xs" label="报道筛选" active={view.filter} onSelect={key => changeView({ filter: key as Filter })}
            items={(Object.entries(filterNames) as Array<[Filter, string]>).map(([key, label]) => ({
              key, label: `${label} ${story.timeline.filter(row => include(row, key)).length}`,
            }))} />
          {days.size === 0 && <p className={styles.empty}>这个筛选下没有报道。</p>}
          {[...days].map(([day, rows]) => <section key={day} className={styles.day}><h3>{day}</h3>
            <ol>{rows.map(report => <TimelineRow key={report.id} report={report} />)}</ol>
          </section>)}
          {story.reportCount > story.timeline.length && <p className={styles.meta}>显示最近 {story.timeline.length} 篇，共 {story.reportCount} 篇报道。</p>}
        </Panel>
        {observed && <Panel id="heat" title="本事件热度走势"><HeatChart points={story.heat} /></Panel>}
        {story.related.length > 0 && <Panel title="关联事件"><ul className={styles.links}>{story.related.map(item =>
          <li key={item.publicId}><span className={styles.meta}>{item.relation === "storyline" ? "同一故事线" : "相关事件"}</span><IntentLink href={`/story/${item.publicId}`}>{item.title}</IntentLink></li>)}</ul></Panel>}
      </div>
      <aside className={styles.aside}>
        {observed && <Panel title="为什么热">
          <p>过去 48 小时，已观察到 <b>{story.whyHot.participants48h}</b> 个独立主体参与讨论或报道，最近 6 小时新增 <b>{story.whyHot.newParticipants6h}</b> 个。</p>
          {!story.whyHot.observationComplete && <p className={styles.meta}>部分信源观测不完整，以上仅为已观察到的参与。</p>}
          <p className={styles.meta}>{story.whyHot.recentReports24h} 篇近期报道 {story.whyHot.rank && <IntentLink href="/hot">· 热点榜第 {story.whyHot.rank} 名</IntentLink>}</p>
        </Panel>}
        {story.officialReports.length > 0 && <Panel title="官方一手"><ul className={styles.links}>{story.officialReports.slice(0, 5).map(row =>
          <li key={row.id}><span className={styles.meta}>{row.source.name}</span><IntentLink href={`/articles/${row.id}`}>{row.title}</IntentLink></li>)}</ul>
          <button className={styles.quietButton} type="button" onClick={() => { changeView({ filter: "official" }); moveTo("reports"); }}>在时间线筛选全部官方报道</button>
        </Panel>}
        {story.topics.length > 0 && <Panel title="相关分类"><ul className={styles.topics}>{story.topics.map(topic => <li key={topic.slug}><IntentLink href={`/all?topic=${encodeURIComponent(topic.slug)}`}>{topic.name}</IntentLink></li>)}</ul></Panel>}
        <Panel title="事件记录"><dl className={styles.dates}>
          <div><dt>最早报道</dt><dd>{monthDayTime(story.firstReportAt)}</dd></div>
          <div><dt>最新报道</dt><dd>{monthDayTime(story.latestAt)}</dd></div>
        </dl></Panel>
      </aside>
    </div>
  </div>;
}
