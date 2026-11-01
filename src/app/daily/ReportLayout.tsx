"use client";
// AIHOT ReportLayout and Kicker (MIT). Copyright (c) 2026 数字生命卡兹克.
import { useEffect, useRef, useState, type AnchorHTMLAttributes, type ReactNode } from "react";
import { IntentLink } from "../_components/feed/IntentLink";
import { Sheet } from "../_components/feed/Sheet";
import { useMainShell } from "../_components/home/MainShell";
import type { OutlineEntry } from "./_paper";
import type { ReportKind, ReportNavigationEntry } from "./_types";
import { KindSwitch, ReportArchive, ReportPhoneNav } from "./ReportNav";
import styles from "./daily.module.css";

function scrollerOf(target: HTMLElement | null) { let parent = target?.parentElement ?? null; while (parent && !/(auto|scroll)/.test(getComputedStyle(parent).overflowY)) parent = parent.parentElement; return parent; }
export function scrollToReport(id: string) {
  const target = document.getElementById(id); if (!target) return;
  const parent = scrollerOf(target);
  const bar = target.closest(`.${styles.shell}`)?.querySelector<HTMLElement>(`[data-phone-bar]`);
  const offset = bar && getComputedStyle(bar).display !== "none" ? bar.offsetHeight + 24 : 24;
  if (parent) parent.scrollTo({ top: parent.scrollTop + target.getBoundingClientRect().top - parent.getBoundingClientRect().top - offset, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  history.replaceState(history.state, "", `#${id}`);
}
export function DailyLink({ to, viewTransition, children, onClick, ...props }: Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & { to: string; viewTransition?: boolean }) {
  const { href } = useMainShell();
  void viewTransition;
  if (to.startsWith("#")) return <a href={to} {...props} onClick={event => { onClick?.(event); if (!event.defaultPrevented) { event.preventDefault(); scrollToReport(to.slice(1)); } }}>{children}</a>;
  if (!to.startsWith("/")) return <a href={to} {...props} onClick={onClick}>{children}</a>;
  return <IntentLink href={href(to)} {...props} onClick={onClick}>{children}</IntentLink>;
}
export function Kicker({ children, className = "" }: { children: ReactNode; className?: string }) { return <div className={`flex items-center gap-2.5 text-[12px] font-semibold tracking-[0.3em] text-accent ${className}`}><span className="h-[2px] w-6 rounded-full bg-accent" aria-hidden="true" />{children}</div>; }
export function ReportLayout({ kind, index, current, today, outline = [], back, title, children }: { kind: ReportKind; index: ReportNavigationEntry[]; current: string | null; today: string; outline?: readonly OutlineEntry[]; back?: { to: string; label: string }; title?: string; children: ReactNode }) {
  const root = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false), [active, setActive] = useState(""), [scrolled, setScrolled] = useState(false), [titleShown, setTitleShown] = useState(false);
  useEffect(() => { const element = root.current; const scroller = scrollerOf(element); if (!element || !scroller) return; const resize = new ResizeObserver(() => element.style.setProperty("--daily-scroller-height", `${scroller.clientHeight}px`)); resize.observe(scroller); return () => resize.disconnect(); }, []);
  useEffect(() => { const element = root.current; const scroller = scrollerOf(element); const update = () => { const bar = element?.querySelector<HTMLElement>("[data-phone-bar]"); const barHeight = bar && getComputedStyle(bar).display !== "none" ? bar.offsetHeight : 0; const boundary = (scroller?.getBoundingClientRect().top ?? 0) + barHeight + 24; setScrolled((scroller?.scrollTop ?? 0) > 4); const heading = element?.querySelector<HTMLElement>("[data-page-title]"); setTitleShown(!heading || heading.getBoundingClientRect().bottom < boundary - 24); let current = ""; for (const item of outline) { const target = document.getElementById(item.id); if (target && target.getBoundingClientRect().top <= boundary) current = item.id; } setActive(current); }; scroller?.addEventListener("scroll", update, { passive: true }); update(); return () => scroller?.removeEventListener("scroll", update); }, [outline]);
  return <div ref={root} className={styles.shell}><ReportArchive kind={kind} index={index} current={current} /><div className={styles.body}>
    <header data-phone-bar="" className={`${styles.phoneBar} ${!back ? styles.wideBar : ""} ${scrolled ? styles.scrolled : ""}`}>{back ? <><DailyLink to={back.to} className={styles.back}><svg width="25" height="25" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15 5l-7 7 7 7" /></svg><span>{back.label}</span></DailyLink><span aria-hidden={!titleShown} className={`${styles.phoneTitle} ${titleShown ? styles.titleShown : ""}`}>{title}</span><span /></> : <><KindSwitch kind={kind} phone />{outline.length > 0 ? <button type="button" title="本期目录" aria-label="本期目录" onClick={() => setOpen(true)}><svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M8 6h13M8 12h13M8 18h13" /><circle cx="3.5" cy="6" r="1" /><circle cx="3.5" cy="12" r="1" /><circle cx="3.5" cy="18" r="1" /></svg></button> : <span />}</>}</header>
    {!back && <ReportPhoneNav kind={kind} index={index} current={current} today={today} />}
    {outline.length > 0 && <Sheet open={open} onClose={() => setOpen(false)} title="本期目录"><div className={styles.outline}><ol>{outline.map((item, i) => <li key={item.id}><a href={`#${item.id}`} className={`${styles.outlineItem} ${active === item.id ? styles.outlineActive : ""} ${item.level > 2 ? styles.outlineNested : ""}`} aria-current={active === item.id ? "location" : undefined} onClick={event => { event.preventDefault(); setOpen(false); requestAnimationFrame(() => scrollToReport(item.id)); }}>{item.level <= 2 && <span className={styles.outlineMark}>{item.mark ?? String(i + 1).padStart(2, "0")}</span>}<span className={styles.outlineLabel}>{item.text}</span>{active === item.id ? <span className={styles.outlineCurrent}>正在读</span> : item.note && <span className={styles.outlineNote}>{item.note}</span>}</a></li>)}</ol></div></Sheet>}
    <div className={styles.paper}>{children}</div></div></div>;
}
