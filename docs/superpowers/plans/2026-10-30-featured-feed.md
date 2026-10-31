# 精选页实施与进度

目标：将 AIHOT 精选真实组件及交互移植到 Pulse 的 p0 白纸，本轮仅前端及接口交接。

## 全局约束

- 直接在 main 开发提交，不创建分支、worktree 或 PR；保护已有 site/changelog.json 改动。
- AIHOT 源码为布局、组件、交互和样式真值，不增删小组件或额外说明行。保留 Pulse 品牌、字体、p0 几何、封面六槽和菜单转场。
- 精选和全部动态共用新闻卡片与工具栏；分类独立由 URL 控制。新 timeline 不能由全部动态或六槽接口替代。
- 新同源接口 site/timeline、site/groups/:factId/reports，仅白名单代理；FastAPI 留待队友按 DOCK-006 实现。
- 20条首批、最多40条；首批算在三批自动加载内；p0 滚动容器；760/600/640px 内容断点分别控制工具栏、卡片和热点。
- 当前热点、信源头像堆叠和趋势、日期折叠、归组展开/抽屉、原帖/媒体/引用条件分支均保留。
- 数据缓存最多60秒且不超过各批最早服务端截止；30分钟位置恢复独立；mock 显式且隔离。
- 保留 MIT 及 Copyright (c) 2026 数字生命卡兹克。

## 任务

- [x] 1. 共用 FeedToolbar、FeedItem、DayHeader、TimelineSlot 与原版归组/媒体组件；保持全部动态兼容。
- [x] 2. 新 timeline/types/mock/cache、精选编排/热点/连续加载、精确代理、事件待接入目标与导航。
- [x] 3. DOCK-006、README、研究索引、来源声明与专项验收记录。
- [x] 4. 逻辑、lint/build、桌面/移动/reduced-motion 浏览器检查和独立源码审查。

交付命令：核对 main 与提交范围，以 `完成’精选‘页搭建` 提交并 push；最终执行状态以 Git 提交和远端回执为准。

2026-10-31：上述四项已完成；42项逻辑、28组精选、18组全部动态、13组共享导航浏览器检查及 lint／生产构建通过，独立源码审查通过。验收记录为 `docs/pulse-featured-verification-2026-10-31.md`。
