"use client";
// AIHOT features/story/HeatChart.tsx (MIT). Copyright (c) 2026 数字生命卡兹克.
import { useId, useMemo, useState } from "react";
import { PillTabs } from "../../_components/feed/PillTabs";
import { monthDayTime } from "../../hot/_data";
import { areaPath, curvePath, type Pt } from "../../hot/curve";
import type { HeatPoint } from "./story-data";
import styles from "./story.module.css";

const hour = 3600_000;
const ranges = [{ hours: 24, label: "24 小时" }, { hours: 72, label: "3 天" }, { hours: 168, label: "7 天" }];

function plottedRange(all: HeatPoint[], hours: number) {
  const end = Date.parse(all[all.length - 1]?.hour ?? "");
  return all.filter(point => Date.parse(point.hour) >= end - hours * hour);
}

function plot(points: HeatPoint[]) {
  if (points.length < 3) return null;
  const first = Date.parse(points[0].hour);
  const last = Date.parse(points[points.length - 1].hour);
  const peak = Math.max(...points.map(point => point.heat));
  const scale = 10 ** Math.floor(Math.log10(peak / 4 || 1));
  const step = [1, 2, 2.5, 5, 10].map(value => value * scale).find(value => value >= peak / 4) ?? scale;
  const top = Math.max(step, Math.ceil(peak / step) * step);
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);
  const x = (at: number) => 100 * (at - first) / Math.max(last - first, hour);
  const y = (heat: number) => 100 * (1 - heat / top);
  const runs: Pt[][] = [];
  let run: Pt[] = [], previous = NaN;
  for (const point of points) {
    const at = Date.parse(point.hour);
    if (at - previous > hour) { runs.push(run); run = []; }
    run.push([x(at), y(point.heat)]);
    previous = at;
  }
  runs.push(run);
  const reference = points.find(point => Date.parse(point.hour) === last - 24 * hour);
  const current = points[points.length - 1].heat;
  const change = reference && reference.heat > 0 ? Math.round(100 * (current - reference.heat) / reference.heat) : null;
  return { x, y, ticks, peak, current, change, line: runs.map(curvePath).join(""), area: runs.map(run => areaPath(run, 100)).join("") };
}

export function HeatChart({ points }: { points: HeatPoint[] }) {
  const id = `story-heat-${useId().replace(/[^\w-]/g, "")}`;
  const [hours, setHours] = useState(168);
  const [selected, setSelected] = useState<number | null>(null);
  const choices = useMemo(() => {
    const seen = new Set<number>();
    return ranges.filter(range => {
      const count = plottedRange(points, range.hours).length;
      if (seen.has(count)) return false;
      seen.add(count);
      return count > 0;
    });
  }, [points]);
  const range = choices.find(choice => choice.hours === hours) ?? choices[choices.length - 1];
  const shown = useMemo(() => plottedRange(points, range?.hours ?? 168), [points, range]);
  const chart = useMemo(() => plot(shown), [shown]);
  if (!chart) return <p className={styles.empty}>还没有足够的连续观测数据，暂不绘制趋势。</p>;
  const active = selected === null ? null : shown[selected];
  const dot = active ?? shown[shown.length - 1];
  const dotX = chart.x(Date.parse(dot.hour)), dotY = chart.y(dot.heat);
  const pick = (clientX: number, rect: DOMRect) => {
    const x = 100 * (clientX - rect.left) / rect.width;
    let index = 0;
    shown.forEach((point, i) => {
      if (Math.abs(chart.x(Date.parse(point.hour)) - x) < Math.abs(chart.x(Date.parse(shown[index].hour)) - x)) index = i;
    });
    setSelected(index);
  };
  return <div className={styles.chart}>
    <div className={styles.chartHeader}>
      <dl>
        <div><dt>可比范围当前</dt><dd>{Math.round(chart.current)}</dd></div>
        <div><dt>可比范围峰值</dt><dd>{Math.round(chart.peak)}</dd></div>
        <div><dt>近 24 小时变化</dt><dd>{chart.change === null ? "–" : `${chart.change > 0 ? "+" : ""}${chart.change}%`}</dd></div>
      </dl>
      {choices.length > 1 && <PillTabs size="xs" label="时间范围" active={String(range.hours)}
        onSelect={key => { setHours(Number(key)); setSelected(null); }}
        items={choices.map(choice => ({ key: String(choice.hours), label: choice.label }))} />}
    </div>
    <div className={styles.chartGrid}>
      {chart.ticks.map(tick => <span key={tick} className={styles.chartTick} style={{ top: `${chart.y(tick)}%` }} aria-hidden="true">{tick}</span>)}
      <div tabIndex={0} role="img" aria-label={`热度走势，当前 ${Math.round(chart.current)}，峰值 ${Math.round(chart.peak)}`}
        className={styles.plot} onPointerMove={event => pick(event.clientX, event.currentTarget.getBoundingClientRect())}
        onPointerDown={event => pick(event.clientX, event.currentTarget.getBoundingClientRect())}
        onPointerLeave={event => { if (event.pointerType === "mouse") setSelected(null); }}
        onBlur={() => setSelected(null)} onKeyDown={event => {
          if (event.key === "ArrowRight") setSelected(index => Math.min(shown.length - 1, (index ?? -1) + 1));
          else if (event.key === "ArrowLeft") setSelected(index => Math.max(0, (index ?? shown.length) - 1));
          else if (event.key === "Escape") setSelected(null);
          else return;
          event.preventDefault();
        }}>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <defs><linearGradient id={id} x2="0" y2="100%"><stop stopColor="currentColor" stopOpacity=".2" /><stop offset="1" stopColor="currentColor" stopOpacity="0" /></linearGradient></defs>
          {chart.ticks.map(tick => <line key={tick} x1="0" x2="100" y1={chart.y(tick)} y2={chart.y(tick)} className={styles.gridLine} vectorEffect="non-scaling-stroke" />)}
          <path d={chart.area} fill={`url(#${id})`} />
          <path d={chart.line} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
        </svg>
        <span className={styles.chartDot} style={{ left: `${dotX}%`, top: `${dotY}%` }} aria-hidden="true" />
        {active && <span className={styles.chartTip} style={dotX > 55 ? { right: `${100 - dotX}%` } : { left: `${dotX}%` }}>
          {monthDayTime(active.hour)} · 热度 {active.heat.toFixed(1)} · {active.participants} 位参与者
        </span>}
      </div>
    </div>
    <div className={styles.chartAxis}><time dateTime={shown[0].hour}>{monthDayTime(shown[0].hour)}</time>
      <time dateTime={shown[shown.length - 1].hour}>{monthDayTime(shown[shown.length - 1].hour)}</time></div>
    <p className={styles.meta}>趋势仅比较持续完整观测到的相同主体。移动指针或点击图表可查看每小时热度，键盘可用左右方向键切换。</p>
  </div>;
}
