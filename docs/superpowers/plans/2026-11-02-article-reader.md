# Pulse 单条新闻阅读页实施

目标：按本会话已批准方案，完整复用 AIHOT item／item-original、features/item、ArticleLayout 与原样式，适配 Pulse p0。

## 约束

- main 直接实施，保留开工已有未提交改动；不创建分支、worktree、PR，不改 Python 后端。
- 保持 Next.js 16／React 19／TypeScript／Tailwind 4／GSAP；不新增源站没有的产品功能。
- 阅读容器不足56rem单栏，56–76rem双栏，76rem起三栏；所有阅读滚动使用p0。
- 旧详情接口兼容；reader明确存在时优先执行其限制，不回退旧正文字段。Markdown／海报／OG及事件后续仅精确代理，不伪造真实内容。
- 当前document16项／60秒上限与上游截止取早，30分钟位置恢复独立；mock仅显式且隔离。
- 保留原MIT和Copyright (c) 2026 数字生命卡兹克。

## 任务与进度

- [x] 数据：reader契约、旧字段安全适配、示例、预览与缓存、精确代理及边界测试。
- [x] 阅读：原版文章版式、正文增强、侧栏、目录／进度、移动工具、原帖、分享与海报。
- [x] 集成：语言路由及replace导航、卡片预览、tag精确传递、元信息、p0内部滚动。
- [x] 交接：DOCK-009、README、研究／阶段记录、第三方声明。
- [x] 验证：逻辑、lint、生产构建、桌面／移动／reduced-motion聚焦浏览器检查及代码审查。

最终检查：32项相关逻辑、37项新闻阅读浏览器、13组共享导航回归，lint／生产构建通过。实际后端依赖与验证边界见docs/pulse-article-reader-verification-2026-11-02.md。
