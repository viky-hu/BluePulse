"use client";
// AIHOT ReaderTools, item actions, Menu and OutlineSheet (MIT), adapted to p0.
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Sheet } from "../../_components/feed/Sheet";
import { Presence } from "../../_components/feed/Presence";
import { IconBookmark, IconCopy, IconDownload, IconExternal, IconImage, IconList, IconMenu, IconShare } from "../../_components/feed/icons";
import { useBrowserState } from "../../_lib/use-browser-state";
import { useMainShell } from "../../_components/home/MainShell";
import type { ArticleSnapshotInput } from "../../_components/home/ArticleActions";
import type { OutlineEntry } from "./types";
import { scrollToSection } from "./scroll";
import styles from "./reader.module.css";

export function useReaderStar(article: ArticleSnapshotInput) {
  const { mock } = useMainShell();
  const { state, store } = useBrowserState(mock);
  const on = state.starred.some(item => item.id === article.id);
  return { on, toggle: () => store.toggleStar({ id: article.id, title: article.title, summary: article.summary ?? null, sourceName: article.source.name, publishedAt: article.published_at, score: Number.isFinite(article.importance_score) ? article.importance_score : null }) };
}

export function useReaderToast() {
  const [toast, setToast] = useState<string | null>(null);
  useEffect(() => { if (toast) { const timer = setTimeout(() => setToast(null), 1600); return () => clearTimeout(timer); } }, [toast]);
  return [toast, setToast] as const;
}

export function usePaperHost() {
  const [host, setHost] = useState<HTMLElement | null>(null);
  useLayoutEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- resolve the existing external portal host before paint
    setHost(document.querySelector<HTMLElement>("[data-p0-content]"));
  }, []);
  return host;
}

function useReadingDown(host: HTMLElement | null) {
  const [down, setDown] = useState(false);
  useEffect(() => {
    const area = host?.querySelector<HTMLElement>("[data-p0-scroller]");
    if (!area) return;
    let last = area.scrollTop, frame = 0;
    const update = () => {
      frame = 0;
      const y = area.scrollTop, end = area.scrollHeight - area.clientHeight;
      if (y < 80 || y > end - 120) { setDown(false); last = y; }
      else if (Math.abs(y - last) > 6) { setDown(y > last); last = y; }
    };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(update); };
    area.addEventListener("scroll", schedule, { passive: true });
    return () => { cancelAnimationFrame(frame); area.removeEventListener("scroll", schedule); };
  }, [host]);
  return down;
}

export function ReaderToolbar({ saved, toggle, onOutline, onShare, originalUrl, originalLabel, wide }: {
  saved: boolean; toggle: () => void; onOutline?: () => void; onShare: () => void;
  originalUrl?: string | null; originalLabel: string; wide: boolean;
}) {
  const host = usePaperHost(), hidden = useReadingDown(host);
  const { active } = useMainShell();
  if (!host) return null;
  const tool = (icon: ReactNode, label: string, action?: () => void, pressed?: boolean) => <button type="button" onClick={action} disabled={!action} aria-pressed={pressed} className={styles.tool} data-on={pressed}>{icon}<span>{label}</span></button>;
  return createPortal(<nav className={`${styles.chrome} ${styles.toolbar}`} aria-label="阅读工具" data-wide={wide} data-hidden={hidden} inert={!active}>
    <div className={styles.toolGrid} style={{ gridTemplateColumns: `repeat(${onOutline ? 4 : 3}, minmax(0,1fr))` }}>
      {tool(<IconBookmark size={22} filled={saved} />, saved ? "已收藏" : "收藏", toggle, saved)}
      {onOutline && tool(<IconList size={22} />, "目录", onOutline)}
      {tool(<IconShare size={22} />, "分享", onShare)}
      {originalUrl ? <a href={originalUrl} target="_blank" rel="noopener noreferrer" className={styles.tool}><IconExternal size={22} /><span>{originalLabel}</span></a> : tool(<IconExternal size={22} />, originalLabel)}
    </div>
  </nav>, host);
}

export function ReadingProgress() {
  const host = usePaperHost(), ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const area = host?.querySelector<HTMLElement>("[data-p0-scroller]");
    if (!area) return;
    let frame = 0;
    const update = () => { frame = 0; const max = area.scrollHeight - area.clientHeight; if (ref.current) ref.current.style.transform = `scaleX(${max > 0 ? Math.min(1, Math.max(0, area.scrollTop / max)) : 0})`; };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(update); };
    update();
    area.addEventListener("scroll", schedule, { passive: true }); area.addEventListener("load", schedule, true);
    const observer = new ResizeObserver(schedule); observer.observe(area); if (area.firstElementChild) observer.observe(area.firstElementChild);
    return () => { cancelAnimationFrame(frame); observer.disconnect(); area.removeEventListener("scroll", schedule); area.removeEventListener("load", schedule, true); };
  }, [host]);
  return host ? createPortal(<div ref={ref} className={`${styles.chrome} ${styles.progress}`} aria-hidden="true" data-reading-progress />, host) : null;
}

export function Toast({ text }: { text: string | null }) {
  const host = usePaperHost();
  return host && text ? createPortal(<div role="status" className={`${styles.chrome} ${styles.toast}`}>{text}</div>, host) : null;
}

export interface ActionRow { key: string; label: string; icon: ReactNode; onSelect?: () => void; href?: string; download?: boolean }
export function ActionsSheet({ open, onClose, rows }: { open: boolean; onClose: () => void; rows: ActionRow[] }) {
  return <Sheet open={open} onClose={onClose} label="更多操作"><ul className={styles.toolSheet}>{rows.map(row => <li key={row.key}>{row.href
    ? <a href={row.href} download={row.download} onClick={onClose} className={styles.actionRow}>{row.icon}{row.label}</a>
    : <button type="button" className={styles.actionRow} onClick={() => { onClose(); row.onSelect?.(); }}>{row.icon}{row.label}</button>}</li>)}</ul></Sheet>;
}

export function MoreMenu({ rows, onShare }: { rows: ActionRow[]; onShare: () => void }) {
  const [open, setOpen] = useState(false), ref = useRef<HTMLDivElement>(null), trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => { if (!ref.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") { setOpen(false); trigger.current?.focus(); } };
    document.addEventListener("pointerdown", outside); document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); };
  }, [open]);
  const all: ActionRow[] = [{ key: "share", label: "分享链接", icon: <IconShare size={15} />, onSelect: onShare }, ...rows];
  return <div ref={ref} className={styles.menuWrap}><button ref={trigger} type="button" aria-label="更多操作" aria-haspopup="menu" aria-expanded={open} className={styles.iconButton} onClick={() => setOpen(!open)}><IconMenu size={17} /></button>
    <Presence show={open} enter={styles.menuEnter} exit={styles.menuExit} duration={140}><div className={styles.menu} role="menu">{all.map(row => row.href
      ? <a key={row.key} role="menuitem" href={row.href} download={row.download} onClick={() => setOpen(false)}>{row.icon}{row.label}</a>
      : <button key={row.key} role="menuitem" type="button" onClick={() => { setOpen(false); row.onSelect?.(); }}>{row.icon}{row.label}</button>)}</div></Presence>
  </div>;
}

export function OutlineSheet({ open, onClose, outline }: { open: boolean; onClose: () => void; outline: OutlineEntry[] }) {
  const [current, setCurrent] = useState<string | null>(null);
  useEffect(() => {
    if (!open) return;
    const area = document.querySelector<HTMLElement>("[data-p0-scroller]"), bar = area?.querySelector<HTMLElement>("[data-reader-bar]");
    const top = (area?.getBoundingClientRect().top ?? 0) + (bar?.offsetHeight ?? 0) + 24;
    let at: string | null = null;
    for (const entry of outline) { const target = document.getElementById(entry.id); if (target && target.getBoundingClientRect().top <= top) at = entry.id; }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reflect the current external scroll position when opening the sheet
    setCurrent(at);
  }, [open, outline]);
  let number = 0;
  return <Sheet open={open} onClose={onClose} title="目录"><ol className={`${styles.toolSheet} ${styles.outlineSheet}`}>{outline.map(entry => {
    const top = entry.level <= 2, on = entry.id === current;
    if (top) number++;
    return <li key={entry.id}><a href={`#${entry.id}`} data-nested={!top} aria-current={on ? "location" : undefined} onClick={event => { event.preventDefault(); onClose(); requestAnimationFrame(() => scrollToSection(entry.id)); }}>
      {top && <span className={styles.outlineNumber}>{String(number).padStart(2, "0")}</span>}<span>{entry.text}</span>{on && <small>正在读</small>}
    </a></li>;
  })}</ol></Sheet>;
}

export const actionIcons = { poster: <IconImage size={20} />, copy: <IconCopy size={20} />, markdown: <IconDownload size={20} /> };
