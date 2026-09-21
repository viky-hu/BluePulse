<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# Blue Pulse Project Rules

## Technology and source of truth

- Keep the existing stack: Next.js 16, React 19, TypeScript, Tailwind CSS 4, and GSAP 3 with `@gsap/react`.
- Before changing Next.js code, read the relevant local guide under `node_modules/next/dist/docs/`. Do not rely on conventions remembered from older Next.js versions.
- Before changing animation code, inspect the relevant GSAP Skills, the current implementation, and the repository's animation notes. Prefer official GSAP APIs and plugins over rebuilding solved behavior.
- Treat `qlxf.svg` as immutable Logo geometry truth. Preserve its `0 0 3621 4252` viewBox, all three closed paths, every original `d` value, and `vector-effect="non-scaling-stroke"`.

## Typography

- Use the repository's local Google Sans variable font for English UI text. Expose it through `next/font/local`; do not introduce a runtime dependency on Google Fonts.
- Google Sans supports weights 400 through 700, but cover and display typography defaults to 400 unless the design explicitly calls for another weight.
- Use `"Microsoft YaHei"` as the primary Chinese fallback.
- Large display titles should be isolated scene elements rather than ordinary page copy. They default to regular weight and zero letter spacing.

## Layout and responsive design

- The desktop design reference is a 34 x 19 viewport measured from the user's full-screen laptop. Translate these measurements into viewport-relative ratios; do not use CSS physical units such as `cm`.
- Define separate, viewport-safe mobile constraints. Do not mechanically reuse desktop measurements on narrow or short screens.
- Keep fixed-format visual elements stable with explicit viewBox, aspect-ratio, or min/max constraints so animation state never changes layout unexpectedly.

## SVG scene composition

- For a moving color boundary that changes artwork or text color, use two coordinate-identical SVG scenes: a base scene and an alternate-color scene clipped by the same animated `clipPath` as the covering color field.
- The reference login title currently uses duplicated SVG `<text>` elements, not outlined glyph `<path>` data. Do not describe it as converted-to-path lettering.
- When animating SVG title characters, keep matching `<tspan>` nodes aligned by index across both scenes and animate each pair together.
- Preserve source SVG geometry and viewBox data when moving assets into components. Animation wrappers may transform presentation, but must not rewrite geometry casually.

## Animation lifecycle

- Use `useGSAP` with a component scope for React animation work. Clean up timelines, observers, listeners, delayed/font-ready callbacks, and resize handling when the component unmounts.
- Prefer transforms and opacity for motion. Avoid layout thrashing, and reserve `will-change` for elements that are actively animated.
- Provide a meaningful `prefers-reduced-motion` path. It must show a coherent static state and keep required interactions functional.
- Make one-shot transitions idempotent: route every input method through one guarded action, disable inputs as soon as the transition starts, and ignore duplicate requests.
- When viewport geometry changes, preserve normalized animation progress rather than restarting the experience.

## Component and file boundaries

- Keep route files thin. Co-locate page-specific components, animation orchestration, configuration, and CSS Modules near the route or feature that owns them.
- Separate visual primitives from the timeline orchestrator. Do not accumulate an entire page, all SVG markup, interaction handling, and animation logic in one TSX or global CSS file.
- Use global CSS only for true application-wide foundations. Keep feature styling in local modules.
- Build reusable visual elements with explicit props instead of coupling them to page-global selectors or mutable singleton state.

## Validation focus

- Put the majority of implementation effort into frontend composition and motion quality.
- At minimum, run lint and a production build after changes, then perform focused checks at one representative desktop viewport, one mobile viewport, and with reduced motion enabled.
- Do not expand routine visual work into a large browser matrix, long performance capture, or unrelated regression suite unless the change's risk requires it or the user asks for it.
