"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import type { ArticleCard } from "../../_lib/home-data";
import { invalidateSessionSnapshot, readSessionSnapshot, saveSessionSnapshot } from "../../_lib/session-restore";
import { RouteReady, useMainShell } from "./MainShell";
import { ArticleActions } from "./ArticleActions";
import { buildHomeHref, canonicalHref, parseHomeRoute, type HomeFilters } from "./home-routes";
import { emptyHomeFeed, getCachedHomeFeed, getCachedHomeSources, invalidateHomeFeed, loadHomeFeed, loadHomeSources, type HomeFeed } from "./home-feed-cache";
import { ARTICLE_TOPIC_LABELS } from "./article-topic-labels";
import styles from "./home.module.css";

export function displayDate(value?: string | null) {
  if (!value || !Number.isFinite(Date.parse(value))) return "日期待核";
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value));
}
function validCache(value: HomeFeed | null, key: string): value is HomeFeed {
  if (!value || !Number.isFinite(value.expiresAt) || value.expiresAt <= Date.now()) return false;
  return !!value && value.key === key && value.status === "ready" && [value.articles, value.featured, value.collected].every(rows => Array.isArray(rows) && rows.every(row => row && typeof row.id === "string" && typeof row.title === "string" && typeof row.source?.name === "string"));
}

export function ArticleRows({ articles, kind = "article" }: { articles: ArticleCard[]; kind?: "article" | "featured" | "collected" }) {
  const shell = useMainShell();
  return <div className={styles.articleList}>
    {articles.map((article, index) => <div key={article.id} className={styles.articleEntry} data-card-key={article.id}>
      <Link href={shell.href(`/articles/${article.id}`)} className={`${styles.articleRow} ${kind === "featured" ? styles.featuredRow : ""}`}>
        <span className={styles.articleIndex}>{kind === "featured" ? `TOP ${index + 1}` : String(index + 1).padStart(2, "0")}</span>
        <span className={styles.articleRowBody}>
          <span className={styles.articleRowMeta}><time>{kind === "collected" ? `收录于 ${displayDate(article.first_seen_at)} · 原文 ${displayDate(article.published_at)}` : displayDate(article.published_at ?? article.first_seen_at)}</time><span className={styles.metaDot} />{article.source.name}</span>
          <strong>{article.title || article.source_title}</strong>
          {kind !== "article" && article.summary ? <span className={styles.articleRowSummary}>{article.summary}</span> : null}
          {kind === "featured" && article.featured_reason ? <span className={styles.articleRowSummary}>关注理由 · {article.featured_reason}</span> : null}
        </span><span className={styles.articleRowArrow} aria-hidden>↗</span>
      </Link><ArticleActions article={article} />
    </div>)}
  </div>;
}

function Filters({ filters, apply }: { filters: HomeFilters; apply: (filters: HomeFilters) => void }) {
  const shell = useMainShell();
  const [query, setQuery] = useState(filters.q), [liveSources, setSources] = useState(() => getCachedHomeSources(shell.mock) ?? []);
  const sources = liveSources;
  useEffect(() => {
    let active = true;
    loadHomeSources(shell.mock).then(data => { if (active) setSources(data); }).catch(() => {});
    return () => { active = false; };
  }, [shell.mock]);
  const types = [...new Set(sources.map(source => source.source_type))].sort();
  return <section className={styles.searchPanel} aria-label="资讯筛选">
    <form className={styles.searchForm} onSubmit={event => { event.preventDefault(); apply({ ...filters, q: query.trim() }); }}>
      <input value={query} maxLength={200} onChange={event => setQuery(event.target.value)} placeholder="输入关键词，例如：警务大模型" aria-label="搜索关键词" /><button type="submit">搜索资讯</button>
    </form>
    <div className={styles.filterGrid}>
      <label><span>时间范围</span><select value={filters.period} onChange={event => apply({ ...filters, period: event.target.value as HomeFilters["period"] })}><option value="24h">近 24 小时</option><option value="7d">近 7 天</option><option value="30d">近 30 天</option><option value="all">全部时间</option></select></label>
      <label><span>资讯地区</span><select value={filters.region} onChange={event => apply({ ...filters, region: event.target.value as HomeFilters["region"] })}><option value="">全部地区</option><option value="domestic">国内</option><option value="foreign">国外</option></select></label>
      <label><span>主题分类</span><select value={filters.topic} onChange={event => apply({ ...filters, topic: event.target.value })}><option value="">全部主题</option>{Object.entries(ARTICLE_TOPIC_LABELS).map(([slug, name]) => <option key={slug} value={slug}>{name}</option>)}</select></label>
      <label><span>具体来源</span><select value={filters.source} onChange={event => apply({ ...filters, source: event.target.value })}><option value="">全部来源</option>{sources.map(source => <option key={source.id} value={source.id}>{source.name}</option>)}</select></label>
      <label><span>来源类型</span><select value={filters.sourceType} onChange={event => apply({ ...filters, sourceType: event.target.value })}><option value="">全部来源</option>{types.map(type => <option key={type} value={type}>{type}</option>)}</select></label>
      <label><span>排列方式</span><select value={filters.sort} onChange={event => apply({ ...filters, sort: event.target.value as HomeFilters["sort"] })}><option value="recent">最新发布</option><option value="importance">关注度优先</option></select></label>
    </div><div className={styles.searchFootnote}><button type="button" onClick={() => apply(parseHomeRoute(shell.pathname, new URLSearchParams()).filters)}>重置筛选</button></div>
  </section>;
}

/** Content owns data; the shared shell owns geometry, menu, navigation and scrolling. */
export function HomeDashboard() {
  const shell = useMainShell();
  const route = parseHomeRoute(shell.pathname, new URLSearchParams(shell.routeKey.split("?")[1]));
  const [loaded, setLoaded] = useState(() => ({ activation: shell.activation, feed: getCachedHomeFeed(shell.routeKey, shell.mock) ?? emptyHomeFeed(shell.routeKey) }));
  const feed = loaded.feed;
  const [retry, setRetry] = useState(0);
  const filterKey = JSON.stringify(route.filters);
  const lastRequest = useRef({ key: shell.routeKey, refreshRevision: shell.refreshRevision, retry: 0 });
  useEffect(() => {
    // The next activation is announced before Next replaces the outgoing page.
    if (shell.activation.key !== shell.routeKey) return;
    let active = true;
    const setFeed = (value: HomeFeed) => setLoaded({ activation: shell.activation, feed: value });
    const key = shell.routeKey;
    const previousRequest = lastRequest.current;
    const force = previousRequest.key === key
      && (previousRequest.refreshRevision !== shell.refreshRevision || previousRequest.retry !== retry);
    lastRequest.current = { key, refreshRevision: shell.refreshRevision, retry };
    const cached = !force && shell.restore ? readSessionSnapshot<HomeFeed>(`feed:${key}`, shell.mock) : null;
    if (validCache(cached, key)) {
      queueMicrotask(() => { if (active) setFeed(cached); });
      return () => { active = false; };
    }
    const cachedPage = !force ? getCachedHomeFeed(key, shell.mock) : null;
    if (cachedPage) {
      queueMicrotask(() => { if (active) setFeed(cachedPage); });
      return () => { active = false; };
    }
    queueMicrotask(() => {
      if (!active) return;
      setFeed(emptyHomeFeed(key));
      const filters = JSON.parse(filterKey) as HomeFilters;
      void loadHomeFeed({ key, pathname: shell.pathname, filters, cursor: route.cursor, mock: shell.mock }, { force }).then(next => {
        if (!active) return;
        setFeed(next);
        if (next.status === "ready" && next.expiresAt > Date.now()) saveSessionSnapshot(`feed:${key}`, next, shell.mock);
        else invalidateSessionSnapshot(`feed:${key}`, shell.mock);
      });
    });
    return () => { active = false; };
  }, [shell.activation, shell.routeKey, shell.pathname, shell.mock, shell.restore, shell.refreshRevision, filterKey, route.cursor, retry]);
  const currentPage = getCachedHomeFeed(shell.routeKey, shell.mock);
  const current = feed.key === shell.routeKey && (loaded.activation === shell.activation || shell.activation.key !== shell.routeKey)
    ? feed
    : currentPage ?? emptyHomeFeed(shell.routeKey);
  const apply = (filters: HomeFilters) => shell.navigate(buildHomeHref(shell.pathname, filters, { mock: shell.mock }));
  const nextHref = buildHomeHref(shell.pathname, route.filters, { cursor: current.next, mock: shell.mock });
  const previous = readSessionSnapshot<string>(`previous:${shell.routeKey}`, shell.mock);
  const header = route.kind === "home" ? "近期资讯" : route.kind === "all" ? "全部动态" : "搜索结果";
  if (!route.valid) return <><RouteReady /><p role="alert">没有这个分类。<Link href={shell.href("/")}>返回精选</Link></p></>;
  return <div className={styles.content}>
    <RouteReady ready={current.status !== "loading"} />
    {route.kind === "all" ? <header className={styles.pageHeader}><h1>全部动态</h1><p>浏览国内外警务科技资讯，按时间、主题与来源筛选。</p></header> : null}
    {route.kind === "search" || route.kind === "all" ? <Filters key={filterKey} filters={route.filters} apply={apply} /> : null}
    {route.kind === "home" && current.featured.length ? <section className={styles.featuredSection} aria-label="精选资讯"><ArticleRows articles={current.featured} kind="featured" /></section> : null}
    {current.collected.length ? <section className={styles.collectedSection}><div className={styles.feedTools}><span className={styles.feedLabel}>最近收录</span><Link href={shell.href("/articles?period=all")} className={styles.inlineButton}>查看全部</Link></div><p className={styles.collectedNote}>可能包含往期文章；请以原文日期为准，不代表本期精选。</p><ArticleRows articles={current.collected} kind="collected" /></section> : null}
    <section className={styles.feedSection} aria-label={header}>
      <div className={styles.feedTools}><span className={styles.feedLabel}>{header}</span>{route.kind !== "search" && route.kind !== "all" ? <div className={styles.periodSwitch}>{(["24h", "7d", "30d", "all"] as const).map(period => <button key={period} type="button" aria-pressed={route.filters.period === period} className={route.filters.period === period ? styles.periodActive : ""} onClick={() => apply({ ...route.filters, period })}>{period === "all" ? "全部" : period === "24h" ? "24 小时" : period === "7d" ? "7 天" : "30 天"}</button>)}</div> : null}</div>
      {current.status === "error" ? <div className={`${styles.statePanel} ${styles.stateError}`} role="alert"><strong>资讯暂时无法载入</strong><p>{current.error}</p><button type="button" className={styles.inlineButton} onClick={() => { invalidateHomeFeed(shell.routeKey, shell.mock); setRetry(value => value + 1); }}>重试</button></div> : null}
      {current.articles.length ? <ArticleRows articles={current.articles} /> : current.status === "ready" ? <div className={styles.statePanel} role="status">{route.kind === "home" ? "本期暂无已审核资讯" : "没有匹配的资讯"}</div> : null}
      {current.status !== "loading" && (current.articles.length > 0 || route.cursor) ? <div className={styles.pagination}><span>{current.articles.length} 条</span><div>{route.cursor ? <Link className={styles.inlineButton} href={typeof previous === "string" && previous.startsWith("/") ? previous : buildHomeHref(shell.pathname, route.filters, { mock: shell.mock })}>上一页</Link> : null}{current.next ? <Link className={styles.inlineButton} href={nextHref} onClick={() => saveSessionSnapshot(`previous:${canonicalHref(nextHref)}`, shell.routeKey, shell.mock)}>下一页 →</Link> : null}</div></div> : null}
    </section>
  </div>;
}
