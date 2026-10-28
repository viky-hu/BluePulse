<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# Blue Pulse Project Rules

## Git 协作约定

- 用户负责前端主线；Codex 为用户执行的前端及相关文档工作，直接在 `main` 开发和提交。工作开始及提交前都核对当前分支。
- 除非用户明确要求，不创建或切换前端功能分支、不创建 worktree、不引入 PR 流程。此约定优先于技能中的默认分支隔离建议；切换时保护现有改动，不丢弃工作。
- 后端由队友在其分支开发，完成后由用户决定并执行合并；不擅自修改、合并或删除队友分支。

## 项目主线与模块工作约定

- 主线：从 `D:/AIHOT` 尽可能完整地复用已选模块的真实实现，将其改造成国内外警务科技情报系统，并接入 Pulse 现有界面。
- 范围：以当前用户要求及 README 的最新具体菜单清单为准。早期设想和 AIHOT 原站栏目仅供参考；分组名不代表允许补齐所有条目。每个会话只处理指定模块及必要的共享适配。
- 本系统不设置独立“主题”菜单或内容模块，也不保留 `/topics` 页面；文章分类元数据及检索筛选属于现有阅读能力，不据此恢复主题栏目。
- “照搬复用”：优先复用实际组件、信息层级、交互状态、样式参数和成熟业务行为，再做必要适配；未经要求不另行设计、删减模块功能或只制作外观空壳。
- 界面映射：保留 Pulse 品牌、菜单、共享 p0 白纸和导航动效；移除原站重复的整页背景与外层框架，按 p0 容器重新编排，并适配内部滚动、吸顶、弹层及移动端。
- 领域改造：替换 AI 行业的信源、主题、机构、案例和文案，保留适用的通用机制。沿用既有技术栈，版本差异正常适配，不作为回避复用的理由。
- 开工：核对当前分支和未提交改动；阅读 README 的宏观规划、AIHOT 基础功能和具体菜单清单，再按研究索引阅读本模块的 AIHOT 原始源码及 Pulse 现状。研究记录不代替源码核对。
- 交付：简述“原始源码 → 复用内容 → Pulse 适配 → 验证结果”。缺失后端应列明接口依赖和真实状态；模块结论写回相关文档，不把静态研究、占位页面或测试数据当作业务完成。

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

## AIHOT adoption and required research

- Read `docs/aihot-understanding.md` and `docs/aihot-backend-stage-map.md` before implementing AIHOT-derived behavior. The evidence is a static, non-Git `D:/AIHOT` download snapshot checked on 2026-10-11; it is not a runtime or production validation.
- Reuse the selected modules' actual frontend implementations and business behavior within Pulse's existing Next.js/GSAP frontend and Python/FastAPI backend. Adapt framework integrations and contracts rather than transplanting React Router loaders, PostgreSQL SQL, or pg-boss.
- Public reading is anonymous. Browser bookmarks/read/history/preferences do not require normal user accounts or cloud sync. A future same-site `/admin` must have server-enforced admin sessions, CSRF, and audit; an existing account table or local command is not a completed admin backend.
- Never turn absent event/report/module APIs into fabricated results. The local AIHOT module lists are empty; online-only model rankings and monitors are not available implementations in this snapshot.
- For routes and HTTP integration read research §2 and §11, then `D:/AIHOT/apps/web/app/routes.ts`, `apps/api/src/routes/site.ts`, and `packages/contracts/src/site.ts`. For browser state/cache read §9 and `apps/web/app/lib/{local-state,restore,session-cache,page-reuse,api.server}.ts`; persistent preferences, 30-minute history restoration, and server-deadline page reuse are separate lifecycles.
- For collection/model work read §3–4 and §10, then `D:/AIHOT/packages/backend/src/content/materials.ts`, `editorial/analyze.ts`, `providers/receipts.ts`, and `operations/recover.ts`. Bind results to input/prompt versions, preserve human overrides, store paid-call results before business writes, and treat unknown outcomes explicitly.
- For events/selection/hot/reports read §5–8, then `D:/AIHOT/packages/backend/src/events/{group,relate,hot}.ts`, `reports/{edition,compose}.ts`, and `publication/{scope,publish,representative}.ts`. A score-qualified candidate waits for grouping; heat counts independent participants; a homepage six-slot edition is not a daily report.
- Every public exit must share visibility, release, withdrawal, evidence, and full-text permission policies. Read research §8–12 before adding RSS/MCP/Markdown/SEO/media or deploying; use the backend stage map to report actual gaps and dependencies.
- Preserve AIHOT's MIT notice and `Copyright (c) 2026 数字生命卡兹克` when copying substantial code. Its name/logo and third-party news full-text rights are not granted by that software license.
