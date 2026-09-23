import {
  calculatePanelGeometry,
  type PanelGeometry,
} from "./intro-config.ts";

export const WHITE_PAPER_ASPECT_RATIO = 2 / 3;
export const DESKTOP_REFERENCE_WIDTH = 34;
export const DESKTOP_REFERENCE_HEIGHT = 19;

export type WhitePaperId = "p0" | "p1" | "p2" | "p3" | "p4" | "p5";

export interface WhitePaperLayout {
  id: WhitePaperId;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: 0 | 90 | -90;
  entryX: number;
  contentEntryX: number;
}

export interface WhitePaperLayoutSet {
  viewportWidth: number;
  viewportHeight: number;
  papers: WhitePaperLayout[];
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function makePaper(
  id: WhitePaperId,
  x: number,
  y: number,
  height: number,
  rotation: 0 | 90 | -90,
  entryX: number,
  contentEntryX = 0,
): WhitePaperLayout {
  return {
    id,
    x,
    y,
    width: height * WHITE_PAPER_ASPECT_RATIO,
    height,
    rotation,
    entryX,
    contentEntryX,
  };
}

function calculateDesktopPapers(
  viewportWidth: number,
  viewportHeight: number,
  panel: PanelGeometry,
): WhitePaperLayout[] {
  const unit = Math.min(
    viewportWidth / DESKTOP_REFERENCE_WIDTH,
    viewportHeight / DESKTOP_REFERENCE_HEIGHT,
  );
  const paper = (value: number) => value * unit;
  const p1Height = paper(9 * 1.12);
  const p2Height = paper(5 * 1.35);
  const p3Height = paper(9.7 * 1.12);
  const p4Height = paper(9 * 1.12);
  const p5Height = paper(11.8 * 1.12);
  const p1AnchorWidth = paper(8) * WHITE_PAPER_ASPECT_RATIO;
  const p2AnchorWidth = paper(4) * WHITE_PAPER_ASPECT_RATIO;
  const p1Width = p1Height * WHITE_PAPER_ASPECT_RATIO;
  const p2Width = p2Height * WHITE_PAPER_ASPECT_RATIO;
  const p3Width = p3Height * WHITE_PAPER_ASPECT_RATIO;

  return [
    makePaper(
      "p0",
      panel.x,
      panel.y,
      panel.height,
      0,
      -Math.max(panel.width * 0.06, unit),
      -Math.max(panel.width * 0.72, viewportWidth * 0.14),
    ),
    makePaper(
      "p1",
      viewportWidth - paper(3.8) - p1AnchorWidth,
      paper(3.8),
      p1Height,
      0,
      viewportWidth - (viewportWidth - paper(3.8) - p1AnchorWidth) + p1Width + paper(1.2),
    ),
    makePaper(
      "p2",
      viewportWidth - paper(3) - p2AnchorWidth,
      paper(1.5),
      p2Height,
      0,
      viewportWidth - (viewportWidth - paper(3) - p2AnchorWidth) + p2Width + paper(0.8),
    ),
    makePaper(
      "p3",
      paper(3.7),
      paper(3.2),
      p3Height,
      0,
      -(paper(3.7) + p3Width + paper(1.2)),
    ),
    makePaper(
      "p4",
      paper(5.5),
      viewportHeight - paper(1) - paper(8) * WHITE_PAPER_ASPECT_RATIO,
      p4Height,
      90,
      -(paper(5.5) + p4Height + paper(1.4)),
    ),
    makePaper(
      "p5",
      viewportWidth - paper(15.7),
      viewportHeight - paper(4.2) + p5Height * WHITE_PAPER_ASPECT_RATIO,
      p5Height,
      -90,
      -(viewportWidth - paper(15.7) + p5Height + paper(1.6)),
    ),
  ];
}

function calculateMobilePapers(
  viewportWidth: number,
  viewportHeight: number,
  panel: PanelGeometry,
): WhitePaperLayout[] {
  const scale = clamp(viewportWidth / 390, 0.78, 1.18);
  const size = (value: number) => value * scale;
  const p1Height = size(104 * 1.12);
  const p2Height = size(68 * 1.35);
  const p3Height = size(116 * 1.12);
  const p4Height = size(94 * 1.12);
  const p5Height = size(140 * 1.12);
  const p1AnchorWidth = size(92) * WHITE_PAPER_ASPECT_RATIO;
  const p2AnchorWidth = size(56) * WHITE_PAPER_ASPECT_RATIO;
  const p1Width = p1Height * WHITE_PAPER_ASPECT_RATIO;
  const p2Width = p2Height * WHITE_PAPER_ASPECT_RATIO;
  const p3Width = p3Height * WHITE_PAPER_ASPECT_RATIO;
  const p5Width = p5Height * WHITE_PAPER_ASPECT_RATIO;
  const bottomBand = Math.max(viewportHeight - size(22), panel.y + panel.height);
  const p4Y = Math.min(bottomBand - size(72), viewportHeight - size(44));
  const p5VisualY = Math.min(bottomBand - size(116), viewportHeight - size(102));

  return [
    makePaper(
      "p0",
      panel.x,
      panel.y,
      panel.height,
      0,
      -Math.max(panel.width * 0.06, size(18)),
      -Math.max(panel.width * 0.72, viewportWidth * 0.2),
    ),
    makePaper(
      "p1",
      viewportWidth - size(14) - p1AnchorWidth - size(8),
      size(28),
      p1Height,
      0,
      viewportWidth - (viewportWidth - size(14) - p1AnchorWidth - size(8)) + p1Width + size(12),
    ),
    makePaper(
      "p2",
      viewportWidth - size(8) - p2AnchorWidth,
      size(164),
      p2Height,
      0,
      viewportWidth - (viewportWidth - size(8) - p2AnchorWidth) + p2Width + size(10),
    ),
    makePaper(
      "p3",
      size(10),
      size(232),
      p3Height,
      0,
      -(size(10) + p3Width + size(12)),
    ),
    makePaper(
      "p4",
      size(34),
      p4Y,
      p4Height,
      90,
      -(size(34) + p4Height + size(12)),
    ),
    makePaper(
      "p5",
      size(128),
      p5VisualY + p5Width,
      p5Height,
      -90,
      viewportWidth - size(128) + size(20),
    ),
  ];
}

export function calculateWhitePaperLayout(
  viewportWidth: number,
  viewportHeight: number,
  panelGeometry?: PanelGeometry,
): WhitePaperLayoutSet {
  const safeWidth = Math.max(viewportWidth, 1);
  const safeHeight = Math.max(viewportHeight, 1);
  const panel =
    panelGeometry ?? calculatePanelGeometry(safeWidth, safeHeight);
  const papers =
    safeWidth <= 768
      ? calculateMobilePapers(safeWidth, safeHeight, panel)
      : calculateDesktopPapers(safeWidth, safeHeight, panel);

  return {
    viewportWidth: safeWidth,
    viewportHeight: safeHeight,
    papers,
  };
}

export function getWhitePaperHeadlineLines(
  title: string,
  maxWidth: number,
  fontSize: number,
  maxLines = 2,
): string[] {
  const safeFontSize = Math.max(fontSize, 1);
  const charactersPerLine = Math.max(
    2,
    Math.floor(Math.max(maxWidth, safeFontSize * 2) / (safeFontSize * 0.96)),
  );
  const maxCharacters = charactersPerLine * maxLines;
  const characters = Array.from(title);

  if (characters.length <= maxCharacters) {
    return Array.from({ length: Math.ceil(characters.length / charactersPerLine) }, (_, index) =>
      characters.slice(index * charactersPerLine, (index + 1) * charactersPerLine).join(""),
    );
  }

  const truncated = characters.slice(0, Math.max(maxCharacters - 1, 1));
  truncated.push("…");
  return Array.from({ length: maxLines }, (_, index) =>
    truncated.slice(index * charactersPerLine, (index + 1) * charactersPerLine).join(""),
  ).filter(Boolean);
}
