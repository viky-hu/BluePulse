// AIHOT components/ui/Badge.tsx (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import type { ReactNode } from "react";
import styles from "./feed.module.css";
type Tone = "selected" | "accent" | "amber" | "hot" | "ok" | "neutral";
export function Badge({ tone = "neutral", dot = false, children, className = "", title }: { tone?: Tone; dot?: boolean; children: ReactNode; className?: string; title?: string }) {
  return <span title={title} data-tone={tone} className={`${styles.badge} ${className}`}>{dot && <span className={styles.badgeDot} aria-hidden="true" />}{children}</span>;
}
export function SelectedBadge() { return <Badge tone="selected" dot>精选</Badge>; }
export function SameEventBadge() { return <Badge title="同一新闻已有精选代表">同新闻</Badge>; }
