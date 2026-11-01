# 关于页初始页入口实施计划

用户已确认：关于页顶部右侧增加“产品初始页 ↗”描边按钮，当前窗口重新播放初始动画；保留真实／演示模式和阅读数据。按项目约定直接在 main 操作，保留已有日报改动。

实现：在 AboutPulse 的独立顶部行放置标签和按钮，沿用 secondary 样式并约束手机端尺寸。按钮使用 browserKeys(mock).entry 清除对应完成标记，再以 location.assign(href("/")) 重新加载首页，使首帧 bootstrap 和 MainShell 一致初始化。点击立即禁用，存储操作失败时显示可重试状态。无需调整动画时间轴、Logo 或共享导航。

- [x] 修改 AboutPulse.tsx 和 about.module.css。
- [x] 运行 lint、生产构建；聚焦验证桌面、手机、reduced-motion 下按钮可见、重播、模式及阅读数据保留、完成后刷新稳定。
- [x] 将验证结果写回文档，只提交本次文件。

本次为低影响按钮增补，不增加镜像实现的单元测试；用真实浏览器完成交互检查。

## 验证结果（2026-11-01）

- 原始源码 → 复用内容：复用 Pulse AboutPulse 的 secondary 按钮、browserKeys 的模式隔离键，以及既有首页 bootstrap / RootEntry / InitialIntro；此入口不新增 AIHOT 业务能力。
- Pulse 适配：顶部标签与按钮独立横排行；只移除当前模式的 entry 标记，整页加载首页以保持首帧与 React 状态一致，重复触发有守卫，存储失败显示可重试提示。
- `pnpm lint`、`pnpm build` 均退出 0。
- Chromium 生产构建实测：1440×900 演示、390×844 演示、1440×900 真实模式 + reduced motion。按钮在视口内、无横向溢出；点击进入 `/` 并保留 mock 参数；当前模式标记清除，另一模式标记和阅读数据保留；可继续到主页面，完成后刷新无重播。无 pageerror。
- 已查看桌面及手机截图；产物在忽略目录 `test-results/about-intro/`。真实模式使用隔离本地 HTTP fixture，不涉及线上服务、采集或模型调用。本功能无新增后端依赖。
