"use client";
// AIHOT components/ui/SourceAvatar.tsx (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
/* eslint-disable @next/next/no-img-element -- source-sized media uses supplied URL/srcSet without an image proxy */
import { useState } from "react";
import styles from "./feed.module.css";

export function SourceAvatar({ name, iconUrl, avatarUrl, iconSrcSet, avatarSrcSet, size = 18 }: { name: string; iconUrl?: string | null; avatarUrl?: string | null; iconSrcSet?: string; avatarSrcSet?: string; size?: number }) {
  const [failed, setFailed] = useState<string | null>(null);
  const src = avatarUrl ?? iconUrl;
  if (src && failed !== src) return <img src={src} srcSet={avatarUrl ? avatarSrcSet : iconSrcSet} sizes={`${size}px`} decoding="async" alt="" width={size} height={size} loading="lazy" onError={() => setFailed(src)} className={styles.avatar} style={{ width: size, height: size }} />;
  let hue = 0;
  for (const char of name) hue = (hue * 31 + char.charCodeAt(0)) % 360;
  const initial = (name.replace(/^[^\p{L}\p{N}]+/u, "")[0] ?? "A").toUpperCase();
  return <span aria-hidden="true" className={styles.avatarInitial} style={{ width: size, height: size, fontSize: Math.max(9, Math.round(size * .5)), background: `oklch(0.6 0.07 ${hue})` }}>{initial}</span>;
}
