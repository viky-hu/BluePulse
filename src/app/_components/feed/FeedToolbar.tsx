"use client";
// AIHOT Filters.tsx: CategoryTabs and SearchField (MIT), framework adaptation only.
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import { useEffect, useRef, useState } from "react";
import { useMainShell } from "../home/MainShell";
import { buildHomeHref, type HomeFilters } from "../home/home-routes";
import { ALL_FILTERS, activeAllFilter, selectAllFilter } from "../../all/_data";
import { FeedIcon } from "./FeedIcons";
import { PillTabs } from "./PillTabs";
import styles from "./feed.module.css";

function SearchField({ filters, base }: { filters: HomeFilters; base: "/" | "/all" }) {
  const shell = useMainShell();
  const [value, setValue] = useState(filters.q);
  const input = useRef<HTMLInputElement>(null), composing = useRef(false);
  useEffect(() => {
    const focus = (event: KeyboardEvent) => {
      const target = event.target;
      if (!shell.active || event.defaultPrevented || document.querySelector('[role="dialog"][aria-modal="true"]:not([inert])') || event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey || event.isComposing || (target instanceof HTMLElement && (target.closest("input, textarea, select") || target.isContentEditable))) return;
      event.preventDefault(); input.current?.focus();
    };
    window.addEventListener("keydown", focus);
    return () => window.removeEventListener("keydown", focus);
  }, [shell.active]);
  return <form className={styles.search} role="search" aria-label="搜索全部动态" onSubmit={event => { event.preventDefault(); if (!composing.current) shell.navigate(buildHomeHref("/all", { ...filters, period: base === "/" ? "all" : filters.period, q: value.trim().slice(0, 200), sort: "recent" }, { mock: shell.mock })); }}>
    <label htmlFor="all-search" className={styles.srOnly}>搜索标题、摘要与正文</label>
    <span className={styles.searchIcon}><FeedIcon name="search" /></span>
    <input ref={input} id="all-search" name="q" value={value} onChange={event => setValue(event.target.value)} onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }} onKeyDown={event => { if (event.key === "Enter" && (event.nativeEvent.isComposing || composing.current || event.keyCode === 229)) event.preventDefault(); }} placeholder="搜索标题、摘要…" maxLength={200} autoComplete="off" enterKeyHint="search" />
    {value ? <button type="button" aria-label="清空" onClick={() => { setValue(""); input.current?.focus(); }}><FeedIcon name="close" /></button> : <kbd aria-hidden="true">/</kbd>}
  </form>;
}
export function FeedToolbar({ filters, base }: { filters: HomeFilters; base: "/" | "/all" }) {
  const shell = useMainShell();
  return <>
    <div className={styles.toolbar}>
      <PillTabs label="筛选" active={activeAllFilter(filters)} items={ALL_FILTERS.map(item => ({ ...item, to: buildHomeHref(base, selectAllFilter(filters, item.key), { mock: shell.mock }), prefetch: "intent" }))} />
      <SearchField key={`${base}:${filters.q}`} filters={filters} base={base} />
    </div>
    {base === "/all" && filters.q && <div className={styles.searchModes}><PillTabs size="xs" label="搜索排序" active="time" items={[{ key: "time", label: "最新" }, { key: "relevance", label: "全文相关", disabled: true, title: "全文相关排序暂不可用" }]} /></div>}
  </>;
}
