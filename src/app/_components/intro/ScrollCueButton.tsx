import styles from "./intro.module.css";

export function ScrollCueButton() {
  return (
    <button
      className={styles.scrollCue}
      type="button"
      aria-label="继续浏览"
    >
      <span className={styles.arrowTrack} aria-hidden="true">
        <svg className={styles.arrow} viewBox="0 0 24 24">
          <path d="m6.5 9 5.5 5.5L17.5 9" />
        </svg>
        <svg className={styles.arrow} viewBox="0 0 24 24">
          <path d="m6.5 9 5.5 5.5L17.5 9" />
        </svg>
      </span>
    </button>
  );
}
