"use client";

import { useCallback, useId, useRef, useState } from "react";
import { useGSAP } from "@gsap/react";
import { gsap } from "gsap";
import { DrawSVGPlugin } from "gsap/DrawSVGPlugin";
import { Observer } from "gsap/Observer";
import { FloatingCanvas } from "./FloatingCanvas";
import { LogoMark } from "./LogoMark";
import { MaskedSvgTitle } from "./MaskedSvgTitle";
import { ScrollCueButton } from "./ScrollCueButton";
import {
  calculatePanelGeometry,
  INTRO_COLORS,
  INTRO_COPY,
  INTRO_TIMING,
  type IntroExitSource,
  type IntroPhase,
  type PanelGeometry,
} from "./intro-config";
import styles from "./intro.module.css";

gsap.registerPlugin(DrawSVGPlugin, Observer, useGSAP);

const INITIAL_GEOMETRY = calculatePanelGeometry(1440, 900);

function getViewportGeometry() {
  const viewport = window.visualViewport;
  return calculatePanelGeometry(
    Math.round(viewport?.width ?? window.innerWidth),
    Math.round(viewport?.height ?? window.innerHeight),
  );
}

export function InitialIntro() {
  const rootRef = useRef<HTMLElement>(null);
  const sceneRef = useRef<SVGSVGElement>(null);
  const geometryRef = useRef<PanelGeometry>(INITIAL_GEOMETRY);
  const phaseRef = useRef<IntroPhase>("boot");
  const requestExitRef = useRef<(source: IntroExitSource) => void>(() => undefined);
  const [geometry, setGeometry] = useState(INITIAL_GEOMETRY);
  const [phase, setPhase] = useState<IntroPhase>("boot");
  const idSeed = useId().replaceAll(":", "");
  const curtainClipId = `intro-curtain-clip-${idSeed}`;
  const shadowFilterId = `intro-panel-shadow-${idSeed}`;

  const requestButtonExit = useCallback(() => {
    requestExitRef.current("button");
  }, []);

  useGSAP(
    () => {
      const root = rootRef.current;
      const scene = sceneRef.current;
      if (!root || !scene) return;

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
      const prefersReducedMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)",
      ).matches;
      const curtainState = { visibleProgress: 1 };
      const exitProgress = { current: 0 };
      let entryTimeline: gsap.core.Timeline | undefined;
      let exitTimeline: gsap.core.Timeline | undefined;

      const updatePhase = (nextPhase: IntroPhase) => {
        phaseRef.current = nextPhase;
        root.dataset.phase = nextPhase;
        setPhase(nextPhase);
      };

      const syncCurtain = () => {
        const height = geometryRef.current.viewportHeight * curtainState.visibleProgress;
        gsap.set([curtain, curtainClip], { attr: { height } });
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

      requestExitRef.current = (source) => {
        if (phaseRef.current !== "ready") return;

        root.dataset.exitSource = source;
        updatePhase("exiting");
        disableInput();

        if (prefersReducedMotion) {
          curtainState.visibleProgress = 0;
          exitProgress.current = 1;
          syncCurtain();
          gsap.set([titleScene, cueShell], { autoAlpha: 0 });
          updatePhase("complete");
          return;
        }

        exitTimeline = gsap
          .timeline({
            defaults: { overwrite: "auto" },
            onComplete: () => updatePhase("complete"),
          })
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
            curtainState,
            {
              visibleProgress: 0,
              duration: INTRO_TIMING.curtainExit,
              ease: "power3.inOut",
              onUpdate: () => {
                exitProgress.current = 1 - curtainState.visibleProgress;
                syncCurtain();
              },
            },
            0,
          );
      };

      const onKeyDown = (event: KeyboardEvent) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        if (phaseRef.current !== "ready") return;
        event.preventDefault();
        requestExitRef.current("keyboard");
      };

      const onResize = () => {
        const nextGeometry = getViewportGeometry();
        geometryRef.current = nextGeometry;
        setGeometry(nextGeometry);
        syncCurtain();
      };

      window.addEventListener("keydown", onKeyDown);
      window.addEventListener("resize", onResize, { passive: true });
      window.visualViewport?.addEventListener("resize", onResize, { passive: true });
      onResize();

      gsap.set(logoPaths, { drawSVG: "0 0" });
      gsap.set(titleCharacters, { autoAlpha: 0, y: 36 });
      gsap.set(subtitleCharacters, { autoAlpha: 0, y: 18 });
      syncCurtain();

      const showStaticCover = () => {
        gsap.set(logo, { autoAlpha: 0 });
        gsap.set([panel, titleScene, cueShell], { autoAlpha: 1, scale: 1 });
        gsap.set([...titleCharacters, ...subtitleCharacters], { autoAlpha: 1, y: 0 });
        updatePhase("ready");
        enableInput();
      };

      const playEntry = () => {
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
      };

      void (document.fonts?.ready ?? Promise.resolve()).then(playEntry);

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
          <filter
            id={shadowFilterId}
            x="-25%"
            y="-20%"
            width="150%"
            height="150%"
            colorInterpolationFilters="sRGB"
          >
            <feDropShadow
              dx="0"
              dy="18"
              stdDeviation="22"
              floodColor="#121110"
              floodOpacity="0.24"
            />
          </filter>
        </defs>

        <rect
          data-intro-curtain
          x="0"
          y="0"
          width={geometry.viewportWidth}
          height={geometry.viewportHeight}
          fill={INTRO_COLORS.curtain}
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
