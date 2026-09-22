"use client";

import { useCallback, useId, useRef, useState } from "react";
import { useGSAP } from "@gsap/react";
import { gsap } from "gsap";
import { CustomEase } from "gsap/CustomEase";
import { DrawSVGPlugin } from "gsap/DrawSVGPlugin";
import { Observer } from "gsap/Observer";
import { FloatingCanvas } from "./FloatingCanvas";
import { GreenCanvas } from "./GreenCanvas";
import { LatestReportTitle } from "./LatestReportTitle";
import { LogoMark } from "./LogoMark";
import { MaskedSvgTitle } from "./MaskedSvgTitle";
import { ReportLine } from "./ReportLine";
import { ScrollCueButton } from "./ScrollCueButton";
import {
  calculatePanelGeometry,
  calculateReportGeometry,
  INTRO_COLORS,
  INTRO_COPY,
  INTRO_TIMING,
  type IntroExitSource,
  type IntroPhase,
  type PanelGeometry,
  type ReportGeometry,
} from "./intro-config";
import styles from "./intro.module.css";

gsap.registerPlugin(CustomEase, DrawSVGPlugin, Observer, useGSAP);

const INITIAL_GEOMETRY = calculatePanelGeometry(1440, 900);
const INITIAL_REPORT_GEOMETRY = calculateReportGeometry(1440, 900);
const CURTAIN_EXIT_EASE_PATH =
  "M0,0 C0.04,0.12 0.08,0.48 0.2,0.78 C0.36,0.95 0.7,0.995 1,1";
const REPORT_FLUID_EASE_PATH =
  "M0,0 C0.06,0.55 0.16,0.84 0.35,0.95 C0.58,0.995 0.84,1 1,1";
const REPORT_TEXT_EASE_PATH =
  "M0,0 C0.08,0.25 0.22,0.58 0.42,0.82 C0.62,0.95 0.84,0.995 1,1";

function getViewportGeometries() {
  const viewport = window.visualViewport;
  const width = Math.round(viewport?.width ?? window.innerWidth);
  const height = Math.round(viewport?.height ?? window.innerHeight);
  return {
    panel: calculatePanelGeometry(width, height),
    report: calculateReportGeometry(width, height),
  };
}

export function InitialIntro() {
  const rootRef = useRef<HTMLElement>(null);
  const sceneRef = useRef<SVGSVGElement>(null);
  const geometryRef = useRef<PanelGeometry>(INITIAL_GEOMETRY);
  const reportGeometryRef = useRef<ReportGeometry>(INITIAL_REPORT_GEOMETRY);
  const phaseRef = useRef<IntroPhase>("boot");
  const requestExitRef = useRef<(source: IntroExitSource) => void>(() => undefined);
  const reportMotionRef = useRef({
    greenProgress: 0,
    lineDrawProgress: 0,
    lineEraseProgress: 0,
    titleProgress: 0,
    subtitleProgress: 0,
  });
  const [geometry, setGeometry] = useState(INITIAL_GEOMETRY);
  const [reportGeometry, setReportGeometry] = useState(INITIAL_REPORT_GEOMETRY);
  const [phase, setPhase] = useState<IntroPhase>("boot");
  const idSeed = useId().replaceAll(":", "");
  const curtainClipId = `intro-curtain-clip-${idSeed}`;
  const shadowFilterId = `intro-panel-shadow-${idSeed}`;
  const reportUpperClipId = `intro-report-upper-${idSeed}`;
  const reportLowerClipId = `intro-report-lower-${idSeed}`;

  const requestButtonExit = useCallback(() => {
    requestExitRef.current("button");
  }, []);

  useGSAP(
    (_context, contextSafe) => {
      const root = rootRef.current;
      const scene = sceneRef.current;
      if (!root || !scene) return;
      const safeContext = contextSafe ?? ((callback: () => void) => callback);

      let cancelled = false;
      const select = gsap.utils.selector(root);
      const logo = select<SVGSVGElement>("[data-intro-logo]")[0];
      const logoPaths = select<SVGPathElement>("[data-logo-path]");
      const panel = select<SVGGElement>("[data-intro-panel]")[0];
      const titleScene = select<SVGGElement>("[data-intro-title]")[0];
      const titleCharacters = select<SVGTSpanElement>("[data-title-char]");
      const subtitleCharacters = select<SVGTSpanElement>("[data-subtitle-char]");
      const cueShell = select<HTMLDivElement>("[data-scroll-cue-shell]")[0];
      const curtain = select<SVGRectElement>("[data-intro-curtain]")[0];
      const curtainClip = select<SVGRectElement>("[data-intro-curtain-clip]")[0];
      const greenCanvas = select<SVGRectElement>("[data-report-green]")[0];
      const reportLine = select<SVGLineElement>("[data-report-line]")[0];
      const reportTitleScene = select<SVGGElement>("[data-report-title-scene]")[0];
      const reportTitles = select<SVGTextElement>("[data-report-title] text");
      const reportSubtitle = select<SVGTextElement>("[data-report-subtitle]")[0];
      const reportUpperClip = select<SVGRectElement>("[data-report-upper-clip]")[0];
      const reportLowerClip = select<SVGRectElement>("[data-report-lower-clip]")[0];
      const prefersReducedMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)",
      ).matches;
      const reportFluidEase = CustomEase.create(
        "blue-pulse-fluid",
        REPORT_FLUID_EASE_PATH,
      );
      const curtainExitEase = CustomEase.create(
        "blue-pulse-curtain",
        CURTAIN_EXIT_EASE_PATH,
      );
      const reportTextEase = CustomEase.create(
        "blue-pulse-text",
        REPORT_TEXT_EASE_PATH,
      );
      const curtainProgress = { value: 0 };
      const reportMotion = reportMotionRef.current;
      let entryTimeline: gsap.core.Timeline | undefined;
      let exitTimeline: gsap.core.Timeline | undefined;
      let resizeFrame: number | undefined;

      const updatePhase = (nextPhase: IntroPhase) => {
        phaseRef.current = nextPhase;
        root.dataset.phase = nextPhase;
        setPhase(nextPhase);
      };

      const syncCurtain = () => {
        const height = geometryRef.current.viewportHeight * (1 - curtainProgress.value);
        gsap.set([curtain, curtainClip], { attr: { height } });
      };

      const syncReport = () => {
        const nextGeometry = reportGeometryRef.current;
        const greenProgress = Math.max(0, Math.min(reportMotion.greenProgress, 1));
        const lineDrawProgress = Math.max(0, Math.min(reportMotion.lineDrawProgress, 1));
        const lineEraseProgress = Math.max(0, Math.min(reportMotion.lineEraseProgress, 1));
        const titleProgress = Math.max(0, Math.min(reportMotion.titleProgress, 1));
        const subtitleProgress = Math.max(0, Math.min(reportMotion.subtitleProgress, 1));
        const topDistance = nextGeometry.green.centerY - nextGeometry.green.top;
        const bottomDistance = nextGeometry.green.bottom - nextGeometry.green.centerY;

        gsap.set(greenCanvas, {
          attr: {
            x: nextGeometry.green.x,
            y: nextGeometry.green.centerY - topDistance * greenProgress,
            width: nextGeometry.green.width,
            height: (topDistance + bottomDistance) * greenProgress,
          },
        });
        const lineDrawEnd = lineDrawProgress * 100;
        const lineEraseStart = lineEraseProgress * 100;
        const lineStart = lineEraseProgress > 0 ? lineEraseStart : 0;
        const lineEnd = lineEraseProgress > 0 ? 100 : lineDrawEnd;
        const seamBleed = INTRO_TIMING.reportClipSeamBleed;

        gsap.set(reportLine, {
          attr: {
            x1: nextGeometry.line.x1,
            x2: nextGeometry.line.x2,
            y1: nextGeometry.line.centerY,
            y2: nextGeometry.line.centerY,
            strokeWidth: nextGeometry.line.strokeWidth,
          },
          drawSVG: `${lineStart}% ${lineEnd}%`,
        });
        gsap.set([reportUpperClip, reportLowerClip], {
          attr: { x: 0, width: nextGeometry.viewportWidth },
        });
        gsap.set(reportUpperClip, {
          attr: {
            y: nextGeometry.title.centerY - nextGeometry.title.halfHeight * titleProgress,
            height: nextGeometry.title.halfHeight * titleProgress + seamBleed,
          },
        });
        gsap.set(reportLowerClip, {
          attr: {
            y: nextGeometry.title.centerY - seamBleed,
            height: nextGeometry.title.halfHeight * titleProgress + seamBleed,
          },
        });
        gsap.set(reportTitles, {
          attr: {
            x: nextGeometry.title.centerX,
            y: nextGeometry.title.centerY,
            fontSize: nextGeometry.title.fontSize,
          },
        });
        gsap.set(reportSubtitle, {
          attr: {
            x: nextGeometry.subtitle.centerX,
            y: nextGeometry.subtitle.y,
            fontSize: nextGeometry.subtitle.fontSize,
          },
          autoAlpha: subtitleProgress,
        });
        if (titleProgress > 0) gsap.set(reportTitleScene, { autoAlpha: 1 });
        if (lineDrawProgress > 0 && lineEraseProgress < 1) {
          gsap.set(reportLine, { autoAlpha: 1 });
        }
      };

      const wheelObserver = Observer.create({
        target: root,
        type: "wheel",
        tolerance: 12,
        debounce: true,
        onDown: () => requestExitRef.current("wheel"),
      });
      const touchObserver = Observer.create({
        target: root,
        type: "touch",
        tolerance: 24,
        dragMinimum: 12,
        lockAxis: true,
        debounce: true,
        onUp: () => requestExitRef.current("touch"),
      });

      const disableInput = () => {
        wheelObserver.disable();
        touchObserver.disable();
      };

      const enableInput = () => {
        wheelObserver.enable();
        touchObserver.enable();
      };

      disableInput();

      const runExit = (source: IntroExitSource) => {
        if (phaseRef.current !== "ready") return;

        root.dataset.exitSource = source;
        updatePhase("exiting");
        disableInput();

        if (prefersReducedMotion) {
          curtainProgress.value = 1;
          reportMotion.greenProgress = 1;
          reportMotion.lineDrawProgress = 0;
          reportMotion.lineEraseProgress = 0;
          reportMotion.titleProgress = 1;
          reportMotion.subtitleProgress = 1;
          syncCurtain();
          syncReport();
          gsap.set([titleScene, cueShell], { autoAlpha: 0 });
          gsap.set(reportLine, { drawSVG: "0 0", autoAlpha: 0 });
          updatePhase("complete");
          return;
        }

        exitTimeline = gsap
          .timeline({
            defaults: { overwrite: "auto" },
            onComplete: () => updatePhase("complete"),
          })
          .addLabel("exitStart", 0)
          .to(
            [titleScene, cueShell],
            {
              autoAlpha: 0,
              duration: INTRO_TIMING.contentFade,
              ease: "power2.out",
            },
            0,
          )
          .to(
            curtainProgress,
            {
              value: 1,
              duration: INTRO_TIMING.curtainExit,
              ease: curtainExitEase,
              onUpdate: syncCurtain,
            },
            "exitStart",
          )
          .addLabel(
            "greenStart",
            `exitStart+=${INTRO_TIMING.reportGreenDelay}`,
          )
          .call(() => updatePhase("reporting"), [], "greenStart")
          .to(
            reportMotion,
            {
              greenProgress: 1,
              duration: INTRO_TIMING.reportGreenExpand,
              ease: reportFluidEase,
              onUpdate: syncReport,
            },
            "greenStart",
          )
          .addLabel(
            "greenEnd",
            `greenStart+=${INTRO_TIMING.reportGreenExpand}`,
          )
          .addLabel(
            "lineStart",
            `greenEnd+=${INTRO_TIMING.reportGreenHold}`,
          )
          .to({}, { duration: INTRO_TIMING.reportGreenHold }, "greenEnd")
          .set(reportLine, { autoAlpha: 1 }, "lineStart")
          .to(
            reportMotion,
            {
              lineDrawProgress: 1,
              duration: INTRO_TIMING.reportLineDraw,
              ease: reportFluidEase,
              onUpdate: syncReport,
            },
            "lineStart",
          )
          .addLabel(
            "lineComplete",
            `lineStart+=${INTRO_TIMING.reportLineDraw}`,
          )
          .addLabel(
            "titleStart",
            `lineComplete-=${INTRO_TIMING.reportTitleLead}`,
          )
          .to(
            reportMotion,
            {
              titleProgress: 1,
              duration: INTRO_TIMING.reportTitleReveal,
              ease: reportTextEase,
              onUpdate: syncReport,
            },
            "titleStart",
          )
          .to(
            reportMotion,
            {
              subtitleProgress: 1,
              duration: INTRO_TIMING.reportSubtitleFade,
              ease: reportTextEase,
              onUpdate: syncReport,
            },
            "<",
          )
          .addLabel(
            "eraseStart",
            `lineComplete+=${INTRO_TIMING.reportLineHold}`,
          )
          .to(
            reportMotion,
            {
              lineEraseProgress: 1,
              duration: INTRO_TIMING.reportLineErase,
              ease: reportFluidEase,
              onUpdate: syncReport,
              onComplete: () => {
                reportMotion.lineDrawProgress = 0;
                reportMotion.lineEraseProgress = 0;
                syncReport();
                gsap.set(reportLine, { autoAlpha: 0, drawSVG: "0 0" });
              },
            },
            "eraseStart",
          );
      };

      requestExitRef.current = (source) => safeContext(() => runExit(source))();

      const onKeyDown = (event: KeyboardEvent) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        if (phaseRef.current !== "ready") return;
        event.preventDefault();
        requestExitRef.current("keyboard");
      };

      const onResize = () => {
        const nextGeometries = getViewportGeometries();
        geometryRef.current = nextGeometries.panel;
        reportGeometryRef.current = nextGeometries.report;
        setGeometry(nextGeometries.panel);
        setReportGeometry(nextGeometries.report);
        syncCurtain();
        syncReport();

        if (resizeFrame !== undefined) cancelAnimationFrame(resizeFrame);
        resizeFrame = requestAnimationFrame(() => {
          resizeFrame = undefined;
          safeContext(() => {
            syncCurtain();
            syncReport();
          })();
        });
      };

      window.addEventListener("keydown", onKeyDown);
      window.addEventListener("resize", onResize, { passive: true });
      window.visualViewport?.addEventListener("resize", onResize, { passive: true });
      onResize();

      gsap.set(logoPaths, { drawSVG: "0 0" });
      gsap.set(titleCharacters, { autoAlpha: 0, y: 36 });
      gsap.set(subtitleCharacters, { autoAlpha: 0, y: 18 });
      gsap.set(reportTitleScene, { autoAlpha: 0 });
      gsap.set(reportLine, { autoAlpha: 0, drawSVG: "0 0" });
      gsap.set(reportSubtitle, { autoAlpha: 0 });
      syncCurtain();
      syncReport();

      const showStaticCover = () => {
        gsap.set(logo, { autoAlpha: 0 });
        gsap.set([panel, titleScene, cueShell], { autoAlpha: 1, scale: 1 });
        gsap.set([...titleCharacters, ...subtitleCharacters], { autoAlpha: 1, y: 0 });
        updatePhase("ready");
        enableInput();
      };

      const playEntry = safeContext(() => {
        if (cancelled) return;
        if (prefersReducedMotion) {
          showStaticCover();
          return;
        }

        const panelRevealPosition = `reveal+=${INTRO_TIMING.panelDelay}`;
        const panelGeometry = geometryRef.current;
        const panelCenterX = panelGeometry.x + panelGeometry.width / 2;
        const panelCenterY = panelGeometry.y + panelGeometry.height / 2;
        gsap.set(panel, { svgOrigin: `${panelCenterX} ${panelCenterY}` });

        entryTimeline = gsap.timeline({ defaults: { overwrite: "auto" } });
        entryTimeline
          .call(() => updatePhase("logo"))
          .to(logoPaths, {
            drawSVG: "0 100%",
            duration: INTRO_TIMING.logoDraw,
            ease: "power1.inOut",
          })
          .to({}, { duration: INTRO_TIMING.logoHold })
          .to(logo, {
            autoAlpha: 0,
            duration: INTRO_TIMING.logoFade,
            ease: "power1.out",
          })
          .call(() => updatePhase("revealing"))
          .set(titleScene, { autoAlpha: 1 }, "reveal")
          .to(
            titleCharacters,
            {
              autoAlpha: 1,
              y: 0,
              duration: INTRO_TIMING.titleCharacter,
              ease: "power3.out",
              stagger: (_index, target) =>
                Number((target as SVGElement).dataset.charIndex) * INTRO_TIMING.titleStagger,
            },
            "reveal",
          )
          .to(
            subtitleCharacters,
            {
              autoAlpha: 1,
              y: 0,
              duration: INTRO_TIMING.subtitleCharacter,
              ease: "power3.out",
              stagger: (_index, target) =>
                Number((target as SVGElement).dataset.charIndex) *
                INTRO_TIMING.subtitleStagger,
            },
            "reveal",
          )
          .fromTo(
            panel,
            {
              autoAlpha: 0,
              scale: INTRO_TIMING.panelInitialScale,
            },
            {
              autoAlpha: 1,
              scale: 1,
              duration: INTRO_TIMING.panelRevealDuration,
              ease: INTRO_TIMING.panelRevealEase,
            },
            panelRevealPosition,
          )
          .to(
            cueShell,
            {
              autoAlpha: 1,
              duration: INTRO_TIMING.panelRevealDuration,
              ease: INTRO_TIMING.panelRevealEase,
            },
            panelRevealPosition,
          )
          .call(() => {
            updatePhase("ready");
            enableInput();
          });
      });

      void (document.fonts?.ready ?? Promise.resolve()).then(() => playEntry());

      return () => {
        cancelled = true;
        entryTimeline?.kill();
        exitTimeline?.kill();
        wheelObserver.kill();
        touchObserver.kill();
        requestExitRef.current = () => undefined;
        window.removeEventListener("keydown", onKeyDown);
        window.removeEventListener("resize", onResize);
        window.visualViewport?.removeEventListener("resize", onResize);
        if (resizeFrame !== undefined) cancelAnimationFrame(resizeFrame);
      };
    },
    { scope: rootRef },
  );

  const cueCenterY = geometry.y + geometry.height * (1 - 0.085);

  return (
    <main
      ref={rootRef}
      className={styles.stage}
      data-phase="boot"
      aria-label="Blue Pulse 初始页面"
    >
      <h1 className={styles.srOnly}>Blue Pulse 国内外警务科技情报系统</h1>
      <svg
        ref={sceneRef}
        className={styles.scene}
        viewBox={`0 0 ${geometry.viewportWidth} ${geometry.viewportHeight}`}
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <defs>
          <clipPath id={curtainClipId} clipPathUnits="userSpaceOnUse">
            <rect
              data-intro-curtain-clip
              x="0"
              y="0"
              width={geometry.viewportWidth}
              height={geometry.viewportHeight}
            />
          </clipPath>
          <clipPath id={reportUpperClipId} clipPathUnits="userSpaceOnUse">
            <rect
              data-report-upper-clip
              x="0"
              y={reportGeometry.title.centerY}
              width={reportGeometry.viewportWidth}
              height="0"
            />
          </clipPath>
          <clipPath id={reportLowerClipId} clipPathUnits="userSpaceOnUse">
            <rect
              data-report-lower-clip
              x="0"
              y={reportGeometry.title.centerY}
              width={reportGeometry.viewportWidth}
              height="0"
            />
          </clipPath>
          <filter
            id={shadowFilterId}
            x="-35%"
            y="-35%"
            width="175%"
            height="185%"
            colorInterpolationFilters="sRGB"
          >
            <feDropShadow
              dx="0"
              dy="22"
              stdDeviation="26"
              floodColor="#121110"
              floodOpacity="0.32"
            />
          </filter>
        </defs>

        <rect
          x="0"
          y="0"
          width={geometry.viewportWidth}
          height={geometry.viewportHeight}
          fill={INTRO_COLORS.page}
        />
        <rect
          data-intro-curtain
          x="0"
          y="0"
          width={geometry.viewportWidth}
          height={geometry.viewportHeight}
          fill={INTRO_COLORS.curtain}
        />
        <GreenCanvas
          geometry={reportGeometry}
          fill={INTRO_COLORS.reportGreen}
        />
        <FloatingCanvas
          geometry={geometry}
          curtainClipId={curtainClipId}
          shadowFilterId={shadowFilterId}
          lightFill={INTRO_COLORS.panel}
          darkFill={INTRO_COLORS.curtain}
        />
        <MaskedSvgTitle
          geometry={geometry}
          curtainClipId={curtainClipId}
          title={INTRO_COPY.title}
          subtitle={INTRO_COPY.subtitle}
          lightAreaFill={INTRO_COLORS.curtain}
          darkAreaFill={INTRO_COLORS.gold}
        />
        <ReportLine geometry={reportGeometry} color={INTRO_COLORS.reportLine} />
        <LatestReportTitle
          geometry={reportGeometry}
          upperClipId={reportUpperClipId}
          lowerClipId={reportLowerClipId}
          titleColor={INTRO_COLORS.reportLine}
          subtitleColor={INTRO_COLORS.reportSubtitle}
        />
      </svg>

      <LogoMark />

      <div
        className={styles.cueShell}
        data-scroll-cue-shell
        style={{ left: geometry.viewportWidth / 2, top: cueCenterY }}
      >
        <ScrollCueButton disabled={phase !== "ready"} onActivate={requestButtonExit} />
      </div>
    </main>
  );
}
