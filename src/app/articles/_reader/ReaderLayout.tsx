"use client";
// AIHOT ArticleLayout, RailSection and PhoneBar (MIT), using the p0 container.
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { IconArrowLeft, IconMore } from "../../_components/feed/icons";
import { useMainShell } from "../../_components/home/MainShell";
import { readerScroller } from "./scroll";
import styles from "./reader.module.css";

export function ArticleLayout({ left, right, children }: { left: ReactNode; right: ReactNode; children: ReactNode }) {
  return <div className={styles.layout}><aside className={styles.leftRail}><div className={styles.railInner}>{left}</div></aside><div className={styles.main}><div className={styles.measure}>{children}</div></div><aside className={styles.rightRail}><div className={styles.railInner}>{right}</div></aside></div>;
}
export function RailSection({ title, children }: { title?: ReactNode; children: ReactNode }) {
  return <section className={styles.railSection}>{title && <h2>{title}</h2>}<div>{children}</div></section>;
}
export function ReaderBack({ selected = false }: { selected?: boolean }) {
  const shell = useMainShell();
  return <button type="button" className={styles.back} onClick={() => {
    const previous = history.state?.pulsePrevious;
    if (typeof previous === "string" && previous.startsWith("/") && !previous.startsWith("//")) history.back();
    else shell.navigate(selected ? "/" : "/all");
  }}><IconArrowLeft size={16} />返回</button>;
}
export function ReaderHeader({ title, selected, onMore }: { title: string; selected?: boolean; onMore?: () => void }) {
  const bar = useRef<HTMLElement>(null), [under, setUnder] = useState(false), [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const area = readerScroller(bar.current);
    if (!area) return;
    let frame = 0;
    const update = () => {
      frame = 0; setScrolled(area.scrollTop > 4);
      const heading = area.querySelector<HTMLElement>("[data-page-title]");
      setUnder(!heading || (!!bar.current && heading.getBoundingClientRect().bottom < bar.current.getBoundingClientRect().bottom));
    };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(update); };
    update(); area.addEventListener("scroll", schedule, { passive: true });
    const observer = new ResizeObserver(schedule); observer.observe(area);
    return () => { cancelAnimationFrame(frame); observer.disconnect(); area.removeEventListener("scroll", schedule); };
  }, [title]);
  return <header ref={bar} className={styles.phoneBar} data-reader-bar data-scrolled={scrolled}><div className={styles.phoneBarGrid}><ReaderBack selected={selected} /><span className={styles.phoneTitle} data-shown={under} aria-hidden={!under}>{title}</span><div className={styles.phoneActions}>{onMore && <button type="button" className={styles.iconButton} aria-label="更多操作" onClick={onMore}><IconMore size={22} /></button>}</div></div></header>;
}
