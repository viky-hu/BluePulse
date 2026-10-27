# Pulse 菜单栏改造验收

日期：2026-10-27。范围按用户最新选择修正为内容五项与更多四项，以及 Pulse 字标、导航落点、主题目录及全部动态。本轮沿用既有入场和共享 p0 导航。原先错误补齐的模型榜、Tibo 重置监控及其占位路由已移除。

## 已交付

- 顶部 Pulse 字标与搜索固定，内容／更多两组共9个栏目在独立区域滚动。AIHOT 菜单行高、字号、SVG图标、分组和选中态已适配至 Pulse 悬浮直角白底菜单；Google Sans及微软雅黑继续使用本地配置。
- 内容为精选、全部动态、热点榜、AI日报、主题；更多为 Agent 接入、关于、更新日志、反馈。没有模型组与模型榜／重置监控入口。
- 新增 `/all`、`/hot`、`/daily`、`/topics`、`/agent`、`/about`、`/changelog`、`/feedback`，均进入共享 p0 与导航就绪流程。
- 关于页已填写 Pulse 的系统介绍，更新日志已记录真实交付变化；Agent 接入和反馈保留入口和建设状态。
- 分类树移至主题目录，分类子页高亮“主题”；旧 `/articles` 高亮“全部动态”。历史、收藏、实体与文章详情原地址继续可用。
- 全部动态使用现有文章接口，默认30天，筛选和分页游标进入URL；重置恢复30天。尚未迁移的栏目显示建设状态，不产生榜单、报告或提交操作。
- 移动菜单支持遮罩、Escape关闭与焦点返回；关闭状态使用 inert。缩放跨断点后恢复正确的可用状态，菜单与场景DOM保持原实例。
- `THIRD_PARTY_NOTICES.md` 补充 Sidebar/nav/icons/Wordmark 来源，保留原MIT完整声明。

## 验证证据

| 检查 | 结果 |
| --- | --- |
| `pnpm lint` | 通过，无错误或警告 |
| `pnpm build` | 通过；TypeScript与全部新路由生成成功 |
| 前端逻辑 | 14项通过，包含README明确清单与菜单逐项对照、未选路由拒绝、选中归属与全部动态默认查询 |
| 主浏览器检查 | 39项通过，未捕获异常0，覆盖未选模型路由404、关于页正文及更新日志 |
| 响应式专项 | 5项通过，未捕获异常0 |
| 视觉检查 | 已查看1360×760桌面、390×844移动菜单及分类内容、reduced-motion截图 |

浏览器使用隔离的生产 Next 服务和确定性 HTTP 测试服务，没有启动采集、付费模型或推送。主检查覆盖首访／回访、全部菜单入口、直达／刷新／后退／前进／Ctrl点击、快速连续导航、p0滚动恢复、收藏／历史／跨标签同步、存储受限、撤回与availability失败。新增全部动态检查覆盖HTTP参数、默认30天、筛选、游标和刷新。

专项在1360×480短窗口中验证分组滚动时搜索位置固定，以及768px断点两侧的关闭／打开状态、键盘焦点可见性、Escape焦点返回及共享场景不重建。

## 复现命令

```powershell
pnpm lint
pnpm build
node --experimental-strip-types --test scripts/intro-config.test.mjs scripts/white-paper-config.test.mjs scripts/topic-menu-config.test.mjs scripts/home-view-transition.test.mjs scripts/home-routes.test.mjs scripts/browser-state.test.mjs
$env:PULSE_PLAYWRIGHT_MODULE='C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright\index.mjs'
node --experimental-strip-types scripts/home-transition-browser-test.mjs
node --experimental-strip-types scripts/sidebar-responsive-browser-test.mjs
```

浏览器产物：`test-results/pulse-sidebar/verification.json`、`responsive/verification.json`及对应PNG（仓库忽略）。主脚本使用3100/3101端口，专项使用3110端口，退出时关闭自己的服务。

检查使用本地契约测试数据；热点、报告、Agent接入及反馈服务不在本轮业务完成范围。模型榜与重置监控没有纳入菜单，也不保留占位页面。现有Node测试有模块类型提示，本轮没有因此修改项目依赖或模块模式。
