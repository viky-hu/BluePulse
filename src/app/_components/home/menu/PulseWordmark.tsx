import styles from "./sidebar.module.css";

/** Pulse's wordmark uses AIHOT's compact dot-and-type composition, with the local UI font. */
export function PulseWordmark() {
  return <span className={styles.wordmark} aria-hidden="true"><span className={styles.brandDot} /><span>Pulse</span></span>;
}
