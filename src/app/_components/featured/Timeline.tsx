"use client";
// AIHOT features/feed/Timeline.tsx, adapted to Pulse's p0 scroller (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Topic } from "../../_lib/home-data";
import type { TimelineListState } from "../../_lib/feed-types";
import { saveSessionSnapshot, invalidateSessionSnapshot } from "../../_lib/session-restore";
import { useMainShell } from "../home/MainShell";
import { FeedItem } from "../feed/FeedItem";
import { DayHeader, TimelineSlot } from "../feed/TimelineParts";
import { Collapse } from "../feed/Presence";
import { fromTimeline, appendTimeline, groupTimeline } from "./_data";
import { requestTimeline, TimelineRequestError } from "./_cache";
import styles from "./featured.module.css";

export function FeaturedTimeline({ start, scopeKey, taxonomy, active }: { start: TimelineListState; scopeKey: string; taxonomy: Topic[]; active: boolean }) {
  const shell = useMainShell();
  const [state, setState] = useState(start), [loading, setLoading] = useState(false), [error, setError] = useState(false);
  const [freshKeys, setFreshKeys] = useState<Set<string>>(() => new Set());
  const stateRef = useRef(state), request = useRef<AbortController | null>(null), sentinel = useRef<HTMLDivElement>(null);
  useEffect(() => { stateRef.current = state; }, [state]);
  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => { if (!active) request.current?.abort(); }, [active]);
  useEffect(() => {
    saveSessionSnapshot(`featured-view:${scopeKey}`, { batches: state.batches, collapsed: state.collapsed }, shell.mock);
    if (state.expiresAt > Date.now()) saveSessionSnapshot(`featured-list:${scopeKey}`, { key: scopeKey, state, taxonomy }, shell.mock);
    else invalidateSessionSnapshot(`featured-list:${scopeKey}`, shell.mock);
  }, [state, scopeKey, taxonomy, shell.mock]);
  const loadMore = useCallback(async () => {
    const current = stateRef.current;
    if (!active || !current.nextCursor || request.current) return;
    const controller = new AbortController(); request.current = controller;
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(12_000)]);
    setLoading(true); setError(false);
    try {
      let page;
      try { page = await requestTimeline(current.filters, current.nextCursor, shell.mock, signal); }
      catch (cause) {
        if (!(cause instanceof TimelineRequestError) || cause.status !== 400) throw cause;
        const head = await requestTimeline(current.filters, null, shell.mock, signal);
        if (!signal.aborted) { const next = fromTimeline({ ...head, expiresAt: Math.min(head.expiresAt, current.expiresAt) }); stateRef.current = next; setState(next); setFreshKeys(new Set()); }
        return;
      }
      if (signal.aborted) return;
      const seen = new Set(current.cards.map(card => card.key));
      setFreshKeys(new Set(page.cards.filter(card => !seen.has(card.key)).map(card => card.key)));
      const next = appendTimeline(stateRef.current, page); stateRef.current = next; setState(next);
    } catch { if (!controller.signal.aborted) setError(true); }
    finally { if (request.current === controller) { request.current = null; setLoading(false); } }
  }, [active, shell.mock]);
  useEffect(() => {
    const element = sentinel.current;
    if (!active || !element || !state.nextCursor || state.batches >= 3 || error || loading) return;
    const observer = new IntersectionObserver(entries => { if (entries.some(entry => entry.isIntersecting)) void loadMore(); }, { root: element.closest("[data-p0-scroller]"), rootMargin: "900px 0px" });
    observer.observe(element);
    return () => observer.disconnect();
  }, [active, state.nextCursor, state.batches, loadMore, loading, error]);
  const days = useMemo(() => groupTimeline(state.cards), [state.cards]);
  let order = 0;
  return <div className={styles.timeline} data-featured-batches={state.batches}>
    {days.map(({ day, cards }) => {
      const collapsed = state.collapsed.includes(day);
      return <section key={day} className={styles.day} aria-label={day} data-collapsed={collapsed}>
        <DayHeader day={day} count={state.dayCounts[day] ?? null} collapsed={collapsed} onToggle={() => { const previous = stateRef.current; const next = { ...previous, collapsed: previous.collapsed.includes(day) ? previous.collapsed.filter(value => value !== day) : [...previous.collapsed, day] }; stateRef.current = next; setState(next); }} />
        <div aria-hidden={collapsed} inert={collapsed}><Collapse open={!collapsed}><ol className={styles.slots}>
          {cards.map(card => <TimelineSlot key={card.key} dataKey={card.key} at={card.anchorAt} fresh={freshKeys.has(card.key)} delay={freshKeys.has(card.key) ? Math.min(order++, 10) * 40 : 0}><FeedItem article={card.item} taxonomy={taxonomy} at={card.anchorAt} group={card.group} filters={state.filters} /></TimelineSlot>)}
        </ol></Collapse></div>
      </section>;
    })}
    <div ref={sentinel} className={styles.sentinel} aria-hidden="true" />
    <div className={styles.end}>
      {loading ? <span className={styles.loading}><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="12" cy="12" r="9" opacity=".2" /><path d="M12 3a9 9 0 0 1 9 9" /></svg>正在加载</span> : error ? <button type="button" data-error="true" onClick={loadMore}>加载失败，点此重试</button> : state.nextCursor ? state.batches >= 3 && <button type="button" onClick={loadMore}>加载更多</button> : state.cards.length > 0 && <span>已经到底了</span>}
    </div>
  </div>;
}
