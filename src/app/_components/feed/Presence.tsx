"use client";
// Ported from AIHOT (MIT). Copyright (c) 2026 数字生命卡兹克.
// See THIRD_PARTY_NOTICES.md.
/* eslint-disable react-hooks/refs -- source Presence retains the previous child only for its exit animation; this ref intentionally never drives updates */
/* eslint-disable react-hooks/set-state-in-effect -- show changes begin/finish the source CSS presence lifecycle */
// Enter and leave animations with CSS keyframes instead of an animation library (about 35 KB of
// compressed JavaScript on every page). An element mounts with its entrance class; when it goes away
// it stays mounted with its exit class for `duration`, then unmounts. Reduced motion is handled by the
// global rule in app.css. Content present at the first render never animates in.
import { cloneElement, useEffect, useRef, useState, type CSSProperties, type ReactElement, type ReactNode } from "react";

import styles from "./overlays.module.css";

type Animatable = ReactElement<{ className?: string; style?: CSSProperties }>;

export function Presence({ show, children, enter, exit, duration }: {
  show: boolean;
  /** One element; it receives the animation class. */
  children: Animatable;
  enter: string;
  exit: string;
  /** Milliseconds the exit class plays before the element unmounts. */
  duration: number;
}) {
  const [phase, setPhase] = useState<"still" | "in" | "out" | "gone">(show ? "still" : "gone");
  const last = useRef<Animatable>(children);
  if (show) last.current = children;
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    if (show) {
      setPhase("in");
      return;
    }
    setPhase((p) => (p === "gone" ? p : "out"));
    const timer = setTimeout(() => setPhase((p) => (p === "out" ? "gone" : p)), duration);
    return () => clearTimeout(timer);
  }, [show, duration]);
  if (!show && phase === "gone") return null;
  const child = show ? children : last.current;
  const cls = !show ? exit : phase === "in" ? enter : "";
  return cloneElement(child, { className: `${child.props.className ?? ""} ${cls}`.trim() });
}

/**
 * A block that opens to its natural height and closes to nothing (grid rows 0fr ↔ 1fr). Only the height
 * is clipped, so rows inside may still reach past its sides (phone rows run to the screen's edges).
 */
export function Collapse({ open, children, duration = 240, className = "" }: { open: boolean; children: ReactNode; duration?: number; className?: string }) {
  return (
    <Presence show={open} enter={styles.collapseIn} exit={styles.collapseOut} duration={duration}>
      <div className={`${styles.collapse} ${className}`} style={{ "--anim-ms": `${duration}ms` } as CSSProperties}>
        <div className={styles.collapseBody}>{children}</div>
      </div>
    </Presence>
  );
}
