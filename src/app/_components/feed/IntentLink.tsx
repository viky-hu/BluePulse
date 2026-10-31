"use client";
// AIHOT components/ui/IntentLink.tsx (MIT): hover/focus/stationary-touch intent.
// Copyright (c) 2026 数字生命卡兹克. Framework calls adapted to Next.js.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, type ComponentProps } from "react";
import { prefetchRouteData } from "../home/route-data-cache";

export function IntentLink({ keepScroll = false, onFocus, onBlur, onMouseEnter, onMouseLeave, onTouchStart, onTouchMove, onTouchEnd, onTouchCancel, ...props }: ComponentProps<typeof Link> & { keepScroll?: boolean }) {
  const router = useRouter();
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const href = String(props.href);
  const clear = () => { if (timer.current !== null) clearTimeout(timer.current); timer.current = null; };
  const start = () => {
    clear();
    timer.current = setTimeout(() => {
      timer.current = null;
      if (`${location.pathname}${location.search}` === href) return;
      router.prefetch(href);
      void prefetchRouteData(href).catch(() => {});
    }, 100);
  };
  useEffect(() => { clear(); return clear; }, [href]);
  return <Link {...props} prefetch={false} data-pulse-scroll={keepScroll ? "preserve" : undefined}
    onFocus={event => { onFocus?.(event); if (!event.defaultPrevented) start(); }}
    onBlur={event => { onBlur?.(event); clear(); }}
    onMouseEnter={event => { onMouseEnter?.(event); if (!event.defaultPrevented) start(); }}
    onMouseLeave={event => { onMouseLeave?.(event); clear(); }}
    onTouchStart={event => { onTouchStart?.(event); if (!event.defaultPrevented) start(); }}
    onTouchMove={event => { onTouchMove?.(event); clear(); }}
    onTouchEnd={event => { onTouchEnd?.(event); clear(); }}
    onTouchCancel={event => { onTouchCancel?.(event); clear(); }} />;
}
