"use client";
// AIHOT MediaGallery / QuotedPost (MIT). Copyright (c) 2026 数字生命卡兹克.
/* eslint-disable @next/next/no-img-element -- source-sized media and srcSet are supplied by the read API */
import { useState } from "react";
import type { MediaView } from "../../_lib/feed-types";
import { Lightbox } from "../../_components/feed/Lightbox";
import { IconArrowUpRight } from "../../_components/feed/icons";
import type { ReaderPost } from "./types";
import styles from "./reader.module.css";

export function MediaGallery({ media, postUrl }: { media: MediaView[]; postUrl: string }) {
  const [open, setOpen] = useState<number | null>(null), shown = media.slice(0, 9);
  const images = shown.filter(item => item.kind === "image"), single = shown.length === 1;
  return <><div className={styles.gallery} data-count={shown.length} data-single={single}>{shown.map(item => {
    const image = <img src={item.poster ?? item.url} srcSet={item.srcSet} sizes="auto, 100vw" width={item.width ?? undefined} height={item.height ?? undefined} decoding="async" alt={item.alt ?? ""} loading="lazy" style={single && item.width && item.height ? { aspectRatio: `${item.width}/${item.height}` } : undefined} />;
    return item.kind === "video" ? <a key={item.url} href={postUrl} target="_blank" rel="noopener noreferrer" className={styles.galleryTile} aria-label="打开原推播放视频">{image}<span className={styles.playMark} aria-hidden="true"><span><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M7 4.5v15a1 1 0 001.5.87l13-7.5a1 1 0 000-1.74l-13-7.5A1 1 0 007 4.5z" /></svg></span></span></a>
      : <button key={item.url} type="button" className={styles.galleryTile} onClick={() => setOpen(images.indexOf(item))} aria-label={item.alt ? `查看大图：${item.alt}` : "查看大图"}>{image}</button>;
  })}</div><Lightbox images={images.map(item => ({ src: item.fullUrl ?? item.url, alt: item.alt }))} index={open} onIndex={setOpen} onClose={() => setOpen(null)} /></>;
}
export function QuotedPost({ quoted, original }: { quoted: NonNullable<ReaderPost["quoted"]>; original: boolean }) {
  const zh = original ? null : quoted.translation;
  return <figure className={styles.quoted}><figcaption><span>引用</span><strong>{quoted.authorName || `@${quoted.handle}`}</strong>{quoted.authorName && quoted.handle && <span>@{quoted.handle}</span>}</figcaption><blockquote>{zh ?? quoted.text}</blockquote>
    {zh && <details><summary>原文</summary><p>{quoted.text}</p></details>}
    {quoted.url && <a href={quoted.url} target="_blank" rel="noopener noreferrer">在 X 查看被引用的帖子 <IconArrowUpRight size={13} /></a>}
  </figure>;
}
