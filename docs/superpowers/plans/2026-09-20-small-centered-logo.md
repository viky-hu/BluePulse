# Small Centered Logo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the existing animated Blue Pulse logo at a fixed 240px width while keeping its center point fixed at the center of the viewport.

**Architecture:** Preserve the full-screen CSS grid stage as the positioning owner and preserve the SVG and GSAP timeline as-is. Change only the SVG canvas sizing rule, so the browser scales the existing `viewBox` proportionally without altering geometry or animation behavior.

**Tech Stack:** Next.js 16.3.5 App Router, React 19.2.8, TypeScript, global CSS, GSAP 3.15.0 with DrawSVGPlugin.

## Global Constraints

- The rendered logo canvas width is exactly `240px` on desktop and mobile.
- The SVG height remains automatic, preserving the original `3621 / 4252` aspect ratio.
- The logo remains centered through the existing `.logo-stage { display: grid; place-items: center; }` rule.
- SVG paths, color, stroke treatment, and GSAP drawing timeline remain unchanged.
- No dependencies are added.

---

### Task 1: Fix the animated logo canvas at 240px

**Files:**
- Modify: `src/app/globals.css:33`
- Test: Browser acceptance check against `/`

**Interfaces:**
- Consumes: Existing `.logo-stage` center alignment and `.logo-canvas` SVG element.
- Produces: A `.logo-canvas` with a computed width of `240px` and proportional automatic height.

- [x] **Step 1: Run the acceptance check before implementation**

Start the existing development server and inspect `.logo-canvas` in the browser at desktop and mobile viewport sizes. Confirm the current computed width is not `240px`, establishing the expected failing state.

- [x] **Step 2: Implement the fixed size**

Replace the responsive width declaration in `src/app/globals.css`:

```css
.logo-canvas {
  display: block;
  width: 240px;
  height: auto;
  overflow: visible;
}
```

- [x] **Step 3: Verify browser behavior**

At desktop and mobile viewport sizes, verify all of the following:

```text
getComputedStyle(document.querySelector(".logo-canvas")).width === "240px"
logo center X === viewport center X
logo center Y === viewport center Y
the SVG paths visibly draw during the GSAP timeline
```

- [x] **Step 4: Run project validation**

Run:

```powershell
pnpm lint
pnpm build
```

Expected: both commands exit with code 0 and report no errors.

- [ ] **Step 5: Commit the implementation** *(left uncommitted to avoid bundling pre-existing user changes in `src/app/globals.css`)*

```powershell
git add -- src/app/globals.css docs/superpowers/plans/2026-09-20-small-centered-logo.md
git commit -m "style: reduce centered logo size"
```
