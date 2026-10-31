// AIHOT routes/hot.tsx method disclosure (MIT). Copyright (c) 2026 数字生命卡兹克.
import { Badge } from "../_components/feed/Badge";
import { BADGES } from "./HotCards";
import styles from "./hot.module.css";
export function InfoIcon({ size = 15 }: { size?: number }) { return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="8.5" /><path d="M12 11v5M12 8h.01" /></svg>; }
export function HotMethod() {
  return <details id="hot-method" className={styles.method}>
    <summary><InfoIcon />热度是怎么算的？<span className={styles.methodToggle}><span className={styles.whenClosed}>了解榜单</span><span className={styles.whenOpen}>收起</span><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg></span></summary>
    <div className={styles.methodBody}>
      <p>热度来自参与同一事件的独立账号与机构，重复采集只算一次，并按 24 小时半衰期衰减。它衡量讨论活跃程度，不是报道质量评分。</p>
      <p>榜单统计过去 48 小时。趋势只比较持续覆盖的同一组信源；它反映我们的监测范围，不代表全网人数。缺少可比历史时，不展示趋势线。</p>
      <p>信源名单只展示可公开阅读的报道来源；讨论参与者还包括只计入热度的账号与机构。同一机构的多个渠道可能合并计数，因此参与者不一定多于信源数。点击事件可查看各方报道与观点。</p>
      <dl>{Object.values(BADGES).map(b => <div key={b.label}><dt><Badge tone={b.tone}>{b.label}</Badge></dt><dd>{b.hint}</dd></div>)}</dl>
    </div>
  </details>;
}
