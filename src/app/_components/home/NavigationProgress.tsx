"use client";

// Adapted from AIHOT components/shell/Chrome.tsx (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import { useEffect, useState } from "react";
import styles from "./navigation-progress.module.css";

export function NavigationProgress({ active }: { active: boolean }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    // Defer the reset as well, preserving the completion transition without a synchronous effect update.
    const timer = setTimeout(() => setVisible(active), active ? 150 : 0);
    return () => clearTimeout(timer);
  }, [active]);
  return <>
    <div className={styles.progress} data-navigation-progress data-active={active} data-visible={visible} aria-hidden="true">
      <div className={styles.line} style={{ transform: `scaleX(${visible ? 0.85 : active ? 0 : 1})`, opacity: visible ? 1 : 0,
        transition: visible ? "transform 2.4s cubic-bezier(0.1, 0.7, 0.2, 1), opacity 120ms" : "transform 200ms, opacity 300ms 120ms" }} />
    </div>
    <span className={styles.srOnly} role="status" aria-live="polite">{visible && active ? "正在载入内容…" : ""}</span>
  </>;
}
