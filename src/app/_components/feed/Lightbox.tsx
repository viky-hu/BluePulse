"use client";
// Ported from AIHOT (MIT). Copyright (c) 2026 数字生命卡兹克.
// See THIRD_PARTY_NOTICES.md.
/* eslint-disable @next/next/no-img-element -- source-sized media uses its supplied URL/srcSet without an image proxy */
import { useLayoutEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { Presence } from "./Presence";
import { useModal } from "./modal";
import { IconArrowLeft, IconArrowRight, IconClose } from "./icons";

import styles from "./overlays.module.css";

export interface LightboxImage {
  src: string;
  alt?: string | null;
}

/**
 * Pictures shown full size over the page. While open, keyboard focus stays in the viewer (Tab moves
 * between its buttons), the page behind does not scroll, Escape closes it and the arrow keys move
 * between pictures; closing puts focus back where it was. On touch screens a picture follows the finger:
 * sideways to the next or previous one, down to close; two fingers zoom as the browser does.
 */
export function Lightbox({ images, index, onIndex, onClose }: { images: LightboxImage[]; index: number | null; onIndex: (i: number) => void; onClose: () => void }) {
  const open = index !== null && !!images[index];
  const dialog = useRef<HTMLDivElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const state = useRef({ index, count: images.length, onIndex, onClose });
  useLayoutEffect(() => { state.current = { index, count: images.length, onIndex, onClose }; }, [index, images.length, onIndex, onClose]);

  useModal({
    open,
    panel: dialog,
    initialFocus: closeButton,
    onClose,
    onKeyDown: (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const { index: at, count, onIndex: go } = state.current;
      if (at !== null && count > 1) go((at + (e.key === "ArrowRight" ? 1 : -1) + count) % count);
      e.preventDefault();
    },
  });

  // Touch: follow one finger, then step, close or snap back. A drag is not also a tap that closes.
  const img = useRef<HTMLImageElement>(null);
  const drag = useRef<{ x: number; y: number; dx: number; dy: number; axis: "x" | "y" | null; moved: boolean } | null>(null);
  const suppressTap = useRef(false);
  const zoomed = () => (window.visualViewport?.scale ?? 1) > 1.01;
  const place = (dx: number, dy: number, animate: boolean) => {
    const el = img.current;
    const backdrop = dialog.current;
    if (!el || !backdrop) return;
    el.style.transition = animate && !window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "transform 220ms cubic-bezier(0.22, 1, 0.36, 1)" : "none";
    el.style.transform = dx || dy ? `translate(${dx}px, ${dy}px)` : "";
    backdrop.style.backgroundColor = dy > 0 ? `rgba(0, 0, 0, ${Math.max(0.3, 0.85 - dy / 600)})` : "";
  };
  const cancelDrag = () => {
    suppressTap.current = true;
    drag.current = null;
    place(0, 0, true);
  };
  const onTouchStart = (e: React.TouchEvent) => {
    if (e.touches.length !== 1 || zoomed()) return cancelDrag();
    suppressTap.current = false;
    drag.current = e.target instanceof Element && e.target.closest("button") ? null : { x: e.touches[0]!.clientX, y: e.touches[0]!.clientY, dx: 0, dy: 0, axis: null, moved: false };
  };
  const onTouchMove = (e: React.TouchEvent) => {
    if (e.touches.length !== 1 || zoomed()) return cancelDrag();
    const d = drag.current;
    if (!d) return;
    d.dx = e.touches[0]!.clientX - d.x;
    d.dy = e.touches[0]!.clientY - d.y;
    if (!d.axis && Math.hypot(d.dx, d.dy) > 8) d.axis = Math.abs(d.dx) > Math.abs(d.dy) ? "x" : "y";
    if (!d.axis) return;
    d.moved = true;
    if (d.axis === "x" && images.length > 1) place(d.dx, 0, false);
    else if (d.axis === "y") place(0, Math.max(0, d.dy), false);
  };
  const onTouchEnd = (e: React.TouchEvent) => {
    if (e.touches.length || zoomed()) return cancelDrag();
    const d = drag.current;
    if (!d?.moved) return;
    suppressTap.current = true;
    drag.current = null;
    const { index: at, count, onIndex: go, onClose: close } = state.current;
    if (d.axis === "x" && count > 1 && at !== null && Math.abs(d.dx) > 60) {
      place(0, 0, false);
      go((at + (d.dx < 0 ? 1 : -1) + count) % count);
    } else if (d.axis === "y" && d.dy > 110) {
      close();
    } else {
      place(0, 0, true);
    }
  };
  const tappedAfterDrag = () => {
    const moved = suppressTap.current;
    suppressTap.current = false;
    drag.current = null;
    return moved;
  };

  const current = open ? images[index!]! : null;
  const many = images.length > 1;
  const nav = styles.lightboxNav;
  if (typeof document === "undefined") return null;
  return createPortal(
    <Presence show={open} enter={styles.fadeIn} exit={styles.fadeOut} duration={160}>
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        aria-label={many && index !== null ? `图片 ${index + 1} / ${images.length}` : "图片"}
        onClick={() => {
          if (!tappedAfterDrag()) onClose();
        }}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        onTouchCancel={cancelDrag}
        className={styles.lightbox}
      >
        {current && (
          <img ref={img} key={current.src} src={current.src} decoding="async" alt={current.alt ?? ""} className={styles.lightboxImage} />
        )}
        <button ref={closeButton} type="button" aria-label="关闭" onClick={(e) => { e.stopPropagation(); onClose(); }} className={styles.lightboxClose}>
          <IconClose size={18} />
        </button>
        {many && index !== null && (
          <>
            <button type="button" aria-label="上一张" onClick={(e) => { e.stopPropagation(); onIndex((index - 1 + images.length) % images.length); }} className={`${nav} ${styles.lightboxPrevious}`}>
              <IconArrowLeft size={18} />
            </button>
            <button type="button" aria-label="下一张" onClick={(e) => { e.stopPropagation(); onIndex((index + 1) % images.length); }} className={`${nav} ${styles.lightboxNext}`}>
              <IconArrowRight size={18} />
            </button>
            <span className={styles.lightboxCount}>
              {index + 1} / {images.length}
            </span>
          </>
        )}
      </div>
    </Presence>, document.body
  );
}
