"use client";
// AIHOT report route loaders adapted to Pulse's existing shared-shell lifecycle (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import { useEffect, useRef, useState } from "react";
import { RouteReady, useMainShell } from "../_components/home/MainShell";
import { emptyDailyData, getCachedDailyPage, invalidateDailyPage, loadDailyPage } from "./_cache";
import { dailyRoute } from "./_route";
import { reportOutline } from "./_paper";
import { ReportLayout } from "./ReportLayout";
import { ReportPaper } from "./ReportPaper";
import { DailyArchive } from "./DailyArchive";
import styles from "./daily.module.css";

export function DailyPage() {
  const shell = useMainShell();
  const [loaded, setLoaded] = useState(() => getCachedDailyPage(shell.routeKey, shell.mock) ?? emptyDailyData(shell.routeKey));
  const [retry, setRetry] = useState(0);
  const previous = useRef({ key: shell.routeKey, refresh: shell.refreshRevision, retry: 0 });
  useEffect(() => {
    if (shell.activation.key !== shell.routeKey) return;
    const key = shell.routeKey, last = previous.current;
    const force = last.key === key && (last.refresh !== shell.refreshRevision || last.retry !== retry);
    previous.current = { key, refresh: shell.refreshRevision, retry };
    const controller = new AbortController();
    queueMicrotask(() => {
      if (controller.signal.aborted) return;
      setLoaded(getCachedDailyPage(key, shell.mock) ?? emptyDailyData(key));
      void loadDailyPage(key, shell.mock, force).then(data => { if (!controller.signal.aborted) setLoaded(data); });
    });
    return () => controller.abort();
  }, [shell.activation.key, shell.routeKey, shell.mock, shell.refreshRevision, retry]);
  const data = loaded.key === shell.routeKey ? loaded : emptyDailyData(shell.routeKey);
  const route = dailyRoute(shell.pathname), report = data.report;
  const again = () => { invalidateDailyPage(shell.routeKey, shell.mock); setRetry(n => n + 1); };
  const state = data.status === "unavailable" ? "日报服务尚未接入" : data.status === "not-found" ? "未找到这期日报" : "日报暂时无法载入";
  const body = data.status === "error" || data.status === "unavailable" || data.status === "not-found"
    ? <div className={styles.empty} role="alert"><h2>{state}</h2><p>{data.error}</p><button type="button" onClick={again}>重试</button></div>
    : data.status === "ready" && !report ? <div className={styles.empty}><h2>还没有发布警务科技日报</h2><p>第一期发布后会出现在这里。</p></div> : null;
  return <div className={styles.page} data-daily-status={data.status}>
    <RouteReady ready={data.status !== "loading"} />
    {route?.kind === "archive" && data.status === "ready" ? <DailyArchive key={`${data.key}:${shell.refreshRevision}:${retry}`} index={data.index} today={data.today} /> : <ReportLayout key={`${data.key}:${shell.refreshRevision}:${retry}`} kind="daily" index={data.index} current={report?.key ?? null} today={data.today} outline={report ? reportOutline(report) : []}>
      {report && data.status === "ready" ? <ReportPaper key={`${report.key}:${report.generatedAt}`} report={report} index={data.index} /> : body}
    </ReportLayout>}
  </div>;
}
