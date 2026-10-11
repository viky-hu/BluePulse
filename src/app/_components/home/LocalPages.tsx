"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useBrowserState } from "../../_lib/use-browser-state";
import { MOCK_ARTICLE_DETAILS } from "../../_lib/home-mock";
import { RouteReady, useMainShell } from "./MainShell";
import { ArticleRows, displayDate } from "./HomeDashboard";
import styles from "./home.module.css";

export function LocalPages({ kind }: { kind: "history" | "starred" }) {
  const shell = useMainShell();
  const { state, store } = useBrowserState(shell.mock);
  const [result, setResult] = useState<{ key: string; items: Record<string, boolean>; error: boolean }>({ key: "", items: {}, error: false });
  const ids = useMemo(() => state.starred.map(item => item.id).sort().join(","), [state.starred]);
  const checkKey = `${shell.mock}:${shell.refreshRevision}:${ids}`;
  const availability = result.key === checkKey ? result.items : {};
  const availabilityError = result.key === checkKey && result.error;
  useEffect(() => {
    if (kind !== "starred" || !state.ready) return;
    let active = true;
    const controller = new AbortController();
    async function check() {
      const entries = ids ? ids.split(",") : [];
      const next: Record<string, boolean> = {};
      if (shell.mock) for (const id of entries) next[id] = !!MOCK_ARTICLE_DETAILS[id];
      else for (let offset = 0; offset < entries.length; offset += 100) {
        const batch = entries.slice(offset, offset + 100);
        const response = await fetch(`/api/bluepulse/articles/availability?ids=${batch.join(",")}`, { cache: "no-store", signal: AbortSignal.any([controller.signal, AbortSignal.timeout(12000)]) });
        if (!response.ok) throw Error("availability");
        const data = await response.json();
        if (!Array.isArray(data.items) || data.items.length !== batch.length || data.items.some((row: { id?: unknown; available?: unknown }) => typeof row.id !== "string" || !batch.includes(row.id) || typeof row.available !== "boolean")) throw Error("invalid availability");
        for (const row of data.items) next[row.id] = row.available;
      }
      if (active) setResult({ key: checkKey, items: next, error: false });
    }
    check().catch(() => { if (active) setResult({ key: checkKey, items: {}, error: true }); });
    return () => { active = false; controller.abort(); };
  }, [ids, kind, shell.mock, checkKey, state.ready]);
  return <section className={`${styles.content} ${styles.historySection}`}>
    <RouteReady ready={state.ready} />
    <div className={styles.viewTools}><h1 className={styles.feedLabel}>{kind === "history" ? "浏览历史" : "本机收藏"}</h1>{kind === "history" && state.history.length ? <button type="button" className={styles.clearButton} onClick={() => store.clearHistory()}>清空历史</button> : null}</div>
    <p className={styles.collectedNote}>{kind === "starred" ? "收藏仅保存在当前浏览器，最多保存 500 条；清除浏览器数据后会丢失。" : "仅记录在当前浏览器中阅读的最近 30 篇文章。"}</p>
    {!state.ready ? <p role="status">正在读取浏览器记录…</p> : kind === "history" ? state.history.length ? <ArticleRows articles={state.history.map(item => item.article)} /> : <p>暂无浏览记录。<Link href={shell.href("/")}>返回精选</Link></p> : state.starred.length ? <div className={styles.historyList}>
      {availabilityError ? <p className={styles.collectedNote} role="status">暂时无法核对文章状态，已保留收藏；可稍后重新打开此页。</p> : null}
      {state.starred.map((item, index) => <article key={item.id} data-card-key={item.id} className={styles.savedEntry}>
        <div className={styles.historyRow}><span className={styles.historyNo}>{String(index + 1).padStart(2, "0")}</span><div className={styles.historyCopy}>
          <small>{item.sourceName} · {displayDate(item.publishedAt)} · 收藏于 {displayDate(item.savedAt)}{item.score !== null ? ` · 评分 ${Math.round(item.score)}` : ""}</small>
          {availability[item.id] === false ? <strong>{item.title}</strong> : <Link href={shell.href(`/articles/${item.id}`)}><strong>{item.title}</strong></Link>}
          {item.summary ? <p className={styles.articleRowSummary}>{item.summary}</p> : null}
          {availability[item.id] === false ? <small role="status">文章已不可公开访问，保留本机收藏快照。</small> : null}
        </div></div><button className={styles.starButton} type="button" onClick={() => store.removeStar(item.id)}>移除收藏</button>
      </article>)}
    </div> : <p>暂无收藏。<Link href={shell.href("/")}>浏览精选资讯</Link></p>}
  </section>;
}
