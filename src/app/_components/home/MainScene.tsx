"use client";

import { useRef, type RefObject } from "react";
import { useGSAP } from "@gsap/react";
import { gsap } from "gsap";
import { calculateWhitePaperLayout, getWhitePaperStapleGeometry } from "../intro/white-paper-config";
import introStyles from "../intro/intro.module.css";
import styles from "./main-shell.module.css";

gsap.registerPlugin(useGSAP);
const INITIAL_STAPLE = getWhitePaperStapleGeometry(180);

export type MainSceneRefs = {
  green: RefObject<SVGSVGElement | null>;
  paper: RefObject<SVGSVGElement | null>;
};

/** Endpoint geometry is viewport-relative CSS, including the very first SSR frame. */
export function MainScene({ greenRef, paperRef }: { greenRef: MainSceneRefs["green"]; paperRef: MainSceneRefs["paper"] }) {
  const staple = useRef<SVGSVGElement>(null), stapleLine = useRef<SVGLineElement>(null);
  useGSAP((_context, contextSafe) => {
    const sync = () => {
      const viewport = window.visualViewport;
      const width = Math.round(viewport?.width ?? window.innerWidth);
      const height = Math.round(viewport?.height ?? window.innerHeight);
      // Use the cover's p0 width, rather than stretching the mark with the main paper.
      const p0 = calculateWhitePaperLayout(width, height).papers[0];
      gsap.set(stapleLine.current, { attr: getWhitePaperStapleGeometry(p0.width) });
    };
    const onResize = contextSafe ? contextSafe(sync) : sync;
    onResize();
    window.addEventListener("resize", onResize, { passive: true });
    window.visualViewport?.addEventListener("resize", onResize, { passive: true });
    return () => {
      window.removeEventListener("resize", onResize);
      window.visualViewport?.removeEventListener("resize", onResize);
    };
  }, { scope: staple });

  return <div className={styles.scene} aria-hidden="true" data-main-scene>
    <svg ref={greenRef} className={styles.green} viewBox="0 0 1 1" preserveAspectRatio="none" data-main-green><rect width="1" height="1" /></svg>
    <svg ref={paperRef} className={styles.paper} viewBox="0 0 1 1" preserveAspectRatio="none" data-main-paper><rect width="1" height="1" /></svg>
    <svg ref={staple} className={`${styles.paperStaple} ${introStyles.paperStaple}`} viewBox="0 0 50 50" data-main-paper-staple>
      <line ref={stapleLine} {...INITIAL_STAPLE} />
    </svg>
  </div>;
}
