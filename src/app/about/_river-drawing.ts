// Adapted from AIHOT SignalRiver.tsx (MIT), Copyright (c) 2026 数字生命卡兹克.
// Original geometry and canvas painting; see THIRD_PARTY_NOTICES.md.
export interface RiverSource {
  name: string;
  kind: string;
  heatOnly: boolean;
}

/** Stage boundaries as fractions of the width: 采集 | 归并 | 精选 | 成刊. */
export const STAGES = [0, 0.25, 0.5, 0.75, 1] as const;

export const STEP = 3;
export const KIND: Record<string, string> = { x_search: "X 账号", rss: "RSS", web_list: "网页", mp_account: "公众号", json_list: "接口" };
export const FLASH_MS = 900;
export const INTRO_MS = 1800;
/** Slow in, slow out: the river starts gently, crosses, and settles. */
export const easeInOut = (u: number) => (1 - Math.cos(Math.PI * Math.min(1, Math.max(0, u)))) / 2;

type RGB = [number, number, number];
export const rgba = (c: RGB, a: number) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
const smooth = (u: number) => (u <= 0 ? 0 : u >= 1 ? 1 : u * u * (3 - 2 * u));

function prng(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface Strand {
  /** y at x = i * STEP. */
  ys: Float32Array;
  end: number;
  bundle: number;
  /** Items on this line can reach the paper (a kept bundle, and a source that is not heat-only). */
  pass: boolean;
  source: RiverSource | null;
}

interface Bundle {
  y: number;
  n: number;
  kept: boolean;
  half: number;
}

export interface Layout {
  w: number;
  h: number;
  strands: Strand[];
  bundles: Bundle[];
  x1: number;
  x2: number;
  gate: number;
  xo: number;
  out: number;
  paper: { x: number; y: number; w: number; h: number };
}

export function layout(w: number, h: number, sources: RiverSource[]): Layout {
  const rand = prng(20260928 + sources.length);
  const n = Math.max(40, Math.min(160, Math.round(w / 7.5)));
  const B = w >= 900 ? 9 : w >= 560 ? 7 : 5;
  const K = B >= 9 ? 3 : 2;
  const kept = new Set(Array.from({ length: K }, (_, k) => Math.round(((k + 0.5) * B) / K - 0.5)));
  const pad = Math.max(14, h * 0.07);
  const x1 = w * STAGES[1];
  const x2 = w * STAGES[2];
  const gate = w * 0.625;
  const xo = w * 0.8;
  // The paper sits a little above the middle; the page sets the latest 精选 under it (42% + 42px).
  const out = h * 0.42;
  const pw = Math.max(26, Math.min(46, w * 0.042));
  const ph = pw * 1.32;
  const paper = { x: w * 0.875 - pw / 2, y: out - ph / 2, w: pw, h: ph };

  // A few big stories and more small ones; every bundle has at least two reports.
  const weights = Array.from({ length: B }, () => 0.45 + rand() ** 1.6 * 1.9);
  const total = weights.reduce((a, b) => a + b, 0);
  const sizes = weights.map((x) => Math.max(2, Math.round((x / total) * n)));
  let diff = n - sizes.reduce((a, b) => a + b, 0);
  for (let i = 0; diff !== 0; i = (i + 1) % B) {
    if (diff > 0) {
      sizes[i]!++;
      diff--;
    } else if (sizes[i]! > 2) {
      sizes[i]!--;
      diff++;
    }
  }
  const spacing = Math.max(0.8, Math.min(1.6, (h * 0.075) / Math.max(...sizes)));
  const bundles: Bundle[] = sizes.map((size, j) => ({ y: h * 0.14 + ((j + 0.5) / B) * h * 0.72, n: size, kept: kept.has(j), half: (size * spacing) / 2 }));

  const cols = Math.ceil(w / STEP) + 1;
  const strands: Strand[] = [];
  let i = 0;
  sizes.forEach((size, j) => {
    const b = bundles[j]!;
    const mean = pad + ((i + size / 2) / n) * (h - 2 * pad);
    for (let r = 0; r < size; r++, i++) {
      const y0 = pad + ((i + 0.5) / n) * (h - 2 * pad) + (rand() - 0.5) * ((h - 2 * pad) / n) * 0.8;
      const amp = 2 + rand() * 5;
      const freq = (Math.PI * 2) / (70 + rand() * 140);
      const phase = rand() * Math.PI * 2;
      const off = (r - (size - 1) / 2) * spacing;
      const yA = y0 + (mean - y0) * 0.25 + amp * 0.4 * Math.sin(freq * x1 + phase);
      const ys = new Float32Array(cols);
      for (let c = 0; c < cols; c++) {
        const x = c * STEP;
        if (x <= x1) {
          const u = x / x1;
          ys[c] = y0 + (mean - y0) * 0.25 * smooth(u) + amp * (1 - 0.6 * u) * Math.sin(freq * x + phase);
        } else if (x <= x2) ys[c] = yA + (b.y + off - yA) * smooth((x - x1) / (x2 - x1));
        else if (!b.kept || x <= gate) ys[c] = b.y + off;
        else if (x <= xo) ys[c] = b.y + off + (out + off * 0.5 - b.y - off) * smooth((x - gate) / (xo - gate));
        else ys[c] = out + off * 0.5;
      }
      const source = sources.length > 0 ? sources[i % sources.length]! : null;
      strands.push({ ys, end: b.kept ? paper.x : gate + w * 0.045, bundle: j, pass: b.kept && !source?.heatOnly, source });
    }
  });
  return { w, h, strands, bundles, x1, x2, gate, xo, out, paper };
}

export function trace(ctx: CanvasRenderingContext2D, s: Strand, from: number, to: number) {
  const a = Math.max(0, Math.floor(from / STEP));
  const b = Math.min(s.ys.length - 1, Math.ceil(to / STEP));
  ctx.beginPath();
  ctx.moveTo(Math.max(from, 0), s.ys[a]!);
  for (let c = a + 1; c <= b; c++) ctx.lineTo(Math.min(c * STEP, to), s.ys[c]!);
}

export interface Colors {
  ink: RGB;
  accent: RGB;
  line: RGB;
  surface: RGB;
  bg: RGB;
  dark: boolean;
}

export function readColors(probe: CanvasRenderingContext2D, element: HTMLElement): Colors {
  const root = getComputedStyle(element);
  const parse = (css: string, fallback: RGB): RGB => {
    if (!css) return fallback;
    probe.clearRect(0, 0, 1, 1);
    probe.fillStyle = `rgb(${fallback.join(",")})`;
    probe.fillStyle = css;
    probe.fillRect(0, 0, 1, 1);
    const d = probe.getImageData(0, 0, 1, 1).data;
    return [d[0]!, d[1]!, d[2]!];
  };
  const bg = parse(root.getPropertyValue("--river-bg").trim(), [250, 249, 246]);
  return {
    ink: parse(root.getPropertyValue("--ink").trim(), [32, 42, 48]),
    accent: parse(root.getPropertyValue("--accent").trim(), [23, 107, 117]),
    line: parse(root.getPropertyValue("--line-strong").trim(), [200, 205, 205]),
    surface: parse(root.getPropertyValue("--surface").trim(), [255, 255, 255]),
    bg,
    dark: bg[0] * 0.3 + bg[1] * 0.59 + bg[2] * 0.11 < 110,
  };
}

export function paintStatic(ctx: CanvasRenderingContext2D, L: Layout, col: Colors) {
  const base = col.dark ? 0.2 : 0.13;
  ctx.clearRect(0, 0, L.w, L.h);
  ctx.lineWidth = 1;
  ctx.lineJoin = "round";
  for (const s of L.strands) {
    const kept = L.bundles[s.bundle]!.kept;
    trace(ctx, s, 0, Math.min(s.end, L.gate));
    ctx.strokeStyle = rgba(col.ink, base);
    ctx.stroke();
    trace(ctx, s, L.gate, s.end);
    if (kept) ctx.strokeStyle = rgba(col.accent, col.dark ? 0.6 : 0.45);
    else {
      const g = ctx.createLinearGradient(L.gate, 0, s.end, 0);
      g.addColorStop(0, rgba(col.ink, base));
      g.addColorStop(1, rgba(col.ink, 0));
      ctx.strokeStyle = g;
    }
    ctx.stroke();
  }
  // The cable into the paper.
  ctx.beginPath();
  ctx.moveTo(L.xo, L.out);
  ctx.lineTo(L.paper.x, L.out);
  ctx.lineWidth = 1.6;
  ctx.strokeStyle = rgba(col.accent, 0.95);
  ctx.stroke();

  // The gate: a hairline across the river, open only where a kept bundle passes.
  const top = L.h * 0.05;
  const bottom = L.h * 0.95;
  const gaps = L.bundles.filter((b) => b.kept).map((b) => [b.y - b.half - 7, b.y + b.half + 7] as const);
  ctx.lineWidth = 1;
  ctx.strokeStyle = rgba(col.line, 1);
  ctx.beginPath();
  let y = top;
  for (const [a, b] of gaps) {
    ctx.moveTo(L.gate, y);
    ctx.lineTo(L.gate, a);
    y = b;
  }
  ctx.moveTo(L.gate, y);
  ctx.lineTo(L.gate, bottom);
  ctx.stroke();
  for (const [a, b] of gaps) {
    for (const yy of [a, b]) {
      ctx.beginPath();
      ctx.moveTo(L.gate - 4, yy);
      ctx.lineTo(L.gate + 4, yy);
      ctx.stroke();
    }
  }

  paintPaper(ctx, L, col, 0);

  // The lines come in from beyond the left edge.
  ctx.save();
  ctx.globalCompositeOperation = "destination-out";
  const fade = ctx.createLinearGradient(0, 0, Math.min(64, L.w * 0.06), 0);
  fade.addColorStop(0, "rgba(0,0,0,1)");
  fade.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = fade;
  ctx.fillRect(0, 0, Math.min(64, L.w * 0.06), L.h);
  ctx.restore();
}

/** The day's paper: a nameplate bar, the headline and two columns of rules. `glow` lights it. */
export function paintPaper(ctx: CanvasRenderingContext2D, L: Layout, col: Colors, glow: number) {
  const p = L.paper;
  ctx.save();
  if (glow > 0) {
    ctx.shadowColor = rgba(col.accent, 0.55 * glow);
    ctx.shadowBlur = 18 * glow;
  }
  ctx.beginPath();
  if (ctx.roundRect) ctx.roundRect(p.x, p.y, p.w, p.h, 5);
  else ctx.rect(p.x, p.y, p.w, p.h);
  ctx.fillStyle = rgba(col.surface, 1);
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.lineWidth = 1;
  ctx.strokeStyle = glow > 0 ? rgba(col.accent, 0.35 + 0.65 * glow) : rgba(col.line, 1);
  ctx.stroke();
  ctx.restore();
  const ix = p.x + p.w * 0.17;
  const iw = p.w * 0.66;
  ctx.fillStyle = rgba(col.accent, 1);
  ctx.fillRect(ix, p.y + p.h * 0.13, iw * 0.42, Math.max(2, p.w * 0.06));
  ctx.fillStyle = glow > 0 ? rgba(col.accent, 0.5 + 0.5 * glow) : rgba(col.ink, 0.82);
  ctx.fillRect(ix, p.y + p.h * 0.29, iw * 0.9, Math.max(2, p.w * 0.075));
  ctx.fillStyle = rgba(col.ink, col.dark ? 0.4 : 0.26);
  for (let r = 0; r < 4; r++) {
    const yy = p.y + p.h * (0.47 + r * 0.12);
    ctx.fillRect(ix, yy, iw * 0.45, 1);
    ctx.fillRect(ix + iw * 0.55, yy, iw * 0.45, 1);
  }
}
