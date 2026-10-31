"use client";
// AIHOT routes/hot.tsx composition (MIT). Copyright (c) 2026 数字生命卡兹克.
// See THIRD_PARTY_NOTICES.md. React Router loader replaced by Pulse's shared route lifecycle.
import { useEffect, useRef, useState } from "react";
import { RouteReady, useMainShell } from "../_components/home/MainShell";
import { emptyHotData, getCachedHot, invalidateHot, loadHot } from "./_cache";
import { Lead, Runner, Row, pad } from "./HotCards";
import { HotHeader } from "./HotHeader";
import { HotMethod } from "./HotMethod";
import styles from "./hot.module.css";

export function HotPage() {
  const shell = useMainShell();
  const [loaded, setLoaded] = useState(() => getCachedHot(shell.routeKey, shell.mock) ?? emptyHotData(shell.routeKey));
  const [retry, setRetry] = useState(0);
  const request = useRef({ key: shell.routeKey, revision: shell.refreshRevision, retry: 0 });
  useEffect(() => {
    if (shell.activation.key !== shell.routeKey) return;
    const key = shell.routeKey, previous = request.current;
    const force = previous.key === key && (previous.revision !== shell.refreshRevision || previous.retry !== retry);
    request.current = { key, revision: shell.refreshRevision, retry };
    const controller = new AbortController();
    queueMicrotask(() => {
      if (controller.signal.aborted) return;
      setLoaded(emptyHotData(key));
      void loadHot(key, shell.mock, force).then(data => { if (!controller.signal.aborted) setLoaded(data); });
    });
    return () => controller.abort();
  }, [shell.activation.key, shell.routeKey, shell.mock, shell.refreshRevision, retry]);
  const data = loaded.key === shell.routeKey ? loaded : emptyHotData(shell.routeKey);
  const hot = data.hot, [lead, ...rest] = hot?.entries ?? [], runners = rest.slice(0, 2), others = rest.slice(2);
  const retryHot = () => { invalidateHot(shell.routeKey, shell.mock); setRetry(value => value + 1); };
  return <div className={styles.page} data-hot-status={data.status}>
    <RouteReady ready={data.status !== "loading"} />
    <HotHeader hot={hot} mock={shell.mock} />
    {(data.status === "error" || data.status === "unavailable") && <div className={`${styles.card} ${styles.emptyCard}`} role="alert"><div className={styles.empty}><div>{data.status === "unavailable" ? "热点榜服务尚未接入" : "热点榜暂时无法载入"}</div><p>{data.error}</p><button type="button" onClick={retryHot}>重试</button></div></div>}
    {data.status === "ready" && (!lead ? <div className={`${styles.card} ${styles.emptyCard}`}><div className={styles.empty}><div>暂时没有热点</div><p>还没有足够多来源共同讨论的事件。</p></div></div> : <>
      <section aria-label="热度前三" className={styles.topThree}><div className={styles.leadSlot}><Lead e={lead} /></div>{runners.map(e => <div className={styles.runnerSlot} key={e.story.publicId}><Runner e={e} /></div>)}</section>
      {others.length > 0 && <section aria-label="其余热点" className={styles.others}><div className={styles.othersHeader}><h2>继续看 <span>No.{pad(others[0].rank)}–{pad(others[others.length - 1].rank)}</span></h2><span>参与者 · 24 小时走势 · 热度指数</span></div><ol className={styles.rows}>{others.map(e => <Row key={e.story.publicId} e={e} />)}</ol></section>}
    </>)}
    <HotMethod />
  </div>;
}
