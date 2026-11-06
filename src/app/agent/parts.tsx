// Adapted from AIHOT features/agent/parts.tsx (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import type { ReactNode } from 'react';
import { IconChevronDown } from '../_components/feed/icons';
import { CopyButton } from './CodeBlock';
import styles from './agent.module.css';

export function PanelHead({ label, title, children }: { label: string; title: string; children?: ReactNode }) {
  return <header className={styles.panelHead}><div className={styles.panelLabel}>{label}</div><h2>{title}</h2>{children && <p>{children}</p>}</header>;
}
export function Steps({ children }: { children: ReactNode }) { return <ol className={styles.steps}>{children}</ol>; }
export function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return <li><span className={styles.stepNumber}>{n}</span><div className={styles.stepBody}><h3>{title}</h3><div>{children}</div></div></li>;
}
export function Block({ title, id, children }: { title: string; id?: string; children: ReactNode }) {
  return <section id={id} className={styles.block}><h3>{title}</h3><div>{children}</div></section>;
}
export function Ask({ text }: { text: string }) { return <div className={styles.ask}><span>{text}</span><CopyButton text={text} /></div>; }
export function Address({ url }: { url: string }) { return <div className={styles.address}><code>{url}</code><CopyButton text={url} label="复制地址" /></div>; }
export function Tips({ items }: { items: {title: string; text: ReactNode}[] }) {
  return <ol className={styles.tips}>{items.map((item, i) => <li key={item.title}><div className={styles.tipNumber}>0{i + 1}</div><h4>{item.title}</h4><p>{item.text}</p></li>)}</ol>;
}
export function Details({ items }: { items: {title: string; body: ReactNode}[] }) {
  return <div className={styles.details}>{items.map(item => <details key={item.title}><summary>{item.title}<IconChevronDown size={16} /></summary><div>{item.body}</div></details>)}</div>;
}
export function Bullets({ items }: { items: ReactNode[] }) { return <ul className={styles.bullets}>{items.map((item, i) => <li key={i}>{item}</li>)}</ul>; }
export function Mono({ children }: { children: ReactNode }) { return <code className={styles.mono}>{children}</code>; }
export function Table({ head, rows, minWidth = 560 }: { head: string[]; rows: (ReactNode[] | {group: string})[]; minWidth?: number }) {
  return <div className={styles.tableScroll} tabIndex={0} role="region" aria-label={head.join('、')}><table style={{ minWidth }}><thead><tr>{head.map(h => <th key={h} scope="col">{h}</th>)}</tr></thead><tbody>{rows.map((row, i) => 'group' in row ? <tr key={i} className={styles.tableGroup}><th colSpan={head.length} scope="colgroup">{row.group}</th></tr> : <tr key={i}>{row.map((cell, j) => <td key={j}>{cell}</td>)}</tr>)}</tbody></table></div>;
}
