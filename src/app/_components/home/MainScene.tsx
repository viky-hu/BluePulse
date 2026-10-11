import styles from "./main-shell.module.css";

/** Endpoint geometry is viewport-relative CSS, including the very first SSR frame. */
export function MainScene() {
  return <div className={styles.scene} aria-hidden="true" data-main-scene>
    <svg className={styles.green} viewBox="0 0 1 1" preserveAspectRatio="none" data-main-green><rect width="1" height="1" /></svg>
    <svg className={styles.paper} viewBox="0 0 1 1" preserveAspectRatio="none" data-main-paper><rect width="1" height="1" /></svg>
  </div>;
}
