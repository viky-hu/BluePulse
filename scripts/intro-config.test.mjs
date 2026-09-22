import assert from "node:assert/strict";
import {
  calculatePanelGeometry,
  calculateReportGeometry,
  INTRO_TIMING,
} from "../src/app/_components/intro/intro-config.ts";

function assertPanelTracksReportTop(viewportWidth, viewportHeight) {
  const panel = calculatePanelGeometry(viewportWidth, viewportHeight);
  const report = calculateReportGeometry(viewportWidth, viewportHeight);
  const lead = Math.max(10, Math.min(14, Math.max(viewportHeight, 1) * 0.012));
  const panelTopDelta = report.green.top - panel.y;
  const naturalWidth = viewportWidth <= 768
    ? panel.width
    : Math.min(
        viewportWidth * (10 / 34),
        viewportHeight * (15 / 19) * (2 / 3),
      );

  assert.ok(
    panel.height > naturalWidth * 1.5,
    "panel should grow taller than its natural aspect ratio for the report layout",
  );
  assert.ok(
    panelTopDelta >= lead - 0.001,
    `panel should lead the green canvas by ${lead}px when it needs extra height`,
  );
  assert.ok(
    panel.y + panel.height <= panel.viewportHeight + 0.001,
    "panel should remain inside the viewport",
  );
}

assertPanelTracksReportTop(1440, 900);
assertPanelTracksReportTop(390, 844);

const desktopPanel = calculatePanelGeometry(3400, 1900);
assert.equal(desktopPanel.width, 1100);
assert.equal(desktopPanel.height, 1528);
assert.equal(desktopPanel.x + desktopPanel.width / 2, 1700);

const shortPanel = calculatePanelGeometry(320, 200);
assert.equal(shortPanel.height, shortPanel.width * 1.5);

const greenStart = INTRO_TIMING.reportGreenDelay;
const greenEnd = greenStart + INTRO_TIMING.reportGreenExpand;
const lineStart = greenEnd + INTRO_TIMING.reportGreenHold;
const lineComplete = lineStart + INTRO_TIMING.reportLineDraw;
const titleStart = lineComplete;
const titleComplete = titleStart + INTRO_TIMING.reportTitleReveal;
const subtitleStart = titleComplete + INTRO_TIMING.reportSubtitleDelay;
const eraseStart = titleComplete + INTRO_TIMING.reportTitleHold;
const eraseComplete = eraseStart + INTRO_TIMING.reportLineErase;

assert.ok(
  INTRO_TIMING.curtainExit >= 1.2 && INTRO_TIMING.curtainExit <= 1.4,
  "curtain should leave the screen over roughly 1.3 seconds",
);
assert.ok(
  greenStart < INTRO_TIMING.curtainExit,
  "green canvas should start before the curtain fully exits",
);
assert.ok(
  greenEnd >= 1.7 && greenEnd <= 1.9,
  "green canvas should finish after a deliberately extended reveal",
);
assert.ok(
  lineStart >= 2 && lineStart <= 2.2,
  "line drawing should start around the 2 second mark",
);
assert.ok(
  titleStart === lineComplete,
  "title should begin when the line finishes drawing",
);
assert.ok(
  INTRO_TIMING.reportTitleReveal >= 0.85 && INTRO_TIMING.reportTitleReveal <= 0.95,
  "title should use the shortened 0.9 second reveal",
);
assert.ok(
  INTRO_TIMING.reportTitleSplitOffset >= 0.3 &&
    INTRO_TIMING.reportTitleSplitOffset <= 0.38,
  "title layers should begin with a clear split offset",
);
assert.ok(
  subtitleStart > titleComplete && eraseStart > titleComplete,
  "subtitle and line erase should wait until the title settles",
);
assert.ok(
  eraseComplete >= 4.4 && eraseComplete <= 4.8,
  "report sequence should complete within the shortened title window",
);
assert.ok(
  INTRO_TIMING.reportClipSeamBleed > 0,
  "title clip paths should overlap slightly at the center seam",
);

console.log("intro geometry checks passed");
