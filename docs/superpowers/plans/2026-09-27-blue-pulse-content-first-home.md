# Blue Pulse 内容优先主页与 Mock 全动画 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Blue Pulse 主页面改为直接呈现资讯内容的桌面/移动界面，按 Branched Menu 示例实现稳定展开的分支主题菜单，全站统一使用钉钉进步体，并让 `/?mock=1` 仍从封面完整播放 GSAP 入场后进入固定 Mock 数据主页。

**Architecture:** 让 `mock` 只决定数据源，不再决定是否跳过 `InitialIntro`。`InitialIntro` 继续负责唯一的封面与过场时间轴，完成过场后挂载 `HomeDashboard`。`HomeDashboard` 负责页面状态和数据编排，拆出一个只负责树形导航绘制与选择的 `BranchedTopicMenu`，把精选、资讯流、详情、历史和演示账号作为紧凑内容模块渲染到 p0 白纸内部。样式继续使用现有 CSS Modules 和全局基础样式，不引入新的 UI、图标或动画库。

**Tech Stack:** Next.js 16.3.5 App Router、React 19.2.8、TypeScript、Tailwind CSS 4、GSAP 3.15.0、`@gsap/react`、`next/font/local`、CSS Modules。

## Global Constraints

- 保留 Next.js 16、React 19、TypeScript、Tailwind CSS 4、GSAP 3 和现有同源 API 转发；不增加 UI 或动画库。
- 修改 Next.js 代码前阅读 `node_modules/next/dist/docs/` 中对应的本地指南；修改 GSAP 前遵循 `useGSAP`、scope、`contextSafe` 和 cleanup 规则。
- `qlxf.svg` 的 `0 0 3621 4252` viewBox、三个闭合 path、每个原始 `d` 值和 `vector-effect="non-scaling-stroke"` 保持不变。
- 主页面不使用顶部主视觉，不增加营销式大标题、英文眉题、装饰性副标题或多行说明；页面优先呈现日期、来源、标题、摘要和媒体。
- 主页面精选固定对应六个位置：p0 = top1，p1 = top2，p2 = top3，p3 = top4，p4 = top5，p5 = top6；生产数据按后端顺序，Mock 数据固定六条。
- 资讯卡片只有在 `media_preview.kind === "image"` 且存在可用 URL 时显示右侧缩略图；没有图片时不显示图片占位。
- 默认资讯时间范围为近 7 天；保留 24 小时、7 天、30 天切换，以及后端已支持的关键词、主题、地区、来源、来源类型、排序和 cursor 分页。
- 主题树始终全部展开，不能通过点击上级项折叠；菜单尺寸在选择主题后保持稳定。
- 左侧菜单是有外边距的直角矩形浮层，不从屏幕边缘长出；移动端通过按钮打开浮动菜单。
- 用户要求所有可见文字统一使用钉钉进步体。项目没有找到该字体文件，只有 `admin/csy` 中的字体栈写法；在字体文件实际提供前，不声称已经完成真实字体渲染。
- `/?mock=1` 只切换到固定 Mock 数据，不请求后端，也不跳过封面动画；生产路径不能在请求失败时混入 Mock 内容。
- 提供 loading、empty、error、缺正文和缺媒体状态；不做大范围性能捕获或无关回归测试。

---

### Task 1: 准备钉钉进步体并统一字体入口

**Files:**
- Create: `src/app/fonts/DingTalkJinBuTi.woff2`（由用户提供的实际字体文件复制而来）
- Modify: `src/app/layout.tsx`
- Modify: `src/app/globals.css`
- Modify: `src/app/_components/intro/intro.module.css`
- Modify: `src/app/_components/home/home.module.css`

**Interfaces:**
- Consumes: 用户提供的可合法使用的钉钉进步体字体文件；现有 Google Sans 变量字体。
- Produces: `--font-dingtalk-jinbu` 全局字体变量；封面、菜单、白纸内容、按钮、表单和详情页都通过同一字体 token 渲染。

- [ ] **Step 1: 确认字体文件来源**

  在开始复制文件前确认用户提供的 `.woff2`、`.woff`、`.ttf` 或 `.otf` 路径，或确认允许从官方渠道取得。若没有文件，只记录 CSS 字体名和回退栈，不把该阶段标记为完成。

- [ ] **Step 2: 注册本地字体**

  在 `layout.tsx` 增加 `next/font/local` 配置，使用固定文件路径、`display: "swap"`、`variable: "--font-dingtalk-jinbu"`，并把变量类与现有 Google Sans 变量类同时挂到 `<body>`。如果提供的文件不是可变字体，使用它真实支持的单一 `400` 权重，不伪造 `400 700` 范围。

- [ ] **Step 3: 让钉钉进步体成为全局首选**

  将 `globals.css` 的 body、表单控件和 feature CSS 中所有 `Google Sans`/`Microsoft YaHei` 首选声明改为：

  ```css
  font-family: var(--font-dingtalk-jinbu), "DingTalk JinBuTi", var(--font-google-sans), "Google Sans", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
  ```

  删除 intro/home CSS 中单独的 Microsoft Rounded 或 Google Sans 首选，避免同一页面出现多套中文字体。

- [ ] **Step 4: 检查字体覆盖面**

  用页面 DOM 和 computed style 检查封面 SVG text、菜单、资讯标题、日期、详情正文、表单和移动端按钮均继承同一字体变量；没有字体文件时在执行记录中保留未完成的字体资源门槛。

### Task 2: 将 Mock 数据源与封面播放状态彻底分离

**Files:**
- Modify: `src/app/page.tsx`
- Modify: `src/app/_components/intro/InitialIntro.tsx`
- Test: `/?mock=1` 和 `/`

**Interfaces:**
- Consumes: `mockData: boolean` 属性；现有 `InitialIntro` GSAP timeline、reduced-motion 分支和 `HomeDashboard` mock 数据开关。
- Produces: 两条入口都从 `boot` 开始；`mockData` 只传给 `HomeDashboard`，不影响 timeline 是否创建或播放。

- [ ] **Step 1: 改名并收窄入口语义**

  在 `page.tsx` 解析 `searchParams.mock === "1"` 后渲染 `<InitialIntro mockData={mock} />`。在 `InitialIntro` 中将 `startInMain` 重命名为 `mockData`，并以该属性只控制 `<HomeDashboard mock={mockData} />`。

- [ ] **Step 2: 删除 Mock 跳过路径**

  `mainReady` 初始值固定为 `false`，根节点 `data-phase` 初始为 `boot`。删除 `useGSAP` 中根据 Mock 直接 `updatePhase("main")` 并 return 的分支；保留正常的 logo 绘制、panel 展开、白纸过场、按钮触发和 `startMainTransition`。

- [ ] **Step 3: 保留减少动态效果路径**

  在 `prefers-reduced-motion: reduce` 时继续跳过中间运动但显示一个完整、可用的静态主页；不因 `mockData` 改变 reduced-motion 行为。所有 timeline、resize listener、font-ready callback 和 delayed callback 继续由 `useGSAP` scope 清理。

- [ ] **Step 4: 验证 idempotent transition**

  确认按钮、键盘激活和重复点击都进入同一个受保护的 transition action；第一次触发后禁用或忽略后续输入；Mock 和生产两条路径都只完成一次从 `complete` 到 `main` 的过场。

### Task 3: 收紧 HomeDashboard 边界并修复当前 lint 风险

**Files:**
- Modify: `src/app/_components/home/HomeDashboard.tsx`
- Create: `src/app/_components/home/home-types.ts`
- Create: `src/app/_components/home/BranchedTopicMenu.tsx`
- Modify: `src/app/_components/home/home.module.css`

**Interfaces:**
- Consumes: `ArticleCard`、`Topic`、`Source`、`ArticleDetail` 及现有 fetch/mock helpers。
- Produces: `BranchedTopicMenu` 接口 `({ topics, activeSlug, status, onSelect })`；HomeDashboard 继续暴露 `({ mock?: boolean })`，页面导航状态仍用 `PageView | article` 判别联合。

- [ ] **Step 1: 把本地 UI 类型集中到 feature 文件**

  将 `PageView`、`ActiveView`、`ListStatus`、`DetailStatus`、`HistoryEntry` 和 `Filters` 移到 `home-types.ts`，保留明确的联合类型和现有 API 类型导入；不要引入 `any` 或全局状态库。

- [ ] **Step 2: 去除 render 阶段 ref 写入**

  将 `articleCardsRef.current = [...]` 从组件 render 主体移到依赖 `[articles, featured, history]` 的 effect，或改用稳定的 `useMemo` 数据源并在读取处使用该数据源，满足 React hooks refs 规则。删除未使用的 `currentPage` 局部变量。

- [ ] **Step 3: 让 Mock 列表和详情使用派生值**

  Mock 列表页由 `useMemo` 根据 `filters`、`pageIndex` 计算当前页和 cursor，避免 effect 首次执行时同步连续 `setState`；Mock 详情由当前 article id 直接派生，不在 effect 中同步写入 detail/status。生产请求仍使用 AbortController，并在 cleanup 中取消请求。

- [ ] **Step 4: 保留原页面状态恢复**

  进入详情前把当前内容区 scrollTop 按 view key 保存；返回时恢复对应列表、筛选、主题和滚动位置；历史记录最多保留 30 条并继续使用本地浏览器存储。

### Task 4: 按 Branched Menu 示例重建固定展开主题菜单

**Files:**
- Create: `src/app/_components/home/BranchedTopicMenu.tsx`
- Modify: `src/app/_components/home/HomeDashboard.tsx`
- Modify: `src/app/_components/home/home.module.css`

**Interfaces:**
- Consumes: `Topic.parent_id`、`Topic.slug`、`Topic.name_zh`、主题请求状态和 HomeDashboard 的 `setTopic`。
- Produces: `nav` 元素中的主干、分支路径、活动标记和叶子按钮；所有上级节点常开且不可折叠，叶子选择调用 `onSelect(topic)`。

- [ ] **Step 1: 按 parent_id 构造稳定树**

  保留后端返回顺序，先建立 root topics，再把 `parent_id` 匹配到的子项放入对应 root；没有父项的条目作为 root，无效 parent_id 的条目放入最后一个稳定分组，不能静默丢弃。

- [ ] **Step 2: 绘制 Branched Menu 几何**

  参考 `D:/pulse/Branched Menu.txt` 的 `trunkPath`、`branch`、`reach` 和活动 marker 思路，在 React 中用一个相对定位的 SVG 绘制主干与每条分支；分支行高、缩进、线宽写成 CSS variables，菜单高度由完整树一次计算，禁止折叠动画改变布局。

- [ ] **Step 3: 定义菜单交互和可访问性**

  每个叶子使用 `button`、`aria-current="page"` 和可见 focus 样式；上级文字使用不可交互的 `div`/`span`，不能触发折叠。活动分支使用 accent color 和 marker，未选分支使用 muted color。主题选择同步 `filters.topic`、分页 cursor、右侧资讯列表和当前 view。

- [ ] **Step 4: 组合完整菜单顺序**

  按 README 的顺序渲染：顶部“图标｜资讯搜索”按钮 → 固定展开主题树 → 保留未规划的空白区 → “图标｜浏览记录”按钮 → 底部“图标｜访客阅读”账号按钮。桌面浮层不贴边，移动端由 menu button 打开，scrim 关闭。

### Task 5: 把 p0 白纸改成内容优先的信息模块

**Files:**
- Modify: `src/app/_components/home/HomeDashboard.tsx`
- Create: `src/app/_components/home/FeaturedList.tsx`
- Create: `src/app/_components/home/ArticleList.tsx`
- Modify: `src/app/_components/home/home.module.css`

**Interfaces:**
- Consumes: `featured`、`articles`、`ListStatus`、`openArticle`、`StoryMeta`、`ArticleCard.media_preview`。
- Produces: 六条精选列表、近期资讯流、主题/搜索结果列表；每条均支持进入文章详情并共享同一返回状态机制。

- [ ] **Step 1: 用六条紧凑精选替换 lead story**

  删除 `leadStory`、`featuredRail` 和大图主卡结构，渲染 `featured.slice(0, 6)` 为连续六行，行标记严格为 `TOP 1` 到 `TOP 6`，并按数组顺序对应 p0 到 p5。每行显示日期、来源、地区、中文标题和最多两行摘要；有图片时只在右侧显示小缩略图。

- [ ] **Step 2: 处理精选不足、为空和失败**

  生产返回少于六条时保留缺位行并显示“暂未有精选资讯”，不拿普通列表文章补位；返回空数组显示明确空状态；请求失败显示错误和重试按钮。Mock 必须始终提供六条固定样例。

- [ ] **Step 3: 让近期资讯紧接精选出现**

  精选之后直接渲染近期资讯流，默认 period 为 `7d`；用紧凑工具条切换 `24h`、`7d`、`30d`。资讯行显示日期、来源、地区、标题和可选摘要/主题，只有图片媒体才显示缩略图；保留 cursor 上一页/下一页。

- [ ] **Step 4: 删除主视觉式页面文案**

  移除 `pageHeader` 中的大标题、英文 eyebrow、长副标题和 header signal。必要的当前视图信息放进一行小型工具栏；不要添加“今天值得先看”“公开资讯观察”“持续追踪”等宣传式说明。

- [ ] **Step 5: 保持详情是实质内容页**

  详情页直接呈现中文标题、原题、日期、来源、摘要、主题、可用媒体、中文正文/译文、原文内容（可用时）和原文链接。正文缺失时保留阅读页并明确说明；详情返回恢复原列表与 scrollTop，不重置筛选。

### Task 6: 精简搜索、历史和演示账号模块

**Files:**
- Modify: `src/app/_components/home/HomeDashboard.tsx`
- Modify: `src/app/_components/home/home.module.css`

**Interfaces:**
- Consumes: 现有 `filters`、`history`、`sources`、`topics`、`navigate` 和 `detailBack`。
- Produces: 与菜单按钮一一对应的搜索、历史、账号内容模块；不接真实登录或注册。

- [ ] **Step 1: 搜索页只保留可用筛选**

  保留关键词、时间、主题、地区、具体来源、来源类型和排序控件；厂商/模型筛选在后端未提供能力前不显示。搜索提交后只更新 `q` 和列表，不插入额外介绍段落。

- [ ] **Step 2: 历史页改成直接记录列表**

  用来源、地区、阅读时间、标题和可选摘要组成紧凑列表，保留清空按钮、空状态和点击进入详情；删除英文 trail 文案和大块历史 hero。

- [ ] **Step 3: 账号页保持演示资料**

  显示访客状态、已读数量、可浏览主题数量、来源数量和“账号功能尚未开放”；不增加登录、注册、认证请求或个人推荐。

- [ ] **Step 4: 清理装饰性英文文案**

  删除 `FIELD NOTE`、`THE DAILY BRIEF`、`LATEST SIGNALS`、`TOPIC STREAM`、`PUBLIC READER` 等非必要眉题；保留来源、地区、日期、原始出处等真实内容标签。

### Task 7: 重做 CSS 为直角浮层与稳定内容区

**Files:**
- Modify: `src/app/_components/home/home.module.css`
- Modify: `src/app/globals.css`

**Interfaces:**
- Consumes: Task 4–6 的 class names 和现有 p0 白纸布局。
- Produces: 桌面/移动/减少动态效果三种稳定视觉状态。

- [ ] **Step 1: 定义布局 token**

  用 CSS variables 定义背景、墨色、分隔线、绿色 accent、菜单宽度、内容内边距、行高和 z-index；桌面菜单使用 `width: clamp(...)`、外边距和 `border-radius: 0`，内容区占右侧约三分之二并在自身滚动。

- [ ] **Step 2: 设计内容行而非卡片堆叠**

  精选和资讯流使用单层列表、细分隔线、明确 hover/focus 和有限的缩略图列；不使用圆角卡片套卡片、巨大数字、渐变背景或多层阴影。p0 白纸保持可读白底和独立滚动条。

- [ ] **Step 3: 响应式约束**

  桌面保留浮动菜单与白纸并排；窄屏把内容扩展到全宽，菜单改为带 scrim 的浮动抽屉，菜单树仍完整展开且不改变内部行高。不得用物理 `cm` 等单位。

- [ ] **Step 4: reduced-motion 和 focus**

  在 `prefers-reduced-motion: reduce` 下取消菜单分支绘制过渡、列表 hover 位移和抽屉滑动，只保留颜色/可见性变化；所有按钮、链接、输入框提供明显 focus-visible 样式。

### Task 8: 最小必要验证与交付检查

**Files:**
- Verify: `src/app/page.tsx`
- Verify: `src/app/_components/intro/InitialIntro.tsx`
- Verify: `src/app/_components/home/HomeDashboard.tsx`
- Verify: `src/app/_components/home/BranchedTopicMenu.tsx`
- Verify: `src/app/_components/home/home.module.css`

**Interfaces:**
- Consumes: 完成的页面、Mock 数据、生产 API 转发和动画状态。
- Produces: 可供用户打开审批的 `/?mock=1` 预览及生产首页。

- [ ] **Step 1: 运行必要静态检查**

  运行 `pnpm lint` 和 `pnpm build`；修复本计划涉及的 hooks、TypeScript、CSS module 和 Next.js 16 报错后再继续，不扩展到无关测试。

- [ ] **Step 2: 检查 Mock 动画**

  打开 `http://localhost:3000/?mock=1`，确认从 logo 绘制、封面白纸和按钮反馈开始，点击后完成过场进入六条精选；刷新后不能直接落在主页面。

- [ ] **Step 3: 检查生产错误隔离**

  打开 `/`，确认真实精选、分类、来源和文章请求分别显示 loading/empty/error；后端失败时不出现 Mock 标题。详情请求失败仍保留返回列表按钮。

- [ ] **Step 4: 做代表性视觉检查**

  在一个桌面尺寸和一个移动尺寸分别检查菜单悬浮位置、六条精选顺序、p0 内滚动、搜索/主题/历史/详情返回；启用减少动态效果后确认主页和交互仍可用。

- [ ] **Step 5: 检查不可变 SVG**

  用 `git diff -- qlxf.svg` 确认没有几何、viewBox、path 或 `vector-effect` 变化。

## README「主页面具体内容设计」逐句检查清单

- [ ] 已阅读并遵循 `docs/system-construction-outline.md`，按系统目标、信息架构和 Stage1 边界设计页面。
- [ ] 已对照 `docs/stage1-backend-plan.md` 与已合入的组员代码，确认前端接入精选、分类、来源、文章列表和详情能力。
- [ ] 已明确主页面展示内容及其顺序，并让菜单选择与白纸内容联动。
- [ ] 左侧已预留主页菜单区域；右侧约三分之二是 p0 白纸内容主体，主页面内容都在其中呈现。
- [ ] 菜单布局、菜单项顺序、样式和交互已经确定，并遵循适用的前端 skills 与官方实践。
- [ ] 菜单整体是独特的直角矩形，视觉上浮在背景之上，不从屏幕边缘延伸出来。
- [ ] 菜单项采用“图标｜字样”的形式。
- [ ] 菜单顶部放置资讯搜索入口，点击后右侧切换到搜索页。
- [ ] 搜索后放置资讯分层分类区域，分类与右侧资讯内容联动。
- [ ] 分类树稳定保持全部展开，不允许点击上级项折叠或展开，菜单尺寸不会频繁变化。
- [ ] 分类模块按分类层级安排空间，并以仓库中的 Branched Menu 为结构参考完成 React 实现。
- [ ] 已设置浏览历史入口，点击后右侧切换到历史记录页。
- [ ] 已保留未规划的菜单空间，没有擅自增加额外栏目。
- [ ] 菜单底部放置账号入口，点击后右侧切换到账号信息页。
- [ ] 已为未来登录功能保留账号页位置，本次没有接入真实登录。

## 用户反馈专项检查清单

- [ ] 页面没有顶部主视觉式大标题、装饰性副标题或多行营销文案，内容模块直接开始。
- [ ] 精选不再使用一个巨大的 lead story；六条 top1–top6 以同一信息密度呈现。
- [ ] `D:/pulse/Branched Menu.txt` 的主干、分支、活动路径和稳定展开逻辑已体现，菜单没有被替换成自定义的平面按钮列表。
- [ ] 全站可见文字使用钉钉进步体文件；字体文件缺失时没有把回退字体误报为钉钉进步体。
- [ ] `/?mock=1` 从头播放正常封面动画，Mock 只影响数据，不影响动画路径。
- [ ] 生产数据失败、为空或超时时没有混入固定 Mock 样例。

