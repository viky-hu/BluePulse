"use client";
// Ported from AIHOT (MIT). Copyright (c) 2026 数字生命卡兹克.
// See THIRD_PARTY_NOTICES.md.
// Inline stroke icons (no icon-font or network requests).
import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 18, children, ...rest }: P & { children: React.ReactNode }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...rest}>
      {children}
    </svg>
  );
}

export const IconArrowLeft = (p: P) => (<Svg {...p}><path d="M19 12H5M11 18l-6-6 6-6" /></Svg>);
export const IconArrowRight = (p: P) => (<Svg {...p}><path d="M5 12h14M13 6l6 6-6 6" /></Svg>);
export const IconArrowUpRight = (p: P) => (<Svg {...p}><path d="M7 17L17 7M8 7h9v9" /></Svg>);
export const IconChevronDown = (p: P) => (<Svg {...p}><path d="M6 9l6 6 6-6" /></Svg>);
export const IconChevronRight = (p: P) => (<Svg {...p}><path d="M9 6l6 6-6 6" /></Svg>);
export const IconClose = (p: P) => (<Svg {...p}><path d="M6 6l12 12M18 6L6 18" /></Svg>);