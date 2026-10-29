"use client";
// Adapted from AIHOT routes/starred.tsx and Presence.tsx (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useBrowserState } from '../_lib/use-browser-state';
import { RouteReady, useMainShell } from '../_components/home/MainShell';
import { StarredCard } from './StarredCard';
import { StarredIcon } from './StarredIcon';
import { useAvailability } from './use-availability';
import styles from './starred.module.css';
type Report = { starredAdded: number; starredSkipped: number; readAdded: number; readSkipped: number; readFailed: boolean };
function reportText(report: Report) {
  const parts = [`新增收藏 ${report.starredAdded} 条`, `已读记录 ${report.readAdded} 条`];
  if (report.starredSkipped || report.readSkipped) parts.push(`超出上限或格式不对而跳过 ${report.starredSkipped + report.readSkipped} 条`);
  if (report.readFailed) parts.push('已读记录没能保存（浏览器存储已满或不可用）');
  return parts.join('，');
}
export default function StarredPage() {
  const shell = useMainShell();
  const { state, store } = useBrowserState(shell.mock);
  const availability = useAvailability(state.starred.map(item => item.id), state.ready, shell.mock, shell.refreshRevision);
  const [notice, setNotice] = useState<{ kind: 'ok' | 'error'; text: string; closing?: boolean } | null>(null);
  const [importing, setImporting] = useState(false);
  const importLock = useRef(false);
  const mounted = useRef(true);
  const fileRef = useRef<HTMLInputElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const exportUrls = useRef(new Set<string>());
  useEffect(() => {
    mounted.current = true;
    const urls = exportUrls.current;
    return () => { mounted.current = false; if (closeTimer.current) clearTimeout(closeTimer.current); for (const url of urls) URL.revokeObjectURL(url); urls.clear(); };
  }, []);
  function showNotice(value: { kind: 'ok' | 'error'; text: string }) {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    setNotice(value);
  }
  function closeNotice() {
    setNotice(value => value ? { ...value, closing: true } : null);
    closeTimer.current = setTimeout(() => setNotice(null), 160);
  }
  function doExport() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(store.exportBundle(), null, 2)], { type: 'application/json' }));
    exportUrls.current.add(url);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `pulse-local-data-${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click();
    setTimeout(() => { URL.revokeObjectURL(url); exportUrls.current.delete(url); }, 0);
  }
  async function doImport(file: File | undefined) {
    if (!file || importLock.current) return;
    importLock.current = true;
    setImporting(true);
    try {
      if (file.size > 8_000_000) throw Error('文件过大（上限 2,000,000 字符）');
      const text = await file.text();
      if (!mounted.current) return;
      const report = store.importBundle(text);
      showNotice({ kind: report.readFailed ? 'error' : 'ok', text: `导入完成：${reportText(report)}` });
    } catch (error) { if (mounted.current) showNotice({ kind: 'error', text: error instanceof Error ? error.message : '导入失败' }); }
    finally { importLock.current = false; if (mounted.current) setImporting(false); if (fileRef.current) fileRef.current.value = ''; }
  }
  return <section className={styles.page}>
    <RouteReady ready={state.ready} />
    <header className={styles.header}>
      <div><h1 data-page-title="">收藏</h1><p>本机收藏的 Pulse 内容，适合稍后阅读和回看。</p></div>
      <div className={styles.tools}>
        <button type="button" disabled={!state.ready || importing} onClick={() => fileRef.current?.click()}>{importing ? '正在导入…' : '导入文件'}</button>
        {state.ready && state.starred.length > 0 && <button type="button" onClick={doExport}><StarredIcon name="download" size={13} /> 导出</button>}
        <input ref={fileRef} aria-label="导入收藏文件" className={styles.srOnly} type="file" accept="application/json,.json" disabled={importing} onChange={event => void doImport(event.target.files?.[0])} />
      </div>
    </header>
    <p className={styles.localHint}>收藏只保存在当前浏览器；清除浏览器数据或换设备后不会同步。</p>
    {notice && <div role="status" className={styles.notice} data-kind={notice.kind} data-closing={notice.closing || undefined}><span>{notice.text}</span><button type="button" aria-label="关闭" onClick={closeNotice}><StarredIcon name="close" /></button></div>}
    {availability.error && <p role="status" className={styles.status}>暂时无法核对文章状态，已保留收藏；可稍后重新打开此页。</p>}
    {!state.ready ? null : state.starred.length === 0 ? <div className={styles.empty}>
      <StarredIcon name="bookmark" size={20} />
      <p>还没有收藏内容。点开任意一条内容，在详情页点击收藏即可添加。</p>
      <Link href={shell.href('/')}>去看精选 →</Link>
    </div> : <ul className={styles.list}>{state.starred.map(item => <StarredCard key={item.id} item={item} current={availability.items[item.id]} href={shell.href(`/articles/${item.id}`)} remove={() => store.removeStar(item.id)} />)}</ul>}
  </section>;
}
