"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import type { Topic } from "../../_lib/home-data";
import type { TimelineListState } from "../../_lib/feed-types";
import { readSessionSnapshot, invalidateSessionSnapshot } from "../../_lib/session-restore";
import { RouteReady, useMainShell } from "../home/MainShell";
import { parseHomeRoute, buildHomeHref } from "../home/home-routes";
import { selectAllFilter } from "../../all/_data";
import { FeedToolbar } from "../feed/FeedToolbar";
import { FeaturedTimeline } from "./Timeline";
import { HotTopics } from "./HotTopics";
import { emptyFeaturedFeed, getCachedFeaturedFeed, invalidateFeaturedFeed, loadFeaturedFeed, requestTimeline, TimelineRequestError, type FeaturedFeedData } from "./_cache";
import { appendTimeline, fromTimeline, parseTimeline, timelineFilters } from "./_data";
import styles from "../feed/feed.module.css";

type SavedList = { key: string; state: TimelineListState; taxonomy: Topic[] };
type SavedView = { batches: number; collapsed: string[] };
function validSaved(value: SavedList | null, key: string): value is SavedList {
  if (!value || value.key !== key || !value.state || value.state.expiresAt <= Date.now() || !Number.isInteger(value.state.batches) || value.state.batches < 1 || !Array.isArray(value.state.collapsed) || !Array.isArray(value.taxonomy)) return false;
  try { parseTimeline(value.state, timelineFilters(key)); return true; } catch { return false; }
}
export function FeaturedFeed() {
  const shell = useMainShell();
  const route = parseHomeRoute("/", new URLSearchParams(shell.routeKey.split("?")[1]));
  const [loaded, setLoaded] = useState(() => ({ feed: emptyFeaturedFeed(shell.routeKey), list: null as TimelineListState | null, generation: 0 }));
  const [previous, setPrevious] = useState<typeof loaded | null>(null), [retry, setRetry] = useState(0);
  const lastReady = useRef<typeof loaded | null>(null);
  useEffect(() => { if (loaded.feed.status === "ready") lastReady.current = loaded; }, [loaded]);
  const lastRequest = useRef({ key: shell.routeKey, revision: shell.refreshRevision, retry: 0 });
  useEffect(() => {
    if (shell.activation.key !== shell.routeKey) return;
    const key = shell.routeKey, before = lastRequest.current;
    const force = before.key === key && (before.revision !== shell.refreshRevision || before.retry !== retry);
    lastRequest.current = { key, revision: shell.refreshRevision, retry };
    const controller = new AbortController();
    const current = () => !controller.signal.aborted;
    queueMicrotask(() => {
      if (!current()) return;
      setPrevious(lastReady.current);
      setLoaded(old => ({ ...old, feed: emptyFeaturedFeed(key) }));
      void (async () => {
        const saved = !force && shell.restore ? readSessionSnapshot<SavedList>(`featured-list:${key}`, shell.mock) : null;
        const view = !force && shell.restore ? readSessionSnapshot<SavedView>(`featured-view:${key}`, shell.mock) : null;
        let feed: FeaturedFeedData, list: TimelineListState | null;
        if (validSaved(saved, key)) {
          list = saved.state;
          feed = { key, status: "ready", expiresAt: list.expiresAt, timeline: list, taxonomy: saved.taxonomy, error: null };
        } else {
          feed = (!force ? getCachedFeaturedFeed(key, shell.mock) : null) ?? await loadFeaturedFeed(key, shell.mock, force);
          if (!current()) return;
          list = feed.timeline ? fromTimeline(feed.timeline) : null;
          // Expired data is read again before restoring a deep anchor. View flags have their own 30m lifetime.
          if (list && view && Number.isInteger(view.batches) && view.batches > 0) {
            try {
              let cursorReset = false;
              while (list.nextCursor && list.batches < view.batches) {
                const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(12_000)]);
                try { list = appendTimeline(list, await requestTimeline(list.filters, list.nextCursor, shell.mock, signal)); }
                catch (error) {
                  if (!(error instanceof TimelineRequestError) || error.status !== 400) throw error;
                  const head = await requestTimeline(list.filters, null, shell.mock, signal);
                  list = fromTimeline({ ...head, expiresAt: Math.min(head.expiresAt, feed.expiresAt) });
                  cursorReset = true;
                  break;
                }
              }
              if (!cursorReset && Array.isArray(view.collapsed)) list.collapsed = view.collapsed.filter(day => typeof day === "string");
            } catch (error) {
              if (!current()) return;
              feed = { ...feed, status: "error", error: error instanceof Error ? error.message : "精选暂时无法载入。" };
            }
          }
        }
        if (!current()) return;
        if (!list || list.expiresAt <= Date.now()) invalidateSessionSnapshot(`featured-list:${key}`, shell.mock);
        setLoaded(old => ({ feed, list, generation: old.generation + 1 })); setPrevious(null);
      })();
    });
    return () => controller.abort();
  }, [shell.activation, shell.routeKey, shell.restore, shell.mock, shell.refreshRevision, retry]);
  const feed = loaded.feed.key === shell.routeKey ? loaded.feed : emptyFeaturedFeed(shell.routeKey);
  const visible = feed.status === "loading" ? previous ?? (loaded.feed.status === "ready" ? loaded : null) : loaded;
  const retryFeed = () => { invalidateFeaturedFeed(shell.routeKey, shell.mock); setRetry(value => value + 1); };
  const state = (title: string, text: string, action?: React.ReactNode) => <div className={styles.emptyCard}><div className={styles.state}><div className={styles.stateTitle}>{title}</div><p>{text}</p>{action && <div className={styles.stateAction}>{action}</div>}</div></div>;
  const filters = { ...route.filters, period: "all" as const };
  return <div className={styles.page} data-featured-status={feed.status}>
    <RouteReady ready={feed.status !== "loading"} />
    <header className={styles.header}><h1>精选{shell.mock ? "（演示）" : ""}</h1></header>
    <FeedToolbar filters={filters} base="/" />
    <div className={styles.results} data-feed-busy={feed.status === "loading"}>
      {(feed.status === "error" || feed.status === "unavailable") && <div role="alert">{state(feed.status === "unavailable" ? "精选服务尚未接入" : "精选暂时无法载入", feed.status === "unavailable" ? "精选时间线服务尚未接入。" : feed.error ?? "请稍后重试。", <button type="button" onClick={retryFeed}>重试</button>)}</div>}
      {feed.status === "category-unavailable" && <div role="status">{state("分类暂不可用", "这个筛选下暂时没有可用内容。", <Link href={buildHomeHref("/", selectAllFilter(filters, "all"), { mock: shell.mock })}>浏览全部精选</Link>)}</div>}
      {visible?.feed.status === "ready" && visible.list && <>
        {!visible.list.filters.region && !visible.list.filters.topic && visible.list.hot && <HotTopics entries={visible.list.hot} />}
        {!visible.list.cards.length ? state("这个筛选下还没有精选内容", "换个类别看看，或者去全部动态里找找。") : <FeaturedTimeline key={`${visible.feed.key}:${visible.generation}`} scopeKey={visible.feed.key} start={visible.list} taxonomy={visible.feed.taxonomy} active={feed.status === "ready" && shell.active} />}
      </>}
    </div>
  </div>;
}
