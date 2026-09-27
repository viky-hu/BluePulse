export type IntroPhase =
  | "boot"
  | "logo"
  | "exiting"
  | "reporting"
  | "complete"
  | "transitioning"
  | "main";

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
  reportGreen: "#A4D7C7",
  reportLine: "#353330",
  reportSubtitle: "#686B67",
} as const;

export const INTRO_TIMING = {
  logoDraw: 1.8,
  logoHold: 0.6,
  logoFade: 0.25,
  panelInitialScale: 0.92,
  panelRevealDuration: 0.8,
  panelRevealEase: "power2.out",
  whitePaperEntry: 1.55,
  p0ContentReveal: 0.65,
  curtainExit: 1.3,
  reportGreenDelay: 0.18,
  reportGreenExpand: 1.65,
  reportGreenHold: 0.23,
  reportLineDraw: 0.86,
  reportTitleReveal: 0.9,
  reportTitleSplitOffset: 0.34,
  reportSubtitleDelay: 0.06,
  reportTitleHold: 0.15,
  reportLineErase: 0.6,
  reportSubtitleFade: 0.42,
  reportCueFade: 0.24,
  reportClipSeamBleed: 1.5,
  mainButtonSettle: 0.22,
  mainTitleFade: 0.28,
  mainPaperExit: 1.05,
  mainGreenDelay: 0.18,
  mainGreenMorph: 1.35,
  mainP0Delay: 0.22,
  mainP0ContentExit: 0.62,
  mainP0Morph: 1.28,
} as const;

export const INTRO_SEQUENCE = {
  logoStart: 0,
  panelStart: 0,
  curtainStart: INTRO_TIMING.logoDraw + INTRO_TIMING.logoHold + INTRO_TIMING.logoFade,
} as const;

export function calculatePanelGeometry(
  viewportWidth: number,
  viewportHeight: number,
): PanelGeometry {
  const safeWidth = Math.max(viewportWidth, 1);
  const safeHeight = Math.max(viewportHeight, 1);
  const isMobile = safeWidth <= 768;

  const mobileWidth = Math.min(
    Math.max(safeWidth - 32, 1),
    Math.max((safeHeight - 48) * (2 / 3), 1),
  );
  const desktopNaturalWidth = Math.min(
    safeWidth * (10 / 34),
    safeHeight * (15 / 19) * (2 / 3),
  );
  const width = isMobile ? mobileWidth : safeWidth * (11 / 34);
  const naturalHeight = (isMobile ? mobileWidth : desktopNaturalWidth) * 1.5;
  const greenTop = calculateReportGreenTop(safeWidth, safeHeight);
  const panelTopLead = Math.max(10, Math.min(14, safeHeight * 0.012));
  const targetPanelTop = Math.max(0, greenTop - panelTopLead);
  const targetPanelHeight = safeHeight - targetPanelTop * 2;
  const safeMargin = isMobile ? Math.min(24, safeHeight * 0.08) : safeHeight * 0.04;
  const safeMaxHeight = Math.max(naturalHeight, safeHeight - safeMargin * 2);
  const height = Math.max(
    naturalHeight,
    Math.min(safeMaxHeight, targetPanelHeight),
  );

  return {
    x: (safeWidth - width) / 2,
    y: (safeHeight - height) / 2,
    width,
    height,
    viewportWidth: safeWidth,
    viewportHeight: safeHeight,
  };
}

export function calculateReportGreenTop(
  viewportWidth: number,
  viewportHeight: number,
): number {
  const safeWidth = Math.max(viewportWidth, 1);
  const safeHeight = Math.max(viewportHeight, 1);
  const isMobile = safeWidth <= 768;
  const shortEdge = Math.min(safeWidth, safeHeight);

  return isMobile
    ? Math.max(44, Math.min(safeHeight * 0.18, shortEdge * 0.28))
    : safeHeight * (2 / 19);
}

export interface ReportGeometry {
  viewportWidth: number;
  viewportHeight: number;
  green: {
    x: number;
    width: number;
    top: number;
    bottom: number;
    centerY: number;
  };
  line: {
    x1: number;
    x2: number;
    centerY: number;
    strokeWidth: number;
  };
  title: {
    centerX: number;
    centerY: number;
    fontSize: number;
    halfHeight: number;
  };
  subtitle: {
    centerX: number;
    y: number;
    fontSize: number;
  };
}

export interface ReportGreenGeometry {
  x: number;
  width: number;
  top: number;
  bottom: number;
  centerY: number;
}

export interface PanelRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface CueGeometry {
  centerX: number;
  centerY: number;
  size: number;
}

export function calculateReportGeometry(
  viewportWidth: number,
  viewportHeight: number,
): ReportGeometry {
  const safeWidth = Math.max(viewportWidth, 1);
  const safeHeight = Math.max(viewportHeight, 1);
  const isMobile = safeWidth <= 768;
  const centerY = safeHeight / 2;

  const greenMargin = isMobile
    ? Math.max(16, Math.min(28, safeWidth * 0.06))
    : safeWidth * (0.5 / 34);
  const greenTop = calculateReportGreenTop(safeWidth, safeHeight);
  const lineMargin = isMobile
    ? Math.max(20, Math.min(32, safeWidth * 0.06))
    : safeWidth * (1 / 34);
  const titleFontSize = isMobile
    ? Math.max(38, Math.min(60, safeWidth * 0.105))
    : Math.min(120, safeWidth * 0.075, safeHeight * 0.13);
  const titleHalfHeight = titleFontSize * 0.74;
  const subtitleFontSize = isMobile
    ? Math.max(14, Math.min(18, safeWidth * 0.045))
    : Math.max(18, Math.min(24, safeWidth * 0.017));

  return {
    viewportWidth: safeWidth,
    viewportHeight: safeHeight,
    green: {
      x: greenMargin,
      width: Math.max(safeWidth - greenMargin * 2, 1),
      top: Math.min(greenTop, safeHeight - 1),
      bottom: safeHeight,
      centerY,
    },
    line: {
      x1: lineMargin,
      x2: Math.max(safeWidth - lineMargin, lineMargin + 1),
      centerY,
      strokeWidth: isMobile
        ? Math.max(3, Math.min(4, safeWidth * 0.009))
        : Math.max(4, Math.min(5, safeWidth * 0.003)),
    },
    title: {
      centerX: safeWidth / 2,
      centerY,
      fontSize: titleFontSize,
      halfHeight: titleHalfHeight,
    },
    subtitle: {
      centerX: safeWidth / 2,
      y: centerY + titleFontSize * (isMobile ? 1.15 : 1.08),
      fontSize: subtitleFontSize,
    },
  };
}

export function calculateCueGeometry(report: ReportGeometry): CueGeometry {
  const safeWidth = Math.max(report.viewportWidth, 1);
  const safeHeight = Math.max(report.viewportHeight, 1);
  const isMobile = safeWidth <= 768;
  const size = isMobile ? 64 : 76;
  const subtitleHalfHeight = report.subtitle.fontSize * 0.5;
  const subtitleGap = isMobile
    ? Math.max(36, Math.min(64, safeHeight * 0.08))
    : Math.max(52, Math.min(96, safeHeight * 0.1));
  const safeBottom = isMobile
    ? Math.max(12, Math.min(28, safeHeight * 0.06))
    : Math.max(20, Math.min(42, safeHeight * 0.05));
  const desiredCenterY =
    report.subtitle.y + subtitleHalfHeight + subtitleGap + size / 2;
  const maxCenterY = safeHeight - size / 2 - safeBottom;

  return {
    centerX: report.subtitle.centerX,
    centerY: Math.max(size / 2, Math.min(desiredCenterY, maxCenterY)),
    size,
  };
}

export function calculateMainGreenGeometry(
  report: ReportGeometry,
): ReportGreenGeometry {
  const safeWidth = Math.max(report.viewportWidth, 1);
  const safeHeight = Math.max(report.viewportHeight, 1);
  const isMobile = safeWidth <= 768;
  const left = safeWidth * (isMobile ? 0.27 : 0.24);
  const rightInset = isMobile
    ? Math.max(12, safeWidth * 0.045)
    : safeWidth * (0.5 / 34);
  const right = Math.max(left + 1, safeWidth - rightInset);
  const top = Math.max(0, report.green.top - safeHeight * (isMobile ? 0.05 : 0.045));

  return {
    x: left,
    width: right - left,
    top,
    bottom: safeHeight,
    centerY: (top + safeHeight) / 2,
  };
}

export function calculateMainPanelRect(
  panel: PanelGeometry,
  report: ReportGeometry,
): PanelRect {
  const green = calculateMainGreenGeometry(report);
  const safeWidth = Math.max(report.viewportWidth, 1);
  const safeHeight = Math.max(report.viewportHeight, 1);
  const leftInset = safeWidth * (safeWidth <= 768 ? 0.04 : 0.025);
  const rightInset = safeWidth * (safeWidth <= 768 ? 0.06 : 0.05);
  const left = green.x + leftInset;
  const right = green.x + green.width - rightInset;
  const top = Math.max(0, green.top - safeHeight * 0.018);
  const bottom = Math.max(
    top + 1,
    green.bottom - safeHeight * (safeWidth <= 768 ? 0.055 : 0.065),
  );

  return {
    x: left,
    y: top,
    width: Math.max(1, right - left),
    height: Math.max(1, bottom - top),
  };
}
