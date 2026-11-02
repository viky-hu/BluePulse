"use client";
// AIHOT StoryFollowups (MIT). Copyright (c) 2026 数字生命卡兹克.
import { useEffect, useRef, useState } from "react";
import { IntentLink } from "../../_components/feed/IntentLink";
import { useMainShell } from "../../_components/home/MainShell";
import type { StoryFollowup, StoryFollowupsResponse, StoryRef } from "./types";
import { relativeTime } from "./format";
import { readerScroller } from "./scroll";
import styles from "./reader.module.css";

export function StoryFollowups({ story, currentId }: { story: StoryRef; currentId: string }) {
  const { href, mock } = useMainShell(), anchor = useRef<HTMLDivElement>(null);
  const [data, setData] = useState<{ key: string; items: StoryFollowup[]; more: boolean } | null>(null);
  useEffect(() => {
    const controller = new AbortController(); let started = false;
    const load = () => {
      if (started || mock) return;
      started = true;
      void fetch(`/api/bluepulse/site/stories/${encodeURIComponent(story.publicId)}/followups`, { cache: "no-store", signal: AbortSignal.any([controller.signal, AbortSignal.timeout(12000)]) })
        .then(response => response.ok ? response.json() : null).then((body: StoryFollowupsResponse | null) => {
          if (controller.signal.aborted || !body || !Array.isArray(body.items) || typeof body.more !== "boolean") return;
          const valid = body.items.every(item => item && typeof item.factId === "string" && item.representative && /^[0-9a-f-]{36}$/i.test(item.representative.id) && typeof item.representative.title === "string" && typeof item.representative.source?.name === "string" && typeof item.representative.timelineAt === "string");
          if (valid) setData({ key: story.publicId, items: body.items.filter(item => item.representative.id !== currentId), more: body.more });
        }).catch(() => {});
    };
    const observer = new IntersectionObserver(entries => { if (entries.some(entry => entry.isIntersecting)) { observer.disconnect(); load(); } }, { root: readerScroller(anchor.current), rootMargin: "500px" });
    if (anchor.current) observer.observe(anchor.current); else load();
    return () => { observer.disconnect(); controller.abort(); };
  }, [story.publicId, currentId, mock]);
  const visible = data?.key === story.publicId ? data : null;
  return <div ref={anchor}><noscript><a href={href(`/story/${story.publicId}`)}>查看事件全部后续</a></noscript>{visible && visible.items.length > 0 && <section className={styles.followups}><header><h2>事件后续 <span>· {visible.items.length}{visible.more ? "+" : ""}</span></h2><IntentLink href={href(`/story/${story.publicId}`)}>查看事件全部 →</IntentLink></header><ul>{visible.items.map(item => <li key={item.factId}><IntentLink href={href(`/articles/${item.representative.id}`)}><span className={styles.followupTitle}><small>同事件</small><span>{item.representative.title}</span></span><span className={styles.followupMeta} suppressHydrationWarning>{item.representative.source.name} · {relativeTime(item.representative.timelineAt)}</span></IntentLink></li>)}</ul></section>}</div>;
}
