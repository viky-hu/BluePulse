"use client";
// AIHOT Filters.tsx: FeedBar, FilterSheet and ActiveFilters (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import { useEffect, useState } from "react";
import { useMainShell } from "../home/MainShell";
import { PhoneBar } from "../home/mobile/MobileChrome";
import { buildHomeHref, type HomeFilters } from "../home/home-routes";
import { ALL_FILTERS, activeAllFilter, selectAllFilter } from "../../all/_data";
import { Sheet } from "./Sheet";
import { IntentLink } from "./IntentLink";
import { FeedIcon } from "./FeedIcons";
import styles from "./feed.module.css";

export function FeedPhoneBar({ filters, base }: { filters: HomeFilters; base: "/" | "/all" }) {
  const shell = useMainShell();
  const [open, setOpen] = useState(false);
  const active = activeAllFilter(filters), filtered = active !== "all";
  const selected = [filters.region, filters.topic].filter(Boolean).map(key => ({ key, label: ALL_FILTERS.find(item => item.key === key)?.label ?? key }));
  const link = (next: HomeFilters) => buildHomeHref(base, next, { mock: shell.mock });
  useEffect(() => {
    const query = matchMedia("(max-width: 768px)");
    const closeOnDesktop = () => { if (!query.matches) setOpen(false); };
    query.addEventListener("change", closeOnDesktop);
    return () => query.removeEventListener("change", closeOnDesktop);
  }, []);
  return <>
    <PhoneBar title={base === "/" ? "精选" : "全部动态"} actions={<>
      <button type="button" className={styles.phoneAction} aria-label={filtered ? "筛选（已选）" : "筛选"} aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)} data-on={filtered}>
        <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true"><path d="M4 7h16M7 12h10M10 17h4" /></svg>
        {filtered && <i aria-hidden="true" />}
      </button>
      <IntentLink href={buildHomeHref("/search", filters, { mock: shell.mock })} className={styles.phoneAction} aria-label="搜索"><FeedIcon name="search" /></IntentLink>
    </>} />
    <Sheet open={open} onClose={() => setOpen(false)} title="筛选">
      <ul className={styles.filterOptions}>{ALL_FILTERS.map(item => <li key={item.key}>
        <IntentLink href={link(selectAllFilter(filters, item.key))} aria-current={active === item.key ? "true" : undefined} onClick={() => setOpen(false)}>
          <span>{item.key === "all" ? "不限" : item.label}</span>
          {active === item.key && <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m5 12 4 4L19 6" /></svg>}
        </IntentLink>
      </li>)}</ul>
    </Sheet>
    {(selected.length > 0 || filters.tag) && <nav className={styles.activeFilters} aria-label="当前筛选">
      {selected.map(item => <IntentLink key={item.key} keepScroll href={link({ ...filters, ...(item.key === filters.region ? { region: "" } : { topic: "" }) })} aria-label={`取消筛选：${item.label}`}>只看{item.label}<FeedIcon name="close" /></IntentLink>)}
      {filters.tag && <IntentLink keepScroll href={link({ ...filters, tag: "" })} aria-label={`取消标签：${filters.tag}`}><span>#{filters.tag}</span><FeedIcon name="close" /></IntentLink>}
    </nav>}
  </>;
}
