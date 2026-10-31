"use client";
// AIHOT routes/hot.tsx + PhoneBar.tsx, adapted to the p0 scroller (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import { useEffect, useRef, useState } from "react";
import type { HotResponse } from "./_types";
import { monthDayTime } from "./_data";
import { InfoIcon } from "./HotMethod";
import styles from "./hot.module.css";
function showMethod() {
  const method = document.getElementById("hot-method") as HTMLDetailsElement | null;
  if (!method) return;
  method.open = true;
  method.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
}
export function HotHeader({ hot, mock }: { hot: HotResponse | null; mock: boolean }) {
  const bar = useRef<HTMLElement>(null), heading = useRef<HTMLHeadingElement>(null);
  const [scrolled, setScrolled] = useState(false), [under, setUnder] = useState(false);
  useEffect(() => {
    const scroller = bar.current?.closest<HTMLElement>("[data-p0-scroller]");
    if (!scroller) return;
    let frame = 0;
    const update = () => {
      frame = 0; setScrolled(scroller.scrollTop > 4);
      if (heading.current && bar.current) setUnder(heading.current.getBoundingClientRect().bottom < bar.current.getBoundingClientRect().bottom);
    };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(update); };
    update(); scroller.addEventListener("scroll", schedule, { passive: true });
    const resize = new ResizeObserver(schedule); resize.observe(scroller);
    return () => { scroller.removeEventListener("scroll", schedule); resize.disconnect(); cancelAnimationFrame(frame); };
  }, []);
  const title = `热点榜${mock ? "（演示）" : ""}`;
  const description = `过去 ${hot?.windowHours ?? 48} 小时，智慧警务科技领域讨论最多的 ${hot?.entries.length || 10} 件事`;
  return <>
    <header ref={bar} className={styles.phoneBar} data-scrolled={scrolled}>
      <div className={styles.phoneBarGrid}><div /><div className={styles.phoneTitle} data-shown={under} aria-hidden={!under}>{title}</div><div className={styles.phoneActions}><button type="button" onClick={showMethod}><InfoIcon size={17} />怎么算</button></div></div>
    </header>
    <div className={styles.phoneHeading}><h1 ref={heading} data-page-title>{title}</h1><div>{description}{hot?.computedAt && <> · <span className={styles.num}>{monthDayTime(hot.computedAt)}</span> 更新</>}</div></div>
    <header className={styles.desktopHeader}><div><div className={styles.liveLabel}><span className={styles.live} aria-hidden="true"><i /><b /></span>实时热度</div><h1>{title}</h1><p>{description}</p></div>{hot?.computedAt && <p className={styles.updated}><span className={styles.num}>{monthDayTime(hot.computedAt)}</span> 更新 · 按讨论热度排序</p>}</header>
  </>;
}
