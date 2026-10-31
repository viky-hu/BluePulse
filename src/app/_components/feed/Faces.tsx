"use client";
// AIHOT features/hot/Faces.tsx (MIT). Copyright (c) 2026 数字生命卡兹克.
// See THIRD_PARTY_NOTICES.md.
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { HotParticipant } from "../../_lib/feed-types";
import styles from "./feed.module.css";
const HOT_FACE_LIMIT = 6;
import { SourceAvatar } from "./SourceAvatar";

/**
 * Who is talking about a hot story: overlapping faces of the 精选组 sources in the order the server
 * gives (T1, T1.5, T2), then a count for everyone else, 氛围组 included. Hover lists every name; where
 * the faces are their own control (not inside a link), a tap or Enter opens the list, so phones and
 * keyboards reach it too.
 */
export function Faces({ participants, total, size = 24, interactive = true }: { participants: HotParticipant[]; total: number; size?: number; interactive?: boolean }) {
  const shown = participants.filter((p) => p.kind === "editorial").slice(0, HOT_FACE_LIMIT);
  const rest = total - shown.length;
  const names = participants.map((p) => p.name).join("、");
  const faces = (
    <>
      {shown.map((p, i) => (
        <span key={p.name} className={styles.face} data-overlap={!!i}>
          <SourceAvatar name={p.name} iconUrl={p.iconUrl} iconSrcSet={p.iconSrcSet} size={size} />
        </span>
      ))}
      {rest > 0 && (
        <span className={styles.faceRest} style={{ height: size, minWidth: size }}>
          +{rest}
        </span>
      )}
    </>
  );
  if (!interactive) {
    return (
      <span className={styles.faces} title={names}>
        {faces}
      </span>
    );
  }
  return <FacesButton participants={participants} total={total} names={names}>{faces}</FacesButton>;
}

function FacesButton({ participants, total, names, children }: { participants: HotParticipant[]; total: number; names: string; children: React.ReactNode }) {
  // Where the list opens: under the faces, kept on screen; fixed, so a card's clipping never hides it.
  const [at, setAt] = useState<{ top: number; left: number } | null>(null);
  const open = at !== null;
  const root = useRef<HTMLSpanElement>(null);
  const popup = useRef<HTMLSpanElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const close = () => setAt(null);
    const onDown = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node) && !popup.current?.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", close, { passive: true, capture: true });
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [open]);
  const editorial = participants.filter((p) => p.kind === "editorial");
  const signal = participants.filter((p) => p.kind !== "editorial");
  const more = total - participants.length;
  return (
    <span ref={root} className={styles.faces}>
      <button
        type="button"
        title={names}
        aria-expanded={open}
        aria-controls={id}
        aria-label={`${total} 位参与者，查看名单`}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          if (open) return setAt(null);
          const r = e.currentTarget.getBoundingClientRect();
          const below = window.innerHeight - r.bottom > 240;
          setAt({ top: below ? r.bottom + 6 : Math.max(8, r.top - 6 - 240), left: Math.min(Math.max(8, r.left), document.documentElement.clientWidth - 248) });
        }}
        className={styles.facesButton}
      >
        {children}
      </button>
      {open && createPortal(
        <span ref={popup} id={id} role="dialog" aria-label="参与讨论的来源" style={at} className={styles.facesPopup}>
          {editorial.length > 0 && (
            <>
              <span className={styles.facesLabel}>精选组</span>
              <span className={styles.facesNames}>{editorial.map((p) => p.name).join("、")}</span>
            </>
          )}
          {signal.length > 0 && (
            <>
              <span className={styles.facesLabel}>氛围组</span>
              <span className={styles.facesNames}>{signal.map((p) => p.name).join("、")}</span>
            </>
          )}
          {more > 0 && <span className={styles.facesMore}>另有 {more} 位未列出</span>}
        </span>, document.body
      )}
    </span>
  );
}
