import styles from "./intro.module.css";

interface ScrollCueButtonProps {
  disabled: boolean;
  onActivate: () => void;
}

export function ScrollCueButton({ disabled, onActivate }: ScrollCueButtonProps) {
  return (
    <button
      className={styles.scrollCue}
      type="button"
      disabled={disabled}
      onClick={onActivate}
      aria-label="进入 Blue Pulse"
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
