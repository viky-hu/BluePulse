"use client";
// Adapted from AIHOT routes/agent.tsx (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import { useEffect, useState, type KeyboardEvent, type MouseEvent } from 'react';
import { useSearchParams } from 'next/navigation';
import { RouteReady, useMainShell } from '../_components/home/MainShell';
import { ReadingAsideCard, ReadingLayout } from '../_components/reading/ReadingLayout';
import { IconArrowUpRight, IconChevronRight, IconCopy, IconList } from '../_components/feed/icons';
import { AGENT_PATH, ANCHORS, isAgentList, LATEST_PATH, SEARCH_PATH, tabHref, tabKey, type AgentTab } from './_contract';
import { ApiPanel, GuidePanel } from './panels';
import { Address } from './parts';
import styles from './agent.module.css';

const TRACKS = [
  { key: 'guide' as const, name: '给 Agent 使用', pitch: '读一份说明，开始查询', fit: '具备联网或命令行权限的 Codex 等客户端', Icon: IconList },
  { key: 'api' as const, name: 'JSON API', pitch: '匿名 GET，自己写程序取数', fit: '脚本、机器人、小程序、看板', Icon: IconCopy },
];

function useHttpStatus(origin: string | null, revision: number) {
  const [status, setStatus] = useState('正在检查 HTTP 入口');
  useEffect(() => {
    if (!origin) return;
    const controller = new AbortController();
    const check = async (path: string) => {
      const response = await fetch(path, { cache: 'no-store', signal: AbortSignal.any([controller.signal, AbortSignal.timeout(12_000)]) });
      if (!response.ok) return { ok: false, code: response.status, originMissing: response.status === 503 && (await response.json().catch(() => null))?.error?.code === 'agent_origin_unconfigured' };
      const type = response.headers.get('content-type') ?? '';
      const ok = path === AGENT_PATH ? type.includes('text/markdown') && (await response.text()).startsWith('# BluePulse Agent') : type.includes('application/json') && isAgentList(await response.json(), path === LATEST_PATH ? 'latest' : 'search');
      return {ok, code: response.status, originMissing: false};
    };
    void Promise.allSettled([AGENT_PATH, LATEST_PATH, SEARCH_PATH].map(check)).then(results => {
      if (controller.signal.aborted) return;
      if (results.every(result => result.status === 'fulfilled' && result.value.ok)) setStatus('HTTP 入口可响应');
      else if (results.some(result => result.status === 'fulfilled' && result.value.originMissing)) setStatus('后端接入地址尚未配置');
      else setStatus('HTTP 入口暂不可用');
    });
    return () => controller.abort();
  }, [origin, revision]);
  return origin ? status : '接入地址尚未配置';
}

export function AgentPage({ origin }: { origin: string | null }) {
  const params = useSearchParams(), tab = tabKey(params.get('tab'));
  const { navigate, active, refreshRevision } = useMainShell();
  const status = useHttpStatus(origin, refreshRevision);
  const select = (key: AgentTab) => { if (key !== tab) navigate(tabHref(key), { preserveScroll: true }); };
  const click = (event: MouseEvent<HTMLAnchorElement>, key: AgentTab) => {
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault(); select(key);
  };
  const keydown = (event: KeyboardEvent<HTMLAnchorElement>, index: number) => {
    if (event.key === ' ') { event.preventDefault(); select(TRACKS[index].key); return; }
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? TRACKS.length - 1 : event.key === 'ArrowRight' ? (index + 1) % TRACKS.length : event.key === 'ArrowLeft' ? (index + TRACKS.length - 1) % TRACKS.length : null;
    if (next === null) return;
    event.preventDefault(); document.getElementById(`agent-tab-${TRACKS[next].key}`)?.focus({ preventScroll: true }); select(TRACKS[next].key);
  };
  useEffect(() => {
    let frame = 0;
    const openHash = () => {
      const id = window.location.hash.slice(1), target = ANCHORS[id];
      if (!target) return;
      if (target !== tab) { navigate(`${tabHref(target)}#${id}`, { replace: true, preserveScroll: true }); return; }
      if (active) frame = requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({block: 'start'}));
    };
    openHash(); window.addEventListener('hashchange', openHash);
    return () => { cancelAnimationFrame(frame); window.removeEventListener('hashchange', openHash); };
  }, [tab, active, navigate]);

  const aside = <>
    <ReadingAsideCard title="接入方式" className={styles.waysAside}><nav aria-label="接入方式">{TRACKS.map(t => <a key={t.key} href={tabHref(t.key)} data-pulse-scroll="preserve" aria-current={tab === t.key ? 'true' : undefined} onClick={e => click(e, t.key)} className={styles.asideWay}><t.Icon size={16} />{t.name}{tab === t.key && <span className={styles.currentDot} />}</a>)}</nav></ReadingAsideCard>
    <ReadingAsideCard title="接入资源"><nav aria-label="接入资源">
      {origin ? <a href={`${origin}${AGENT_PATH}`} className={styles.resource}><span>Agent 使用说明<small>给 Agent 读的 Markdown 接入说明</small></span><IconArrowUpRight size={13} /></a> : <p>接入地址尚未配置。</p>}
      <a href="/agent?tab=api#agent-api-reference" className={styles.resource}><span>JSON API 参数与字段<small>本站当前 HTTP 接口契约</small></span><IconArrowUpRight size={13} /></a>
    </nav></ReadingAsideCard>
    <ReadingAsideCard title="没接上？"><p>把平台、版本和报错写在反馈页，别发 token 或本地文件。</p><a className={styles.feedback} href="/feedback">去反馈 <IconChevronRight size={14} /></a></ReadingAsideCard>
  </>;
  return <div className={styles.page}><RouteReady /><ReadingLayout aside={aside}>
    <header className={styles.header}><div className={styles.kicker}>AGENT 接入</div><h1 data-page-title>把 Pulse 接进你的 Agent</h1><p className={styles.lead}>读一份说明，或通过 JSON API，查询同一份公开警务科技资讯：近期资讯与关键词搜索。全部匿名只读，不用注册，也不用 API Key。</p>
      <div className={styles.entryAddress}><span>Agent 使用说明 · Markdown</span>{origin ? <Address url={`${origin}${AGENT_PATH}`} /> : <p className={styles.unconfigured}>接入地址尚未配置，暂不能提供可复制的请求。</p>}</div>
      <div className={styles.chips}><span className={styles.chip} role="status"><span className={styles.statusDot} />{status}</span><span className={styles.chip}>HTTP API v1</span><span className={styles.chip}>匿名只读 · 无需 Key</span></div>
      <p className={styles.statusNote}>检查当前浏览器到说明、近期资讯与搜索三个 HTTP 入口的响应，不代表客户端已经接通或查询到了新闻。</p>
    </header>
    <div role="tablist" aria-label="接入方式" className={styles.tracks}>{TRACKS.map((t, i) => <a key={t.key} id={`agent-tab-${t.key}`} href={tabHref(t.key)} data-pulse-scroll="preserve" role="tab" tabIndex={tab === t.key ? 0 : -1} aria-selected={tab === t.key} aria-controls="agent-panel" className={styles.track} onClick={e => click(e, t.key)} onKeyDown={e => keydown(e, i)}><span className={styles.trackIcon}><t.Icon size={18} /></span><strong>{t.name}</strong><span>{t.pitch}</span><small>{t.fit}</small></a>)}</div>
    <section id="agent-panel" role="tabpanel" aria-labelledby={`agent-tab-${tab}`} className={styles.panel}>{tab === 'guide' ? <GuidePanel origin={origin} /> : <ApiPanel origin={origin} />}</section>
  </ReadingLayout></div>;
}
