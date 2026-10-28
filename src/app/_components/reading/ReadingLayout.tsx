// Adapted from AIHOT components/ui/Page.tsx (MIT); see THIRD_PARTY_NOTICES.md.
import type { ReactNode } from "react";
import styles from "./reading.module.css";

export function ReadingLayout({ children, aside, className = "" }: { children: ReactNode; aside?: ReactNode; className?: string }) {
  return <div className={`${styles.page} ${className}`}><div className={styles.layout}><div className={styles.main}>{children}</div>{aside && <aside className={styles.aside}>{aside}</aside>}</div></div>;
}

export function ReadingAsideCard({ title, children, className = "" }: { title: string; children: ReactNode; className?: string }) {
  return <section className={`${styles.card} ${className}`}><h2>{title}</h2><div className={styles.cardBody}>{children}</div></section>;
}
