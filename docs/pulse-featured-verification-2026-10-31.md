# 精选页源码复用与前端验收

验收日期：2026-10-31（Asia/Shanghai）；实施始于2026-10-30。分支为 `main`，范围为精选前端、必要共享组件／导航、同源代理及接口交接。没有修改 FastAPI、队友分支、Logo 几何、封面六槽接口或 p0 尺寸。

## 原始源码 → 复用内容 → Pulse 适配

原始证据为非 Git 的 `D:/AIHOT` 下载快照；本次直接阅读原文件，不把静态研究作为原站线上运行证明。

| AIHOT 原始源码 | 复用与适配 |
| --- | --- |
| `routes/home.tsx`、`features/feed/Filters.tsx` | 精选标题、分类／搜索、热点和时间线顺序；Pulse 分类分别由 URL 控制，菜单入口回全部，搜索与旧首页 q 链接进入 `/all`。 |
| `Timeline.tsx`、`DayList.tsx` | 北京时间分日、64px／22px时轨、吸顶日期、折叠、三批自动再手动加载、游标恢复和历史锚点；日期依既定要求无年份／今天，条数只使用服务端完整 `dayCounts`。 |
| `FeedItem.tsx`、`parts.tsx`、`ReadingGroup.tsx`、`Badge.tsx` | 来源、标题、摘要、理由、评分、收藏／已读、精选与同新闻标记／链接；原帖作者／头像／媒体／引用；桌面其他报道展开与移动抽屉。精选和 `/all` 使用同一 FeedItem，全部动态保留标签与原游标分页。 |
| `HotTopics.tsx`、`hot/Faces.tsx`、`SourceAvatar.tsx` | 背景与圆点、完整榜单、排名、标题、六个 editorial 头像和余量、名称提示、热度与趋势；窄容器按原版隐藏头像列并显示前三条，不自算业务数据。 |
| `Sheet.tsx`、`Lightbox.tsx`、`Presence.tsx`、`modal.ts` | 原关闭／拖动／键盘／出入场机制；portal 到 body，锁定 p0 和 document 滚动，焦点限制与返回、减少动效。 |
| 契约、站内 API、`publication/{timeline,groups,hot,scope,publish,representative}.ts` | 时间线、同范围代表／证据／计数及热点语义；建立 Pulse UUID 契约，不复制 React Router loader、SQL 或 worker。 |

共用实现位于 `src/app/_components/feed/`，精选编排位于 `_components/featured/`。内容断点760px／600px／640px分别控制工具栏、卡片／时轨、热点列。保留控件尺寸、信息层级、字体与品牌，无额外辅助说明行或虚构统计组件。MIT 完整许可与版权见 `THIRD_PARTY_NOTICES.md`。

## 验证结果

| 检查 | 结果 |
| --- | --- |
| `pnpm lint` | 通过，0 error／warning |
| `pnpm build` | 生产构建、TypeScript 和路由生成通过 |
| 精选／归组、全部动态、URL、导航状态、缓存、浏览器状态和收藏逻辑 | 42项通过 |
| `scripts/featured-feed-browser-test.mjs` | 28组通过，浏览器异常0；1360×760桌面、390×844移动、桌面 reduced-motion |
| `scripts/all-feed-browser-test.mjs` | 18组通过；筛选／搜索、收藏／已读、分页、日期吸顶和返回位置通过 |
| `scripts/navigation-loading-browser-test.mjs` | 13组通过；首访慢精选、加载条、改跳／晚到隔离、刷新、意图预取、no-store与过期恢复通过 |
| 独立源码审查 | 共用组件、完整变更和交接文档通过；发现的问题已修正并纳入聚焦浏览器检查 |

逻辑复现：

```powershell
node --test scripts/featured-feed.test.mjs src/app/_components/feed/group-request.test.mjs scripts/home-routes.test.mjs scripts/home-view-transition.test.mjs scripts/page-cache.test.mjs scripts/http-cache.test.mjs scripts/browser-state.test.mjs scripts/all-feed.test.mjs scripts/starred-state.test.mjs scripts/starred-availability.test.mjs
```

浏览器脚本启动独立 Next 生产服务和本地确定性 HTTP 服务，不启动采集、模型或通知。导航脚本的首次等待目标已随真实数据入口更新为 `site/timeline`。Playwright 沿用既有运行时，可用 `PULSE_PLAYWRIGHT_MODULE` 指定路径。Node 的既有 `MODULE_TYPELESS_PACKAGE_JSON` 提示保留，没有为消除提示改动 package.json。

截图和请求／检查回执位于忽略目录 `test-results/featured-feed/`、`test-results/all-feed/` 和 `test-results/navigation-loading/`。桌面、移动与 reduced-motion 截图已查看；p0 没有横向溢出，控件通过换行／横向滚动保留尺寸。

## 核查并修正的问题

- 下一批请求期间折叠日期，返回后曾覆盖新折叠状态；现在追加到最新状态，以挂起游标请求验证。
- 上方打开的阅读组在返回时重新请求，延迟500ms曾造成328px锚点漂移。现在组在 layout 阶段登记恢复等待，待 no-store 核验、原240ms展开及布局帧完成后统一恢复锚点；退出清理释放等待，不持久化报道正文。
- 弹层内斜杠曾把焦点送到背后的搜索框；现在尊重活动模态层，抽屉／灯箱已验证 Tab、斜杠、Escape和焦点返回。
- 当前精选菜单刷新回到最新首批和顶部；游标400在连续加载及过期历史重建时回首批，保留最早截止，并不重新套用旧日期折叠。
- 缓存到期测试使用继续走时的系统时钟，避免冻结 GSAP 的 Date.now 时间源；没有为测试时钟修改产品动画参数。

## 真实状态与未完成依赖

本轮证明前端消费、精确代理和受控接口行为。正式 `site/timeline` 与 `site/groups/:factId/reports` 待 FastAPI 实施；404显示待接入，200空结果与503／格式错误分别处理，没有用全部动态、六槽精选或 Mock 自动填补正式页面。

`/?mock=1` 只演示界面，缓存与本地收藏／已读隔离。`/story/:publicId` 保留原热点事件去向，目前仅显示待接入状态，不能作为完整事件模块交付。

后端的 Fact／Story、候选与确认门禁、稳定 anchor、同范围代表／报道／分日数量、独立参与方热度、来源时钟、头像及发布／撤回／全文许可见根目录 DOCK-006。真实契约、数据库迁移及生产联调须由后端另行验收。
