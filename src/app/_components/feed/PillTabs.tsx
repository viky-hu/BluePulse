"use client";
// Direct structural port of AIHOT components/ui/Tabs.tsx (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import Link from "next/link";
import { useRef, type MutableRefObject, type ReactNode } from "react";
import { useGSAP } from "@gsap/react";
import { IntentLink } from "./IntentLink";
import styles from "./feed.module.css";

type Place = { left: number; width: number; at: number };
function placeOf(element: HTMLElement): Place {
  const tab = element.parentElement!.getBoundingClientRect();
  const track = element.closest("[data-pill-track]")!.getBoundingClientRect();
  return { left: tab.left - track.left, width: tab.width, at: Date.now() };
}
function Thumb({ previous }: { previous: MutableRefObject<Place | null> }) {
  const ref = useRef<HTMLSpanElement>(null);
  useGSAP(() => {
    const element = ref.current;
    if (!element) return;
    const now = placeOf(element), from = previous.current;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    let animation: Animation | undefined;
    if (!reduced.matches && from && now.at - from.at < 1000 && (from.left !== now.left || from.width !== now.width)) {
      animation = element.animate([
        { transform: `translateX(${from.left - now.left}px)`, width: `${from.width}px` },
        { transform: "translateX(0)", width: `${now.width}px` },
      ], { duration: 300, easing: "cubic-bezier(0.25, 1, 0.5, 1)" });
    }
    const cancel = () => animation?.cancel();
    reduced.addEventListener("change", cancel);
    return () => { previous.current = placeOf(element); cancel(); reduced.removeEventListener("change", cancel); };
  }, { scope: ref });
  return <span ref={ref} className={styles.thumb} aria-hidden="true" />;
}
export interface TabItem {
  key: string; label: ReactNode; to?: string; prefetch?: "intent";
  resetScroll?: boolean; disabled?: boolean; title?: string;
}
export function PillTabs({ items, active, onSelect, size = "md", label }: { items: TabItem[]; active: string; onSelect?: (key: string) => void; size?: "md" | "xs"; label: string }) {
  const previous = useRef<Place | null>(null);
  const links = items.some(item => item.to);
  const Track = links ? "nav" : "div";
  return <div className={styles.tabsViewport}><Track data-pill-track="" className={styles.tabs} data-size={size} aria-label={label} role={links ? undefined : "tablist"}>
    {items.map(item => {
      const on = item.key === active;
      const inner = <>{on && <Thumb previous={previous} />}<span className={styles.tabLabel}>{item.label}</span></>;
      return item.to ? item.prefetch === "intent" ? <IntentLink key={item.key} href={item.to} keepScroll={!item.resetScroll} data-filter={item.key} aria-current={on ? "page" : undefined} title={item.title}>{inner}</IntentLink> : <Link key={item.key} href={item.to} data-pulse-scroll={!item.resetScroll ? "preserve" : undefined} data-filter={item.key} aria-current={on ? "page" : undefined} title={item.title}>{inner}</Link> : <button key={item.key} type="button" role="tab" aria-selected={on} disabled={item.disabled} title={item.title} onClick={() => onSelect?.(item.key)}>{inner}</button>;
    })}
  </Track></div>;
}
