"use client";
// Adapted from AIHOT features/agent/CodeBlock.tsx (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import { useEffect, useRef, useState } from 'react';
import { IconCopy } from '../_components/feed/icons';
import styles from './agent.module.css';

export function CopyButton({ text, label = '复制' }: { text: string; label?: string }) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle');
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const alive = useRef(true), busy = useRef(false);
  useEffect(() => { alive.current = true; return () => { alive.current = false; if (timer.current) clearTimeout(timer.current); }; }, []);
  return <span className={styles.copyControl}>
    <button type="button" className={styles.copy} onClick={async () => {
      if (busy.current) return;
      busy.current = true;
      if (timer.current) clearTimeout(timer.current);
      try { await navigator.clipboard.writeText(text); if (alive.current) setState('copied'); }
      catch { if (alive.current) setState('failed'); }
      finally { busy.current = false; }
      if (alive.current) timer.current = setTimeout(() => setState('idle'), 2500);
    }}><IconCopy size={14} /><span>{state === 'copied' ? '已复制' : label}</span></button>
    <span role="status" className={state === 'failed' ? styles.copyFailure : styles.srOnly}>{state === 'copied' ? '已复制到剪贴板' : state === 'failed' ? '复制失败，请选择文本手动复制。' : ''}</span>
  </span>;
}

export function CodeBlock({ code, title, lang = 'bash', wrap = false }: { code: string; title?: string; lang?: string; wrap?: boolean }) {
  return <div className={styles.codeBlock}><div className={styles.codeHead}><span>{title ?? lang}</span><CopyButton text={code} /></div><pre tabIndex={0} className={wrap ? styles.wrap : undefined}><code>{code}</code></pre></div>;
}
