"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { IntentLink as Link } from "./IntentLink";
import { RouteReady, useMainShell } from "../_components/home/MainShell";
import { buildHomeHref, canonicalHref, parseHomeRoute } from "../_components/home/home-routes";
import { invalidateSessionSnapshot, readSessionSnapshot, saveSessionSnapshot } from "../_lib/session-restore";
import { emptyAllFeed, getCachedAllFeed, invalidateAllFeed, loadAllFeed, validAllSnapshot, type AllFeedData } from "./_cache";
import { selectAllFilter } from "./_data";
import { AllToolbar } from "./AllToolbar";
import { DayList } from "./DayList";
import { FeedIcon } from "./FeedIcons";
import styles from "../_components/feed/feed.module.css";

// AIHOT components/ui/Page.tsx: EmptyState, with the original optional action slot.
function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return <div className={styles.state}><div className={styles.stateTitle}>{title}</div>{children && <p>{children}</p>}{action && <div className={styles.stateAction}>{action}</div>}</div>;
}
export function AllFeed() {
  const shell = useMainShell();
  const route = parseHomeRoute("/all", new URLSearchParams(shell.routeKey.split("?")[1]));
  const [loaded, setLoaded] = useState(() => ({ activation: shell.activation, feed: getCachedAllFeed(shell.routeKey, shell.mock) ?? emptyAllFeed(shell.routeKey), previous: null as AllFeedData | null }));
  const [retry, setRetry] = useState(0);
  const lastRequest = useRef({ key: shell.routeKey, revision: shell.refreshRevision, retry: 0 });
  useEffect(() => {
    if (shell.activation.key !== shell.routeKey) return;
    let active = true;
    const key = shell.routeKey;
    const before = lastRequest.current;
    const force = before.key === key && (before.revision !== shell.refreshRevision || before.retry !== retry);
    lastRequest.current = { key, revision: shell.refreshRevision, retry };
    const update = (feed: AllFeedData) => { if (active) setLoaded(previous => ({ activation: shell.activation, feed, previous: feed.status === "loading" ? previous.feed.status === "ready" ? previous.feed : previous.previous : null })); };
    const snapshot = !force && shell.restore ? readSessionSnapshot<AllFeedData>(`all-feed:${key}`, shell.mock) : null;
    const cached = validAllSnapshot(snapshot, key) ? snapshot : !force ? getCachedAllFeed(key, shell.mock) : null;
    queueMicrotask(() => {
      if (!active) return;
      if (cached) { update(cached); return; }
      update(emptyAllFeed(key));
      void loadAllFeed(key, shell.mock, force).then(feed => {
        if (!active) return;
        update(feed);
        if (validAllSnapshot(feed, key)) saveSessionSnapshot(`all-feed:${key}`, feed, shell.mock);
        else invalidateSessionSnapshot(`all-feed:${key}`, shell.mock);
      });
    });
    return () => { active = false; };
  }, [shell.activation, shell.routeKey, shell.mock, shell.restore, shell.refreshRevision, retry]);
  const feed = loaded.feed.key === shell.routeKey && (loaded.activation === shell.activation || shell.activation.key !== shell.routeKey)
    ? loaded.feed : getCachedAllFeed(shell.routeKey, shell.mock) ?? emptyAllFeed(shell.routeKey);
  const { filters } = route;
  const firstHref = buildHomeHref("/all", filters, { mock: shell.mock });
  const nextHref = buildHomeHref("/all", filters, { cursor: feed.next, mock: shell.mock });
  const previous = readSessionSnapshot<string>(`all-previous:${shell.routeKey}`, shell.mock);
  const previousHref = typeof previous === "string" && (previous === "/all" || previous.startsWith("/all?")) ? previous : null;
  const retryFeed = () => { invalidateAllFeed(shell.routeKey, shell.mock); setRetry(value => value + 1); };
  const visible = feed.status === "loading" ? loaded.previous ?? (loaded.feed.status === "ready" ? loaded.feed : feed) : feed;
  return <div className={styles.page} data-all-status={feed.status}>
    <RouteReady ready={feed.status !== "loading"} />
    <header className={styles.header}><h1>{filters.q ? `搜索“${filters.q}”` : "全部动态"}{shell.mock ? "（演示）" : ""}</h1></header>
    <AllToolbar filters={filters} />
    <div className={styles.results} data-feed-busy={feed.status === "loading"}>
      {feed.status === "error" && <div className={styles.emptyCard} role="alert"><EmptyState title="资讯暂时无法载入" action={route.cursor ? <Link href={firstHref}>返回第一页</Link> : <button type="button" onClick={retryFeed}>重试</button>}>{feed.error}</EmptyState></div>}
      {feed.status === "category-unavailable" && <div className={styles.emptyCard} role="status"><EmptyState title="分类暂不可用" action={<Link href={buildHomeHref("/all", selectAllFilter(filters, "all"), { mock: shell.mock })}>浏览全部动态</Link>}>这个筛选下暂时没有可用内容。</EmptyState></div>}
      {visible.status === "ready" && (visible.articles.length ? <DayList articles={visible.articles} taxonomy={visible.taxonomy} /> : <div className={styles.emptyCard} role="status"><EmptyState title="没有找到相关内容">{filters.q ? "换个说法，或者去掉筛选再试。" : "这个筛选下暂时没有内容。"}</EmptyState></div>)}
    </div>
    {feed.status === "ready" && (route.cursor || feed.next) && <nav className={styles.pagination} aria-label="分页">{route.cursor && <Link href={previousHref ?? firstHref}>{previousHref ? "上一页" : "返回第一页"}</Link>}{feed.next && <Link href={nextHref} onClick={() => saveSessionSnapshot(`all-previous:${canonicalHref(nextHref)}`, shell.routeKey, shell.mock)}>下一页<FeedIcon name="next" /></Link>}</nav>}
  </div>;
}
