"use client";

// Adapted from AIHOT SignalRiver.tsx (MIT), Copyright (c) 2026 数字生命卡兹克.
// Drawing is preserved; lifecycle, paper colors and clipping are adapted for Pulse.
import { useEffect, useRef, type ReactNode } from "react";
import { useGSAP } from "@gsap/react";
import { gsap } from "gsap";
import { STAGES, STEP, KIND, FLASH_MS, INTRO_MS, easeInOut, rgba, layout, trace, readColors, paintStatic, paintPaper, type Layout, type RiverSource } from "./_river-drawing";
import styles from "./about.module.css";

gsap.registerPlugin(useGSAP);

interface Pulse {
  s: number;
  x: number;
  v: number;
}

export function SignalRiver({
  sources,
  focus,
  onArrive,
  className = "",
  children,
}: {
  sources: RiverSource[];
  focus: number | null;
  onArrive?: () => void;
  className?: string;
  children?: ReactNode;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const labelRef = useRef<HTMLDivElement>(null);
  const focusRef = useRef(focus);
  const arriveRef = useRef(onArrive);
  const redrawRef = useRef<() => void>(() => {});
  useEffect(() => { arriveRef.current = onArrive; }, [onArrive]);

  useEffect(() => {
    focusRef.current = focus;
    redrawRef.current();
  }, [focus]);

  useGSAP(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    const label = labelRef.current;
    const ctx = canvas?.getContext("2d");
    if (!wrap || !canvas || !label || !ctx) return;
    const probe = document.createElement("canvas").getContext("2d", { willReadFrequently: true })!;
    const layer = document.createElement("canvas");
    const lctx = layer.getContext("2d")!;
    const motionPreference = matchMedia("(prefers-reduced-motion: reduce)");
    let still = motionPreference.matches;

    let L: Layout | null = null;
    let col = readColors(probe, wrap);
    let dpr = 1;
    let pulses: Pulse[] = [];
    let passing: number[] = [];
    let spawnDebt = 0;
    let flashAt = -Infinity;
    let hover: { s: number | null; bundle: number | null; paper: boolean } | null = null;
    let frame = 0;
    let last = 0;
    // The intro starts the first time the river is seen.
    let elapsed = still ? INTRO_MS : 0;
    // On screen now (the observer keeps it current after), so the intro plays where it is seen.
    const box = wrap.getBoundingClientRect();
    const scrollRoot = wrap.closest<HTMLElement>("[data-p0-scroller]");
    const rootBox = scrollRoot?.getBoundingClientRect();
    let visible = box.bottom > (rootBox?.top ?? 0) && box.top < (rootBox?.bottom ?? window.innerHeight);
    let disposed = false;

    const build = () => {
      const w = wrap.clientWidth;
      const h = wrap.clientHeight;
      if (w < 10 || h < 10) return;
      dpr = Math.min(2, window.devicePixelRatio || 1);
      for (const c of [canvas, layer]) {
        c.width = Math.round(w * dpr);
        c.height = Math.round(h * dpr);
      }
      const previous = L;
      L = layout(w, h, sources);
      passing = L.strands.flatMap((s, i) => (s.pass ? [i] : []));
      // Keep both reveal time and travelling positions through a paper resize.
      pulses = previous ? pulses.map(p => ({
        s: Math.min(L!.strands.length - 1, Math.floor(p.s / previous.strands.length * L!.strands.length)),
        x: p.x / previous.w * w,
        v: p.v / previous.w * w,
      })) : [];
      hover = null;
      label.hidden = true;
      lctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      paintStatic(lctx, L, col);
    };

    const draw = (now: number) => {
      if (!L) return;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const reveal = still ? 1 : easeInOut(now / INTRO_MS);
      if (reveal < 1) {
        // The river flows in: the drawing is uncovered left to right behind a soft edge.
        const edge = (L.w + 80) * reveal;
        ctx.save();
        ctx.beginPath();
        ctx.rect(0, 0, Math.max(0, edge) * dpr, canvas.height);
        ctx.clip();
        ctx.drawImage(layer, 0, 0);
        ctx.restore();
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        const soft = ctx.createLinearGradient(edge - 80, 0, edge, 0);
        soft.addColorStop(0, rgba(col.bg, 0));
        soft.addColorStop(1, rgba(col.bg, 1));
        ctx.fillStyle = soft;
        ctx.fillRect(edge - 80, 0, 80, L.h);
        return;
      }
      ctx.drawImage(layer, 0, 0);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.lineJoin = "round";
      ctx.lineCap = "round";

      if (hover && (hover.s !== null || hover.bundle !== null)) {
        const lit = hover.bundle !== null ? L.strands.filter((s) => s.bundle === hover!.bundle) : [L.strands[hover.s!]!];
        ctx.lineWidth = lit.length > 1 ? 1 : 1.5;
        for (const s of lit) {
          const kept = L.bundles[s.bundle]!.kept;
          trace(ctx, s, 0, Math.min(s.end, L.gate));
          ctx.strokeStyle = rgba(col.ink, lit.length > 1 ? 0.45 : 0.9);
          ctx.stroke();
          trace(ctx, s, L.gate, s.end);
          ctx.strokeStyle = kept ? rgba(col.accent, 0.95) : rgba(col.ink, lit.length > 1 ? 0.3 : 0.6);
          ctx.stroke();
        }
      }

      const trail = Math.max(24, Math.min(56, L.w * 0.04));
      ctx.lineWidth = 1.8;
      for (const p of pulses) {
        const s = L.strands[p.s]!;
        const head = Math.min(p.x, s.end);
        if (head <= 0) continue;
        const tail = Math.max(0, head - trail);
        let c = col.ink;
        let a = col.dark ? 0.85 : 0.7;
        if (head >= L.gate) {
          if (s.pass) {
            c = col.accent;
            a = 1;
          } else a *= Math.max(0, 1 - (head - L.gate) / (s.end - L.gate));
        }
        if (a <= 0.01) continue;
        const g = ctx.createLinearGradient(tail, 0, head, 0);
        g.addColorStop(0, rgba(c, 0));
        g.addColorStop(1, rgba(c, a));
        trace(ctx, s, tail, head);
        ctx.strokeStyle = g;
        ctx.stroke();
      }

      const f = (now - flashAt) / FLASH_MS;
      if (f >= 0 && f < 1) paintPaper(ctx, L, col, 1 - f);

      const fx = focusRef.current;
      if (fx !== null && fx !== undefined) {
        ctx.fillStyle = rgba(col.bg, 0.62);
        for (let k = 0; k < 4; k++) if (k !== fx) ctx.fillRect(L.w * STAGES[k]!, 0, L.w * (STAGES[k + 1]! - STAGES[k]!), L.h);
      }
    };

    const tick = (now: number) => {
      frame = 0;
      if (disposed || !L || still || !visible || document.hidden) { last = 0; return; }
      const dt = Math.min(0.05, last ? (now - last) / 1000 : 0);
      last = now;
      elapsed += dt * 1000;
      if (elapsed < INTRO_MS * 0.8) {
        draw(elapsed);
        schedule();
        return;
      }
      spawnDebt += dt * (L.w >= 900 ? 7 : 4.5);
      while (spawnDebt >= 1 && pulses.length < 80) {
        spawnDebt -= 1;
        const s = passing.length > 0 && Math.random() < 0.11 ? passing[Math.floor(Math.random() * passing.length)]! : Math.floor(Math.random() * L.strands.length);
        pulses.push({ s, x: -Math.random() * 30, v: L.w * (0.12 + Math.random() * 0.06) });
      }
      const kept: Pulse[] = [];
      for (const p of pulses) {
        p.x += p.v * dt;
        const s = L.strands[p.s]!;
        if (p.x < s.end) kept.push(p);
        else if (s.pass) {
          flashAt = elapsed;
          arriveRef.current?.();
        }
      }
      pulses = kept;
      draw(elapsed);
      schedule();
    };

    const schedule = () => {
      if (!frame && !still && visible && !document.hidden && !disposed) frame = requestAnimationFrame(tick);
    };
    const redraw = () => {
      if (still || !frame) draw(elapsed);
    };
    redrawRef.current = redraw;

    const place = (x: number, y: number, title: string, note: string) => {
      const [t, n] = label.children as unknown as [HTMLElement, HTMLElement];
      t.textContent = title;
      n.textContent = note;
      n.hidden = !note;
      label.hidden = false;
      const w = label.offsetWidth;
      const left = Math.max(8, Math.min(x + 14, wrap.clientWidth - w - 8));
      const top = Math.max(8, Math.min(y + 16, wrap.clientHeight - label.offsetHeight - 8));
      label.style.transform = `translate(${left}px, ${top}px)`;
    };

    const onMove = (e: PointerEvent) => {
      if (!L) return;
      const box = wrap.getBoundingClientRect();
      const x = e.clientX - box.left;
      const y = e.clientY - box.top;
      const p = L.paper;
      if (x >= p.x - 8 && x <= p.x + p.w + 8 && y >= p.y - 8 && y <= p.y + p.h + 8) {
        hover = { s: null, bundle: null, paper: true };
        place(x, y, "警务科技日报", "汇成一份，集中阅读 · 成刊能力建设中");
        redraw();
        return;
      }
      const c = Math.round(x / STEP);
      let best = -1;
      let dist = 7;
      L.strands.forEach((s, i) => {
        if (x > s.end + 2) return;
        const d = Math.abs(s.ys[Math.min(c, s.ys.length - 1)]! - y);
        if (d < dist) {
          dist = d;
          best = i;
        }
      });
      if (best < 0) {
        onLeave();
        return;
      }
      const s = L.strands[best]!;
      const b = L.bundles[s.bundle]!;
      if (x < L.x2) {
        hover = { s: best, bundle: null, paper: false };
        const kind = s.source ? (KIND[s.source.kind] ?? "信源") : "信源";
        place(x, y, s.source ? s.source.name : "一个信源", s.source?.heatOnly ? `${kind} · 只计入热度` : kind);
      } else {
        hover = { s: null, bundle: s.bundle, paper: false };
        if (x < L.gate) place(x, y, "同一件事", `${b.n} 个来源的报道合成一条`);
        else if (b.kept) place(x, y, "进了精选", "有信息量，分数也够");
        else place(x, y, "没进精选", "信息不够、重复或只是营销");
      }
      redraw();
    };
    const onLeave = () => {
      hover = null;
      label.hidden = true;
      redraw();
    };

    const resize = new ResizeObserver(() => {
      build();
      redraw();
    });
    const recolour = () => {
      col = readColors(probe, wrap);
      if (L) paintStatic(lctx, L, col);
      redraw();
    };
    const theme = new MutationObserver(recolour);
    const scheme = matchMedia("(prefers-color-scheme: dark)");
    const seen = new IntersectionObserver(([entry]) => {
      visible = !!entry?.isIntersecting;
      last = 0;
      onVisibility();
    }, { root: scrollRoot });
    const onVisibility = () => {
      last = 0;
      if (still || !visible || document.hidden) {
        if (frame) cancelAnimationFrame(frame);
        frame = 0;
      }
      schedule();
    };
    const onMotionChange = () => {
      still = motionPreference.matches;
      if (still) { elapsed = INTRO_MS; pulses = []; }
      onVisibility();
      redraw();
    };

    build();
    draw(elapsed);
    schedule();
    resize.observe(wrap);
    seen.observe(wrap);
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] });
    scheme.addEventListener("change", recolour);
    motionPreference.addEventListener("change", onMotionChange);
    document.addEventListener("visibilitychange", onVisibility);
    wrap.addEventListener("pointermove", onMove);
    wrap.addEventListener("pointerleave", onLeave);
    return () => {
      disposed = true;
      if (frame) cancelAnimationFrame(frame);
      redrawRef.current = () => {};
      resize.disconnect();
      seen.disconnect();
      theme.disconnect();
      scheme.removeEventListener("change", recolour);
      motionPreference.removeEventListener("change", onMotionChange);
      document.removeEventListener("visibilitychange", onVisibility);
      wrap.removeEventListener("pointermove", onMove);
      wrap.removeEventListener("pointerleave", onLeave);
    };
  }, { scope: wrapRef, dependencies: [sources], revertOnUpdate: true });

  return (
    <div ref={wrapRef} className={`${styles.river} ${className}`} data-signal-river>
      <canvas ref={canvasRef} aria-hidden="true" className={styles.canvas} />
      <div ref={labelRef} hidden className={styles.tooltip} data-river-tooltip>
        <div className={styles.tooltipTitle} />
        <div className={styles.tooltipNote} />
      </div>
      {children}
    </div>
  );
}
