import Link from 'next/link';
import type { LocalStarredItem } from '../_lib/browser-state';
import type { Availability } from './availability';
import { StarredIcon } from './StarredIcon';
import styles from './starred.module.css';
const dateTime = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
export function fullDateTime(value: string) {
  const parts = Object.fromEntries(dateTime.formatToParts(new Date(value)).map(part => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
}
export function StarredCard({ item, current, href, remove }: { item: LocalStarredItem; current?: Availability; href: string; remove: () => void }) {
  const unavailable = current?.status === 'unavailable';
  return <li data-card-key={item.id} className={styles.card} data-unavailable={unavailable}>
    <div className={styles.metadata}>
      <span className={styles.source}>{current?.sourceName ?? item.sourceName}</span>
      {item.publishedAt && <time className={styles.published} dateTime={item.publishedAt}>· {fullDateTime(item.publishedAt)}</time>}
      <span className={styles.saved}>收藏于 <time dateTime={item.savedAt}>{fullDateTime(item.savedAt)}</time></span>
      <button type="button" className={styles.remove} aria-label="取消收藏" title="取消收藏" onClick={remove}><StarredIcon name="close" /></button>
    </div>
    <h2>{unavailable ? item.title : <Link href={href}>{item.title}</Link>}</h2>
    {item.summary && <p className={styles.summary}>{item.summary}</p>}
    {unavailable && <p className={styles.unavailable}>这条内容已不再公开，收藏会保留直到你手动移除。</p>}
    {current?.status === 'summary-only' && <p className={styles.permission}>应来源方要求，这条内容现在只提供摘要。</p>}
  </li>;
}
