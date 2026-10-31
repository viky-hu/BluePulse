# Third-party notices

## AIHOT

Pulse 的浏览器状态、会话恢复和菜单实现移植参考了 AIHOT 开源框架的以下文件：

- `D:/AIHOT/apps/web/app/routes/hot.tsx`、`features/hot/{Sparkline,Delta}.tsx`、`features/hot/curve.ts`：完整热点榜主卡／副卡／列表、标题／窄屏操作、热度说明、原趋势／徽标、小时缺测分段及单调曲线绘制；Pulse对应 `src/app/hot/`，复用现有 `Faces/SourceAvatar/Badge`，仅调整警务文案、Next.js及p0内部滚动／内容宽度适配。`PhoneBar.tsx`、`app.css`为窄屏标题、原字号／颜色／圆角／阴影依据，未移植全站壳。`packages/contracts/src/site.ts`、`apps/api/src/routes/site.ts`、`packages/backend/src/publication/{hot,stories,scope,representative}.ts`、`events/{hot,group}.ts`为字段、公开证据、媒体／头像、独立参与方／趋势及后端交接依据；不移植React Router、Fastify、SQL或pg-boss。真实热榜与事件详情待后端实施，详见DOCK-007；源站品牌、第三方新闻全文及媒体权利不随软件MIT许可取得。

- `D:/AIHOT/apps/web/app/routes/home.tsx`、`features/feed/{Timeline,HotTopics,FeedItem,ReadingGroup,Filters,parts}.tsx`、`features/hot/Faces.tsx`、`components/ui/{SourceAvatar,Sheet,Lightbox,Presence,Badge,Tabs}.tsx`：精选首页信息层级、筛选／搜索、分日时轨和折叠、三批自动再手动加载、同新闻桌面展开／移动抽屉、原帖媒体／引用、收藏、入选标记、头像堆叠／名单／首字降级及热点趋势。Pulse 对应 `src/app/_components/{featured,feed}/`，并由 `/all` 共享工具栏／卡片／日期时轨；以 Next.js URL、p0内部滚动、内容宽度断点和既有浏览器状态适配，保留 Pulse 品牌、字体和封面。`packages/contracts/src/site.ts`、`apps/api/src/routes/site.ts`、`packages/backend/src/publication/{timeline,groups,hot,representative,scope,publish}.ts`、`events/{group,relate,hot}.ts` 为共享类型、读取语义及后端交接依据；未移植其 Fastify／PostgreSQL／pg-boss。Pulse 的 `_lib/feed-types.ts` 保留原外层形状并复用 UUID ArticleCard，后端实现和真实联调仍待队友完成，详见 DOCK-006。

- `D:/AIHOT/apps/web/app/routes/starred.tsx`、`components/ui/Presence.tsx`、`lib/local-state.ts`、`packages/backend/src/publication/availability.ts`：收藏页标题工具、提示及通知、空态、卡片、撤回／仅摘要信息、500条收藏与5000条已读、version 1 JSON 备份合并和独立批次核验。Pulse 对应 `src/app/starred/` 及 `browser-state.ts`，以 Next.js 和 p0 内部内容宽度适配，保留已有 UUID 与历史存储；外观偏好不应用，不移植 React Router、SQL 或第三方模块导入。`nav.ts`／`icons.tsx` 的收藏菜单和书签图形沿用现有菜单适配。

- `D:/AIHOT/apps/web/app/routes/all.tsx`、`features/feed/{Filters,DayList,FeedItem,Timeline,parts}.tsx`、`components/ui/{Tabs,IntentLink,Score,Page}.tsx`、`components/icons.tsx`：全部动态工具栏、分类单选、搜索快捷键、北京时间分日、吸顶日期、时间轴与阅读卡片、评分、收藏图标／反馈、空态及分页。Pulse 对应 `src/app/all/`，以 p0 内容宽度响应，使用 Next.js 路由、既有游标 API，原生滑块由 scoped useGSAP 管理；缺失分类、排序及统计明确交接，不复制原站品牌、React Router 或 PostgreSQL 读取。

- `D:/AIHOT/apps/web/app/components/shell/Chrome.tsx: NavigationProgress`：窗口顶部2px细线、150ms延迟与完成收尾；对应 Pulse `NavigationProgress.tsx`，补充静态减少动效及共享加载状态。
- `D:/AIHOT/apps/web/app/lib/page-reuse.ts`、`api.server.ts: cachedPage`：当前document复用与绝对截止思路；对应 `page-cache.ts`、`http-cache.ts`、资讯及关于页数据缓存。保留Pulse的60秒本地上限，遵守上游禁止缓存和已消耗时间，历史位置期限独立。

- `D:/AIHOT/apps/web/app/routes/changelog.tsx`、`features/changelog/text.tsx`、`components/ui/Page.tsx`：日期卡片、正文块、类型／月份目录、阅读双栏及右侧卡片；对应 Pulse `src/app/changelog/` 和 `_components/reading/`。
- `D:/AIHOT/apps/web/app/routes/feedback.tsx`：表单、单图选择／拖拽／粘贴、草稿和回执；对应 Pulse `src/app/feedback/`。`lib/local-state.ts`、`components/shell/Sidebar.tsx` 的已读红点与来源页记忆适配于 `_lib/site-state.ts`。
- `D:/AIHOT/packages/backend/src/site/meta.ts`、`apps/api/src/routes/site.ts`、HTTP ETag 实现与 `docs/customize.md`：版本化 JSON、元信息与条件缓存思路。Pulse 以 Next.js Route Handlers 提供，未复制 Fastify 或 SQL。反馈后端仅列入 dock.md 交接，没有移植飞书。

- `D:/AIHOT/apps/web/app/lib/local-state.ts`：匿名收藏、已读、存储降级、数据导入导出及跨标签页通知。
- `D:/AIHOT/apps/web/app/lib/restore.ts`、`session-cache.ts`：历史条目快照、30分钟会话恢复及滚动锚点。
- `D:/AIHOT/apps/web/app/components/shell/Sidebar.tsx`、`nav.ts`：菜单分组、条目布局、选中态与路由归属。
- `D:/AIHOT/apps/web/app/components/icons.tsx`：菜单使用的内联 SVG 图标。
- `D:/AIHOT/site/brand/Logo.tsx`：早期圆点与站名的字标排版参考；2026-10-27 已替换为 Pulse 自绘 C 稿路径字标与原有 qlxf 图形，不再使用该圆点排版。
- `D:/AIHOT/apps/web/app/routes/about.tsx`：关于页的标题与入口、统计阶段、最近精选、制作人和二维码卡片组成。
- `D:/AIHOT/apps/web/app/features/about/SignalRiver.tsx`：Canvas 信源曲线、汇束与闸门、报纸绘制、流光、命中判断和阶段高亮。Pulse 对应 `src/app/about/`，适配白纸滚动、GSAP React 生命周期、响应式尺寸与静态减少动效状态；新闻标题和团队内容替换为警务科技领域。

Pulse 对应实现为 `src/app/_lib/browser-state.ts`、`session-restore.ts`、`src/app/_components/home/navigation-config.ts`、`menu/` 及相关集成代码。具体移植范围与领域适配见 [源码研究](docs/aihot-understanding.md) 和 [后端阶段交接](docs/aihot-backend-stage-map.md)。后续复制 AIHOT 实质代码应继续保留以下完整许可与版权声明，并更新本文件的适用范围。

参考仓库：[KKKKhazix/AIHOT](https://github.com/KKKKhazix/AIHOT)。本轮研究使用无 Git 的本地下载快照，无法指定上游提交。AIHOT 名称和 Logo 不包含在其 MIT 软件许可中；Pulse 使用自身品牌。第三方新闻内容及字体等素材各自遵守其原有许可。

以下完整文字来自 `D:/AIHOT/LICENSE`：

```text
MIT License

Copyright (c) 2026 数字生命卡兹克

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
