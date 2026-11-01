import type { RefObject } from "react";
import styles from "./main-shell.module.css";

export type MainSceneRefs = {
  green: RefObject<SVGSVGElement | null>;
  paper: RefObject<SVGSVGElement | null>;
};

/** Endpoint geometry is viewport-relative CSS, including the very first SSR frame. */
export function MainScene({ greenRef, paperRef }: { greenRef: MainSceneRefs["green"]; paperRef: MainSceneRefs["paper"] }) {
  return <div className={styles.scene} aria-hidden="true" data-main-scene>
    <svg ref={greenRef} className={styles.green} viewBox="0 0 1 1" preserveAspectRatio="none" data-main-green><rect width="1" height="1" /></svg>
    <svg ref={paperRef} className={styles.paper} viewBox="0 0 1 1" preserveAspectRatio="none" data-main-paper><rect width="1" height="1" /></svg>
  </div>;
}
