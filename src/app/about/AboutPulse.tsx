"use client";

// Page composition adapted from AIHOT routes/about.tsx (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { RouteReady, useMainShell } from "../_components/home/MainShell";
import { ABOUT } from "./_config";
import { SiteStatsError, type SiteStats } from "./_data";
import { getCachedAboutStats, loadAboutStats } from "./_cache";
import { MOCK_SITE_STATS } from "./_mock";
import { KIND, type RiverSource } from "./_river-drawing";
import { SignalRiver } from "./SignalRiver";
import styles from "./about.module.css";

const NO_SOURCES: RiverSource[] = [];
type StatsState = { activation: object; key: string; stats: SiteStats | null; status: "ready" | "missing" | "error" };

function Figure({ value, unit }: { value: number; unit: string }) {
  const figure = value >= 10000 ? (value / 10000).toFixed(1).replace(/\.0$/, "") : value.toLocaleString("en-US");
  return <div className={styles.figure} data-about-figure>
    <span>{figure}</span><span className={styles.unit}>{value >= 10000 ? "万" : ""}{unit}</span>
  </div>;
}

function Latest({ item, placement }: { item: SiteStats["latest"][number] | undefined; placement: "beside" | "below" }) {
  const { href } = useMainShell();
  if (!item) return null;
  return <Link href={href(`/articles/${item.id}`)} className={`${styles.latest} ${placement === "beside" ? styles.latestBeside : styles.latestBelow}`} data-about-latest={placement}>
    <span className={styles.latestKicker}>最近精选</span>
    <span key={item.id} className={styles.latestText}>
      <strong>{item.title}</strong><span>{item.source}</span>
    </span>
  </Link>;
}

function Maker() {
  const { href } = useMainShell();
  return <section className={styles.maker} aria-labelledby="about-maker">
    <div>
      <p className={styles.kicker}>做这个站的人</p>
      <h2 id="about-maker" className={styles.greeting}>
        <Image src="/logo.svg" alt="青朗先锋实验小组标志" width={48} height={56} className={styles.avatar} unoptimized />
        <span>嗨，这里是<br /><span>青朗先锋实验小组</span></span>
      </h2>
      <div className={styles.prose}>
        <p>前端内容感谢<a href="https://github.com/KKKKhazix/AIHOT" target="_blank" rel="noreferrer">数字生命卡兹克</a>提供大量开源架构～</p>
        <p>我们希望把散落在不同地区、不同语言里的公开警务科技资讯，整理成更容易阅读、查找和回溯的资料。既关注技术的新进展，也关心它在实际工作中怎样使用。</p>
        <p>网站会持续完善资讯采集与中文整理，逐步补上事件追踪和日报。每条信息都尽量留住出处；有疑问时，可以回到原始材料核对。</p>
        <p className={styles.muted}>它一直在改，改了什么都写在<Link href={href("/changelog")}>更新日志</Link>里；有想法、遇到问题，可以通过右侧或下方二维码联系我们，也可以先看看<Link href={href("/feedback")}>反馈页</Link>的当前状态。</p>
      </div>
    </div>
    <div className={styles.contacts} id="pulse-contact">
      <h3>如果觉得有点用，欢迎加入</h3>
      {ABOUT.contacts.map(contact => <figure key={contact.kind} className={styles.qrCard}>
        <a href={contact.src} target="_blank" rel="noreferrer" aria-label={`查看完整${contact.kind}二维码`}>
          <Image src={contact.src} alt={`${contact.title}的${contact.kind}二维码`} width={contact.width} height={contact.height} className={contact.kind === "微信" ? styles.wechatQr : undefined} unoptimized />
        </a>
        <figcaption><div className={styles.contactKind}>{contact.kind}</div><h4>{contact.title}</h4><p>{contact.note}</p></figcaption>
      </figure>)}
    </div>
  </section>;
}

export function AboutPulse() {
  const { mock, href, refreshRevision, routeKey, activation } = useMainShell();
  const requestKey = `${routeKey}:${refreshRevision}`;
  const [result, setResult] = useState<StatsState | null>(() => {
    const cached = getCachedAboutStats(routeKey, mock);
    return cached ? { activation, key: `${requestKey}:0`, stats: cached.stats, status: "ready" } : null;
  });
  const [retry, setRetry] = useState(0);
  const [focus, setFocus] = useState<number | null>(null);
  const [at, setAt] = useState(0);
  const shown = useRef(0);
  const lastRequest = useRef({ routeKey, refreshRevision, retry: 0 });
  const current = result && (result.activation === activation || activation.key !== routeKey) && result.key === `${requestKey}:${retry}` ? result : null;
  const cached = result?.activation !== activation ? getCachedAboutStats(routeKey, mock) : null;
  const stats = mock ? MOCK_SITE_STATS : current ? current.stats : cached?.stats ?? null;
  const status = mock ? "mock" : current?.status ?? (cached ? "ready" : "loading");
  const latest = stats?.latest ?? [];

  useEffect(() => {
    if (mock || activation.key !== routeKey) return;
    let active = true;
    const previous = lastRequest.current;
    const force = previous.routeKey === routeKey && (previous.refreshRevision !== refreshRevision || previous.retry !== retry);
    lastRequest.current = { routeKey, refreshRevision, retry };
    loadAboutStats(routeKey, mock, force).then(page => {
      if (active) setResult({ activation, key: `${requestKey}:${retry}`, stats: page.stats, status: "ready" });
    }).catch(error => {
      if (active) setResult({ activation, key: `${requestKey}:${retry}`, stats: null, status: error instanceof SiteStatsError && error.status === 404 ? "missing" : "error" });
    });
    return () => { active = false; };
  }, [activation, mock, routeKey, requestKey, refreshRevision, retry]);

  const onArrive = useCallback(() => {
    const now = Date.now();
    if (now - shown.current < 2800 || latest.length < 2) return;
    shown.current = now;
    setAt(index => (index + 1) % latest.length);
  }, [latest.length]);

  const values = [stats?.sources, stats?.items, stats?.selected, stats?.dailies];
  const kindNote = stats ? Object.entries(stats.sourceKinds).filter(([, n]) => n > 0).map(([kind, n]) => `${KIND[kind] ?? kind} ${n}`).join(" · ") : "";
  const notes = [kindNote,
    stats?.day.collected != null ? `过去 24 小时收进 ${stats.day.collected.toLocaleString("en-US")} 条` : "",
    stats?.day.selected != null ? `过去 24 小时 ${stats.day.selected} 条进了精选` : "",
    "日报及 RSS、API、MCP 订阅能力建设中",
  ];
  const item = latest.length ? latest[at % latest.length] : undefined;

  return <article className={styles.page} data-about-page>
    <RouteReady ready={status !== "loading"} />
    <header className={styles.hero}>
      <div>
        <p className={styles.kicker}>关于 Pulse</p>
        <h1 className={styles.headline}>{ABOUT.headline[0]}<br /><span>{ABOUT.headline[1]}</span></h1>
        <p className={styles.lead}>{ABOUT.lead}</p>
      </div>
      <div className={styles.actions}>
        <Link href={href("/")} className={styles.primary}>看今天的精选 <span aria-hidden="true">→</span></Link>
        <Link href={href("/daily")} className={styles.secondary}>读最新日报</Link>
      </div>
    </header>

    <section aria-labelledby="about-how" className={styles.how}>
      <h2 id="about-how" className={styles.srOnly}>Pulse 怎么工作</h2>
      <p className={status === "loading" ? styles.srOnly : styles.dataStatus} role="status" data-about-status={status}>
        {status === "mock" ? "演示数据 · 仅用于流程交互预览" : status === "loading" ? "正在读取站点统计…" : status === "missing" ? "站点统计尚未接入，以下为工作流程示意。" : status === "error" ? "站点统计暂时不可用，以下为工作流程示意。" : "站点公开统计 · 流程图为工作机制示意"}
        {status === "error" || status === "missing" ? <button type="button" onClick={() => setRetry(n => n + 1)}>重新读取</button> : null}
      </p>
      <SignalRiver sources={stats?.sampleSources ?? NO_SOURCES} focus={focus} onArrive={onArrive}>
        <Latest item={item} placement="beside" />
      </SignalRiver>
      <p className={styles.srOnly}>示意图：每条线代表一个信源；线汇成束，代表同一件事的多篇报道；经过精选闸门，只有少数几束通过，汇入日报。此图不是实时处理记录。</p>
      <Latest item={item} placement="below" />
      <ol className={styles.stages}>
        {ABOUT.steps.map((stage, i) => <li key={stage.title} tabIndex={0} data-about-stage={i} data-focused={focus === i}
          onPointerEnter={() => setFocus(i)} onPointerLeave={() => setFocus(null)} onFocus={() => setFocus(i)} onBlur={() => setFocus(null)}>
          <div className={styles.stageTitle}><span>{String(i + 1).padStart(2, "0")}</span><h3>{stage.title}</h3></div>
          {values[i] != null && <Figure value={values[i]} unit={stage.unit} />}
          <p>{stage.text}</p>
          {notes[i] && <p className={styles.stageNote}>{notes[i]}</p>}
        </li>)}
      </ol>
      <p className={styles.workflowNote}>从采集到成刊，是我们正在逐步完善的工作流程。自动归组、事件热点与日报尚在建设中；当前可从精选和全部动态开始阅读。</p>
    </section>

    <Maker />
    <aside className={styles.copyright}>Pulse 提供公开资讯的摘要与阅读索引，原文版权归各来源所有。如果你是来源方，希望更正、下架或调整展示方式，请通过网站负责人的微信联系我们。</aside>
    <footer className={styles.footer}><span>Blue Pulse · 国内外警务科技情报系统</span><span>无需注册 · 阅读记录保存在当前浏览器</span></footer>
  </article>;
}
