"use client";
import { useEffect } from "react";
import { RouteReady, useMainShell } from "../../_components/home/MainShell";
import { invalidateArticle } from "../_reader/cache";
import { ReaderBack, ReaderHeader } from "../_reader/ReaderLayout";
import styles from "../_reader/reader.module.css";
export default function ArticleNotFound() {
  const { routeKey, mock } = useMainShell();
  useEffect(() => { invalidateArticle(routeKey, mock); }, [routeKey, mock]);
  return <div className={styles.reader} data-article-status="not-found"><RouteReady /><ReaderHeader title="" /><div className={styles.unavailable}><h1>这里没有内容</h1><p>这篇内容不存在，或已不再公开。</p><ReaderBack /></div></div>;
}
