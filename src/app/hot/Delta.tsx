// AIHOT features/hot/Delta.tsx (MIT). Copyright (c) 2026 数字生命卡兹克.
// See THIRD_PARTY_NOTICES.md. Styles transcribed without changing the source branches.
import type { HotEntryView } from "./_types";
import styles from "./hot.module.css";
export function Delta({ trend, pct, className = "" }: { trend: HotEntryView["trend"]; pct: number | null; className?: string }) {
  const base = `${styles.delta} ${className}`;
  if (trend === "unknown") return <span className={`${base} ${styles.deltaQuiet}`} title="部分信源的采集暂时落后，先不和 6 小时前比较">暂不比较</span>;
  if (trend === "new" || pct === null) return <span className={`${base} ${styles.deltaNew}`}>新上榜</span>;
  if (trend === "flat") return <span className={`${base} ${styles.deltaQuiet}`} title="较 6 小时前">持平</span>;
  const up = trend === "up";
  return <span className={`${base} ${up ? styles.deltaUp : styles.deltaQuiet}`} title="较 6 小时前">{up ? "↑" : "↓"} {Math.abs(Math.round(pct))}%</span>;
}
