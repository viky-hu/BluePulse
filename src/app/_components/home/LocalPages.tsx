"use client";
import Link from "next/link";
import { useBrowserState } from "../../_lib/use-browser-state";
import { RouteReady, useMainShell } from "./MainShell";
import { ArticleRows } from "./HomeDashboard";
import styles from "./home.module.css";
export function LocalPages({ kind }: { kind: "history" }) {
  const shell = useMainShell();
  const { state, store } = useBrowserState(shell.mock);
  return <section className={`${styles.content} ${styles.historySection}`} data-local-page={kind}>
    <RouteReady ready={state.ready} />
    <div className={styles.viewTools}><h1 className={styles.feedLabel}>浏览历史</h1>{state.history.length ? <button type="button" className={styles.clearButton} onClick={() => store.clearHistory()}>清空历史</button> : null}</div>
    <p className={styles.collectedNote}>仅记录在当前浏览器中阅读的最近 30 篇文章。</p>
    {!state.ready ? <p role="status">正在读取浏览器记录…</p> : state.history.length ? <ArticleRows articles={state.history.map(item => item.article)} /> : <p>暂无浏览记录。<Link href={shell.href("/")}>返回精选</Link></p>}
  </section>;
}
