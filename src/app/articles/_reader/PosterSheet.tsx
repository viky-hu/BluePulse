"use client";
// AIHOT PosterSheet (MIT). Copyright (c) 2026 数字生命卡兹克.
/* eslint-disable @next/next/no-img-element -- server-produced image is downloaded and shared unchanged */
import { useEffect, useState } from "react";
import { Sheet } from "../../_components/feed/Sheet";
import { IconDownload, IconShare } from "../../_components/feed/icons";
import styles from "./reader.module.css";

export default function PosterSheet({ id, title, open, onClose, mock }: { id: string; title: string; open: boolean; onClose: () => void; mock: boolean }) {
  const src = `/api/bluepulse/articles/${id}/poster.png`;
  const [loaded, setLoaded] = useState(false), [failed, setFailed] = useState(mock), [canShareFile, setCanShareFile] = useState(false);
  useEffect(() => {
    if (!open) return;
    try {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- browser capability is available only after the sheet opens
      setCanShareFile(!!navigator.canShare?.({ files: [new File([], "p.png", { type: "image/png" })] }));
    } catch { setCanShareFile(false); }
  }, [open]);
  async function share() {
    try {
      const response = await fetch(src, { cache: "no-store" });
      if (!response.ok || !response.headers.get("content-type")?.startsWith("image/png")) return;
      const blob = await response.blob();
      await navigator.share({ files: [new File([blob], `pulse-${id}.png`, { type: "image/png" })], title });
    } catch { /* cancelled: saving remains available */ }
  }
  return <Sheet open={open} onClose={onClose} title="分享海报" centered><div className={styles.poster}>
    <div className={styles.posterImage}>
      {!loaded && !failed && <div className={styles.posterLoading} aria-hidden="true" />}
      {failed ? <p role="status">海报生成失败，请稍后再试。</p> : <img src={src} alt={`${title} · 分享海报`} data-loaded={loaded} onLoad={() => setLoaded(true)} onError={() => setFailed(true)} />}
    </div>
    <p className={styles.posterHint}>长按图片可保存或发送给朋友</p>
    <div className={styles.posterActions}><a href={mock ? undefined : src} download={`pulse-${id}.png`} aria-disabled={!loaded || failed} onClick={event => { if (!loaded || failed) event.preventDefault(); }}><IconDownload size={15} />保存图片</a>
      {canShareFile && <button type="button" onClick={() => void share()} disabled={!loaded || failed}><IconShare size={15} />分享</button>}
    </div>
  </div></Sheet>;
}
