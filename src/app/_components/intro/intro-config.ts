export type IntroPhase =
  | "boot"
  | "logo"
  | "revealing"
  | "ready"
  | "exiting"
  | "complete";

export type IntroExitSource = "button" | "wheel" | "touch" | "keyboard";

export interface PanelGeometry {
  x: number;
  y: number;
  width: number;
  height: number;
  viewportWidth: number;
  viewportHeight: number;
}

export const INTRO_COLORS = {
  curtain: "#353330",
  page: "#F2F2F2",
  panel: "#FDFDFD",
  gold: "#D5AF86",
} as const;

export const INTRO_TIMING = {
  logoDraw: 1.8,
  logoHold: 0.6,
  logoFade: 0.25,
  titleCharacter: 0.28,
  titleStagger: 0.025,
  subtitleCharacter: 0.24,
  subtitleStagger: 0.015,
  panelInitialScale: 0.92,
  panelDelay: 0.2,
  panelRevealDuration: 0.8,
  panelRevealEase: "power2.out",
  contentFade: 0.2,
  curtainExit: 0.8,
} as const;

export const INTRO_COPY = {
  title: "Blue Pulse",
  subtitle: "国内外警务科技情报系统",
} as const;

export function calculatePanelGeometry(
  viewportWidth: number,
  viewportHeight: number,
): PanelGeometry {
  const safeWidth = Math.max(viewportWidth, 1);
  const safeHeight = Math.max(viewportHeight, 1);
  const isMobile = safeWidth <= 768;

  const width = isMobile
    ? Math.min(Math.max(safeWidth - 32, 1), Math.max((safeHeight - 48) * (2 / 3), 1))
    : Math.min(safeWidth * (10 / 34), safeHeight * (15 / 19) * (2 / 3));
  const height = width * 1.5;

  return {
    x: (safeWidth - width) / 2,
    y: (safeHeight - height) / 2,
    width,
    height,
    viewportWidth: safeWidth,
    viewportHeight: safeHeight,
  };
}

export function getTitleLayout(geometry: PanelGeometry) {
  const isMobile = geometry.viewportWidth <= 768;
  const titleY = geometry.viewportHeight * 0.48;

  return {
    centerX: geometry.viewportWidth / 2,
    titleY,
    subtitleY: titleY + (isMobile ? 54 : 100),
  };
}
