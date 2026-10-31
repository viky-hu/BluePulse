"use client";
// AIHOT routes/hot.tsx: Badges, Voices, StoryLink, HeatPanel, Lead, Runner, Row (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
/* eslint-disable @next/next/no-img-element -- preserve supplied cover URLs/srcSet and source loading behavior */
import { IntentLink } from "../_components/feed/IntentLink";
import { Badge } from "../_components/feed/Badge";
import { Faces } from "../_components/feed/Faces";
import { useMainShell } from "../_components/home/MainShell";
import type { HotEntryView } from "./_types";
import { Sparkline } from "./Sparkline";
import { Delta } from "./Delta";
import styles from "./hot.module.css";

export const BADGES: Record<HotEntryView["badges"][number], { label: string; tone: "hot" | "accent" | "amber"; hint: string }> = {
  surge: { label: "爆", tone: "hot", hint: "讨论快速增加" },
  new: { label: "新", tone: "accent", hint: "首报 6 小时内" },
  rising: { label: "发酵中", tone: "amber", hint: "讨论仍在增加" },
};
export const pad = (rank: number) => String(rank).padStart(2, "0");
function Voices({ e }: { e: HotEntryView }) {
  const names = e.sourceNames.slice(0, 2);
  return <span className={styles.voices}>
    <span className={styles.voicesPhrase}>{names.length > 0 && <span className={styles.sourceNames}>{names.join("、")}</span>}{e.sourceCount > names.length ? ` 等 ${e.sourceCount} 个来源` : names.length ? " 报道" : `${e.sourceCount} 个来源`}</span>
    <span className={styles.voicesDot}>·</span><span className={styles.voicesPhrase}><span className={styles.num}>{e.participantCount}</span> 位参与者</span>
  </span>;
}
function Badges({ e }: { e: HotEntryView }) { return e.badges.map(b => <Badge key={b} tone={BADGES[b].tone} title={BADGES[b].hint}>{BADGES[b].label}</Badge>); }
/** The link stretches across the card; Faces stays a separate interactive control above it. */
function StoryLink({ e }: { e: HotEntryView }) {
  const shell = useMainShell();
  return <IntentLink href={shell.href(`/story/${e.story.publicId}`)} className={styles.storyLink}>{e.story.title}</IntentLink>;
}
function HeatPanel({ e }: { e: HotEntryView }) {
  const seen = e.spark.filter((v): v is number => v !== null);
  const peak = Math.max(...seen), peakAt = e.spark.findIndex(v => v === peak);
  return <div className={styles.heatPanel} data-heat-panel>
    <div className={styles.heatPanelHeader}><span>24 小时热度</span><span>峰值 <span className={styles.peak}>{Math.round(peak)}</span>{peakAt >= 0 && <span> · {peakAt === e.spark.length - 1 ? "当前" : `${e.spark.length - 1 - peakAt} 小时前`}</span>}</span></div>
    <Sparkline values={e.spark} className={styles.panelSpark} />
    <div className={styles.heatPanelTimes}><span>24 小时前</span><span>现在</span></div>
  </div>;
}
export function Lead({ e }: { e: HotEntryView }) {
  const panel = !e.cover && e.spark.filter(v => v !== null).length >= 3;
  return <article className={`${styles.card} ${styles.lead}`} data-hot-card="lead" data-card-key={`story:${e.story.publicId}`}>
    <div className={styles.cardTop}><span className={styles.rankLabel} data-rank={e.rank}>NO.{pad(e.rank)}</span><Badges e={e} /><Delta trend={e.trend} pct={e.trendPct} className={styles.pushRight} /></div>
    <div className={styles.leadBody} data-visual={!!e.cover || panel}>
      <div className={styles.leadCopy}><h2><StoryLink e={e} /></h2>{e.summary && <p className={styles.leadSummary}>{e.summary}</p>}</div>
      {e.cover ? <div className={styles.cover}><img src={e.cover.url} srcSet={e.cover.srcSet} sizes="(min-width: 1800px) 350px, (min-width: 1200px) 500px, 58vw" width={e.cover.width ?? undefined} height={e.cover.height ?? undefined} alt="" loading="eager" fetchPriority="high" decoding="async" /></div> : panel && <HeatPanel e={e} />}
    </div>
    <div className={styles.leadFooter}>
      <div className={styles.leadVoices}>
        {e.latest && <p className={styles.latest}><span>最新进展</span>{e.latest}</p>}
        <div className={styles.voicesRow}><Faces participants={e.participants} total={e.participantCount} size={24} /><Voices e={e} /></div>
      </div>
      <div className={styles.leadMetrics}>{!panel && <Sparkline values={e.spark} className={styles.leadSpark} />}<div className={styles.leadHeat}><div>{Math.round(e.heat)}</div><span>热度指数</span></div></div>
    </div>
  </article>;
}
export function Runner({ e }: { e: HotEntryView }) {
  return <article className={`${styles.card} ${styles.runner}`} data-hot-card="runner" data-card-key={`story:${e.story.publicId}`}>
    <div className={styles.cardTop}><span className={styles.rankLabel} data-rank={e.rank}>NO.{pad(e.rank)}</span><Badges e={e} /><Delta trend={e.trend} pct={e.trendPct} className={styles.pushRight} /></div>
    <h2><StoryLink e={e} /></h2>{e.summary && <p className={styles.runnerSummary}>{e.summary}</p>}
    <div className={styles.runnerFooter}><div className={styles.runnerVoices}><Faces participants={e.participants} total={e.participantCount} size={20} /><span><span className={styles.nowrap}><span className={styles.num}>{e.sourceCount}</span> 个来源</span> · <span className={styles.nowrap}><span className={styles.num}>{e.participantCount}</span> 位参与者</span></span></div><div className={styles.runnerMetrics}><Sparkline values={e.spark} className={styles.runnerSpark} /><span>{Math.round(e.heat)}</span></div></div>
  </article>;
}
export function Row({ e }: { e: HotEntryView }) {
  return <li className={styles.row} data-hot-card="row" data-card-key={`story:${e.story.publicId}`}>
    <span className={styles.rowRank} data-rank={e.rank} aria-label={`热度排名第 ${e.rank} 位`}>{pad(e.rank)}</span>
    <div className={styles.rowCopy}><h3><StoryLink e={e} />{e.badges.length > 0 && <span className={styles.rowBadges}><Badges e={e} /></span>}</h3>{e.summary && <p className={styles.rowSummary}>{e.summary}</p>}
      <div className={styles.rowMobile}><Faces participants={e.participants} total={e.participantCount} size={20} /><span className={styles.rowSource}><span className={styles.num}>{e.sourceCount}</span> 个来源</span><span className={styles.rowMobileMetrics}><span className={styles.rowMobileHeat}>{Math.round(e.heat)}</span><Delta trend={e.trend} pct={e.trendPct} /></span></div>
    </div>
    <div className={styles.rowFaces}><Faces participants={e.participants} total={e.participantCount} size={20} /></div><Sparkline values={e.spark} className={styles.rowSpark} /><div className={styles.rowHeat}><span>{Math.round(e.heat)}</span><Delta trend={e.trend} pct={e.trendPct} /></div>
  </li>;
}
