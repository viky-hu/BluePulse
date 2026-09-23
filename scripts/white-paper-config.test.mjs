import assert from "node:assert/strict";
import {
  DESKTOP_REFERENCE_HEIGHT,
  DESKTOP_REFERENCE_WIDTH,
  WHITE_PAPER_ASPECT_RATIO,
  calculateWhitePaperLayout,
  getWhitePaperHeadlineLines,
} from "../src/app/_components/intro/white-paper-config.ts";
import { INTRO_TIMING } from "../src/app/_components/intro/intro-config.ts";
import { MOCK_WHITE_PAPER_ARTICLES } from "../src/app/_components/intro/white-paper-data.ts";

const desktop = calculateWhitePaperLayout(1440, 900);
const mobile = calculateWhitePaperLayout(390, 844);
const desktopUnit = Math.min(
  desktop.viewportWidth / DESKTOP_REFERENCE_WIDTH,
  desktop.viewportHeight / DESKTOP_REFERENCE_HEIGHT,
);

function getPaper(id) {
  return desktop.papers.find((paper) => paper.id === id);
}

function getMobilePaper(id) {
  return mobile.papers.find((paper) => paper.id === id);
}

function getVisualBounds(paper) {
  if (paper.rotation === 90) {
    return {
      left: paper.x - paper.height,
      top: paper.y,
      right: paper.x,
      bottom: paper.y + paper.width,
    };
  }

  if (paper.rotation === -90) {
    return {
      left: paper.x,
      top: paper.y - paper.width,
      right: paper.x + paper.height,
      bottom: paper.y,
    };
  }

  return {
    left: paper.x,
    top: paper.y,
    right: paper.x + paper.width,
    bottom: paper.y + paper.height,
  };
}

assert.equal(MOCK_WHITE_PAPER_ARTICLES.length, 6);
assert.equal(MOCK_WHITE_PAPER_ARTICLES[0].date, "2026.09.20");
assert.match(MOCK_WHITE_PAPER_ARTICLES[0].title, /湖北天门/);
assert.deepEqual(
  MOCK_WHITE_PAPER_ARTICLES.map((article) => article.id),
  ["p0", "p1", "p2", "p3", "p4", "p5"],
);

for (const paper of desktop.papers) {
  assert.ok(paper.height > 0, `${paper.id} should have a height`);
  assert.ok(
    Math.abs(paper.width / paper.height - WHITE_PAPER_ASPECT_RATIO) < 0.0001,
    `${paper.id} should preserve the shared 2:3 paper ratio`,
  );
  assert.ok(paper.entryX !== 0, `${paper.id} should have an off-screen entry offset`);
}

for (const paper of mobile.papers) {
  assert.ok(paper.height > 0, `${paper.id} should have a positive mobile height`);
  assert.ok(
    Math.abs(paper.width / paper.height - WHITE_PAPER_ASPECT_RATIO) < 0.0001,
    `${paper.id} should preserve the shared mobile 2:3 paper ratio`,
  );
}

assert.ok(Math.abs(getPaper("p1").height - 10.08 * desktopUnit) < 0.001, "p1 should grow by 12%");
assert.ok(Math.abs(getPaper("p2").height - 6.75 * desktopUnit) < 0.001, "p2 should grow by 35%");
assert.ok(Math.abs(getPaper("p3").height - 10.864 * desktopUnit) < 0.001, "p3 should grow by 12%");
assert.ok(Math.abs(getPaper("p4").height - 10.08 * desktopUnit) < 0.001, "p4 should grow by 12%");
assert.ok(Math.abs(getPaper("p5").height - 13.216 * desktopUnit) < 0.001, "p5 should grow by 12%");
assert.ok(
  Math.abs(getPaper("p1").x - (desktop.viewportWidth - 3.8 * desktopUnit - 8 * desktopUnit * WHITE_PAPER_ASPECT_RATIO)) < 0.001,
  "p1 should shift slightly left as p2 moves down",
);
assert.ok(
  Math.abs(getPaper("p1").y - 3.8 * desktopUnit) < 0.001,
  "p1 should shift slightly down as p2 moves down",
);
assert.ok(
  Math.abs(getPaper("p2").y - 1.5 * desktopUnit) < 0.001,
  "p2 should move down by one desktop layout unit",
);
assert.ok(
  Math.abs(
    getPaper("p2").x -
      (desktop.viewportWidth - 3 * desktopUnit - 4 * desktopUnit * WHITE_PAPER_ASPECT_RATIO),
  ) < 0.001,
  "p2 should keep its original left coordinate as it grows",
);
assert.ok(
  Math.abs(getPaper("p3").x - 3.7 * desktopUnit) < 0.001 &&
    Math.abs(getPaper("p3").y - 3.2 * desktopUnit) < 0.001,
  "p3 should honor its left and top anchors",
);

assert.equal(desktop.papers.find((paper) => paper.id === "p1")?.rotation, 0);
assert.equal(desktop.papers.find((paper) => paper.id === "p4")?.rotation, 90);
assert.equal(desktop.papers.find((paper) => paper.id === "p5")?.rotation, -90);
assert.ok(
  desktop.papers.find((paper) => paper.id === "p0")?.contentEntryX < 0,
  "p0 content should have a left-side fly-in origin",
);
assert.ok(
  desktop.papers.find((paper) => paper.id === "p1")?.entryX > 0,
  "right-side papers should enter from the right",
);
assert.ok(
  ["p3", "p4", "p5"].every((id) => getPaper(id).entryX < 0),
  "p3, p4, and p5 should enter from the left",
);
assert.ok(
  getPaper("p2").entryX > 0,
  "p2 should enter from the right with p1",
);
assert.ok(
  Math.abs(getPaper("p4").x - 5.5 * desktopUnit) < 0.001,
  "p4 should retain the original rotation-origin x anchor",
);
assert.ok(
  Math.abs(getPaper("p4").y - (desktop.viewportHeight - desktopUnit - 8 * desktopUnit * WHITE_PAPER_ASPECT_RATIO)) < 0.001,
  "p4 should retain its original rotation-origin y coordinate as it grows",
);
assert.ok(
  Math.abs(getVisualBounds(getPaper("p5")).left - (desktop.viewportWidth - 15.7 * desktopUnit)) < 0.001 &&
    Math.abs(getVisualBounds(getPaper("p5")).top - (desktop.viewportHeight - 4.2 * desktopUnit)) < 0.001,
  "p5 should anchor its rotated visual top-left, not its off-screen pivot",
);
assert.ok(
  Math.abs(getVisualBounds(getPaper("p4")).left + 4.58 * desktopUnit) < 0.001,
  "p4 should retain its rotation origin while the enlarged paper extends farther left",
);

assert.ok(
  [116.48, 91.8, 129.92, 105.28, 156.8].every((height, index) =>
    Math.abs(
      getMobilePaper(["p1", "p2", "p3", "p4", "p5"][index]).height - height,
    ) < 0.001,
  ),
  "mobile papers should use the agreed growth rates while retaining their aspect ratio",
);
assert.ok(
  Math.abs(getMobilePaper("p1").x - (390 - 14 - 92 * WHITE_PAPER_ASPECT_RATIO - 8)) < 0.001 &&
    getMobilePaper("p1").y === 28,
  "mobile p1 should shift slightly left and down as p2 moves down",
);
assert.ok(
  Math.abs(getMobilePaper("p2").x - (390 - 8 - 56 * WHITE_PAPER_ASPECT_RATIO)) < 0.001 &&
    getMobilePaper("p2").y === 164,
  "mobile p2 should move down by about one centimeter",
);
assert.ok(
  getMobilePaper("p3").x === 10 && getMobilePaper("p3").y === 232,
  "mobile p3 should keep its original upper-left anchor as it grows",
);
assert.ok(
  getMobilePaper("p4").x === 34 && getMobilePaper("p4").y === 750,
  "mobile p4 should keep its original rotation-origin as it grows",
);
assert.ok(
  Math.abs(getVisualBounds(getMobilePaper("p5")).left - 128) < 0.001 &&
    Math.abs(getVisualBounds(getMobilePaper("p5")).top - 706) < 0.001,
  "mobile p5 should preserve its specified visual upper-left anchor as it grows",
);
assert.equal(INTRO_TIMING.whitePaperEntry, 1.55);
assert.equal(INTRO_TIMING.p0ContentReveal, 0.65);

for (const paper of mobile.papers) {
  assert.ok(paper.width > 0 && paper.height > 0, `${paper.id} should render on mobile`);
}

const lines = getWhitePaperHeadlineLines(
  "浙江丽水：丽警星系形成大规模警务 AI Agent 生态",
  160,
  24,
);
assert.ok(lines.length <= 2, "headlines should be limited to two visual lines");
assert.ok(lines.at(-1)?.endsWith("…") || lines.join("").length > 0);

console.log("white paper config checks passed");
