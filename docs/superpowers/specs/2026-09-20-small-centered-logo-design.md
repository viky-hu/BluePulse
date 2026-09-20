# Small Centered Logo Design

## Goal

Keep the existing Blue Pulse logo exactly centered while reducing its rendered size to a small icon.

## Design

- Preserve the SVG `viewBox`, path geometry, color, stroke treatment, and GSAP drawing timeline.
- Preserve the full-screen grid stage and its center alignment.
- Set the rendered logo canvas width to a fixed `48px`; retain automatic height so the original aspect ratio is unchanged.
- Use the same size on desktop and mobile so the logo remains a deliberately small, stable focal point.

## Scope

Only the `.logo-canvas` sizing rule in `src/app/globals.css` changes. No component, asset, dependency, or animation changes are required.

## Verification

- Run lint and production build.
- Inspect the page at desktop and mobile viewport sizes to confirm the logo remains centered and the drawing animation still runs.
