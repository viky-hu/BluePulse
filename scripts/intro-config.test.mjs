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

  assert.ok(
    panel.height > panel.width * 1.5,
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

const shortPanel = calculatePanelGeometry(320, 200);
assert.equal(shortPanel.height, shortPanel.width * 1.5);

const greenStart = INTRO_TIMING.reportGreenDelay;
const greenEnd = greenStart + INTRO_TIMING.reportGreenExpand;
const lineStart = greenEnd + INTRO_TIMING.reportGreenHold;
const lineComplete = lineStart + INTRO_TIMING.reportLineDraw;
const titleStart = lineComplete - INTRO_TIMING.reportTitleLead;
const titleComplete = titleStart + INTRO_TIMING.reportTitleReveal;
const eraseStart = lineComplete + INTRO_TIMING.reportLineHold;
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
  titleStart < lineComplete && titleComplete <= eraseStart,
  "title should begin before line completion and settle before erase",
);
assert.ok(
  INTRO_TIMING.reportLineHold >= 0.4 && INTRO_TIMING.reportLineHold <= 0.5,
  "line should remain complete only briefly before erasing",
);
assert.ok(
  eraseComplete >= 3.7 && eraseComplete <= 4.2,
  "report sequence should complete within the intended overall window",
);
assert.ok(
  INTRO_TIMING.reportClipSeamBleed > 0,
  "title clip paths should overlap slightly at the center seam",
);

console.log("intro geometry checks passed");
