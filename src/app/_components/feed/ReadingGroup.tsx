"use client";
// AIHOT features/feed/ReadingGroup.tsx (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { GroupInfo, GroupReport, TimelineFilters } from "../../_lib/feed-types";
import { readSessionSnapshot, saveSessionSnapshot } from "../../_lib/session-restore";
import { articleMoment, dayHeading } from "../../all/_data";
import { getMockGroupReports } from "../featured/_mock";
import { useMainShell } from "../home/MainShell";
import { Collapse } from "./Presence";
import { Sheet } from "./Sheet";
import { IntentLink } from "./IntentLink";
import { IconArrowUpRight, IconChevronDown, IconChevronRight } from "./icons";
import { groupReportsUrl, requestGroupReports } from "./group-request";
import styles from "./feed.module.css";

const labelOf = (group: GroupInfo) => group.additionalSourceCount > 0 ? `另有 ${group.additionalSourceCount} 家信源报道` : `${group.reportCount} 篇报道`;

function useReports(group: GroupInfo, filters?: TimelineFilters) {
  const shell = useMainShell();
  const url = groupReportsUrl(group.factId, filters);
  const [state, setState] = useState<{ url: string; reports: GroupReport[] | null; loading: boolean; error: boolean }>({ url, reports: null, loading: false, error: false });
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), [url]);
  const load = useCallback(async (again = false) => {
    request.current?.abort();
    const controller = request.current = new AbortController();
    setState(previous => ({ url, reports: previous.url === url ? previous.reports : null, loading: true, error: false }));
    try {
      const reports = shell.mock ? await getMockGroupReports(group.factId, filters ?? { region: "", topic: "" }) : await requestGroupReports(url, controller.signal, again);
      if (!controller.signal.aborted) setState({ url, reports: Array.isArray(reports) ? reports : reports.reports, loading: false, error: false });
    } catch {
      if (!controller.signal.aborted) setState(previous => ({ ...previous, loading: false, error: !previous.reports }));
    }
  }, [url, shell.mock, group.factId, filters]);
  return { ...(state.url === url ? state : { url, reports: null, loading: false, error: false }), load };
}
function LoadState({ loading, error, empty, onRetry }: { loading: boolean; error: boolean; empty: boolean; onRetry: () => void }) {
  if (loading && empty) return <div className={styles.groupSkeleton}>{[0, 1].map(i => <div key={i} />)}</div>;
  if (error) return <button type="button" className={styles.groupError} onClick={onRetry}>暂时无法加载，点此重试</button>;
  return null;
}

/** Only expansion is saved. no-store report payloads are fetched again on return. */
export function GroupSources({ group, filters, parentId }: { group: GroupInfo; filters?: TimelineFilters; parentId: string }) {
  const shell = useMainShell();
  const holdRestore = shell.holdRestore;
  const entry = `groups-open:${shell.routeKey}`;
  const key = `${groupReportsUrl(group.factId, filters)}:${parentId}`;
  const [open, setOpen] = useState(false);
  const { reports, loading, error, load } = useReports(group, filters);
  const restoreKey = useRef("");
  useLayoutEffect(() => {
    if (!shell.restore || restoreKey.current === `${entry}:${key}`) return;
    restoreKey.current = `${entry}:${key}`;
    if (readSessionSnapshot<Record<string, boolean>>(entry, shell.mock)?.[key]) {
      const release = holdRestore(shell.routeKey);
      const openedAt = performance.now();
      let active = true, timer: ReturnType<typeof setTimeout> | undefined, frame = 0;
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore a previously expanded group on history activation
      setOpen(true);
      void load(true).finally(() => {
        if (!active) return;
        const duration = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 240;
        timer = setTimeout(() => { frame = requestAnimationFrame(() => { frame = requestAnimationFrame(release); }); }, Math.max(0, openedAt + duration - performance.now()));
      });
      return () => { active = false; clearTimeout(timer); cancelAnimationFrame(frame); release(); };
    }
  }, [entry, key, shell.restore, shell.mock, shell.routeKey, holdRestore, load]);
  const toggle = () => {
    const next = !open;
    setOpen(next);
    const saved = { ...readSessionSnapshot<Record<string, boolean>>(entry, shell.mock) };
    if (next) saved[key] = true; else delete saved[key];
    saveSessionSnapshot(entry, saved, shell.mock);
    if (next && !reports && !loading) void load();
  };
  const others = (reports ?? []).filter(report => report.id !== parentId);
  return <div><button type="button" className={styles.groupToggle} aria-expanded={open} onClick={event => { event.preventDefault(); event.stopPropagation(); toggle(); }}>{labelOf(group)}<IconChevronDown size={13} className={open ? styles.groupChevronOpen : undefined} /></button>
    <Collapse open={open} className={styles.groupCollapse}><div className={styles.groupPanel}><ul>{others.map(report => <li key={report.id}><span className={styles.groupSource}>{report.source.name}</span><IntentLink href={shell.href(`/articles/${report.id}`)} className={styles.groupTitle}>{report.title}</IntentLink><a href={report.originalUrl} target="_blank" rel="noopener noreferrer" aria-label="打开原文"><IconArrowUpRight size={13} /></a></li>)}</ul><LoadState loading={loading} error={error} empty={!others.length} onRetry={() => void load()} /></div></Collapse>
  </div>;
}
export function GroupButton({ group, filters, parentId }: { group: GroupInfo; filters?: TimelineFilters; parentId: string }) {
  const [open, setOpen] = useState(false), [mounted, setMounted] = useState(false);
  return <><button type="button" className={styles.groupButton} aria-expanded={open} aria-haspopup="dialog" onClick={event => { event.preventDefault(); event.stopPropagation(); setMounted(true); setOpen(true); }}>{labelOf(group)}<IconChevronRight size={14} /></button>{mounted && <GroupSheet group={group} filters={filters} parentId={parentId} open={open} onClose={() => setOpen(false)} />}</>;
}
function GroupSheet({ group, filters, parentId, open, onClose }: { group: GroupInfo; filters?: TimelineFilters; parentId: string; open: boolean; onClose: () => void }) {
  const shell = useMainShell();
  const { reports, loading, error, load } = useReports(group, filters);
  useEffect(() => { if (open && !reports && !loading && !error) void load(); }, [open, reports, loading, error, load]);
  const others = (reports ?? []).filter(report => report.id !== parentId);
  return <Sheet open={open} onClose={onClose} title="同一新闻的其他报道"><div className={styles.groupSheet}><ul>{others.map(report => {
    const moment = articleMoment({ id: report.id, published_at: report.timelineAt });
    return <li key={report.id}><IntentLink href={shell.href(`/articles/${report.id}`)}><span>{report.source.name} · {dayHeading(moment.day).label} {moment.time}</span><strong>{report.title}</strong></IntentLink><a href={report.originalUrl} target="_blank" rel="noopener noreferrer" aria-label="打开原文"><IconArrowUpRight size={16} /></a></li>;
  })}</ul><LoadState loading={loading} error={error} empty={!others.length} onRetry={() => void load()} /></div></Sheet>;
}
