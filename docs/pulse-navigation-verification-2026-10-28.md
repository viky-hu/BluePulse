# Pulse 切页复用与顶部加载条核查

日期：2026-10-28。范围为当前已选菜单、共享 p0 导航及关于页统计。直接在 main 适配 Next.js 16.3.5，不修改 Python 后端；AIHOT 证据仍是 D:/AIHOT 静态下载快照，不是其线上运行验收。

## 原始源码 → 复用内容 → Pulse 适配

| 原始实现 | 复用与适配 |
| --- | --- |
| `apps/web/app/components/shell/Chrome.tsx: NavigationProgress` | 窗口顶部2px强调色细线，150ms延迟、85%等待位置、2.4秒展开和完成淡出；Pulse 使用 #176b75，减少动效为静态细线，定时器在状态变更/卸载时清理 |
| `components/shell/Sidebar.tsx: prefetch="intent"` | 菜单悬停/键盘聚焦并行预取 Next 路由及客户端数据；预取本身不显示加载条 |
| `lib/page-reuse.ts`、`api.server.ts: cachedPage` | 保留当前 document 的有界缓存、请求合并与强制刷新；客户端数据本地上限60秒，并受响应的绝对截止及禁止缓存策略约束，读取不续期 |
| `routes/about.tsx` 的页面复用 | 关于统计共享请求由缓存持有8秒超时；页面离开仅取消本组件订阅，不取消其他消费者仍需的请求；成功结果参与复用，错误/404/非法统计不缓存 |
| `lib/restore.ts`、`session-cache.ts` | 30分钟位置/锚点恢复独立保留，feed快照同时检查其数据截止；刷新、重试和不可复用的新响应清除旧feed快照，不删除位置或损坏的可恢复存储 |

Pulse 的保留项：p0/绿色底板和菜单、0.22秒退出及0.4秒进入动画、已有字体与Logo几何。可见的路由/资讯/统计加载文字已改由共享细线反馈；辅助技术使用隐藏状态提示及 `aria-busy`。真实错误、空态、未接入状态仍保留。

## 核查发现与修正

- 旧状态机在数据完成后才处理排队导航。补充实测3秒HTTP等待使改跳延迟约3.67秒；现对尚未开始淡入的隐藏目标直接提交最新导航，保留已开始动画的既有节奏。
- 就绪报告同时校验当前URL和导航目标。页面访问使用activation身份，避免后退/前进先显示过时客户端state，以及URL提交前的旧页面触发多余数据请求。
- 同URL服务端刷新使用React Transition跟踪，避免清空ready却因RouteReady未卸载而永远等待。首次封面结束后的revealing等待也显示加载反馈。
- API代理透传 `Cache-Control`、`X-Accel-Expires`、`Age`、`Date`。组合列表/精选/最近收录请求取最早截止；`no-store/no-cache` 的结果可供当前请求展示，但不进入页面或会话数据复用。

## 接口与验证边界

不新增业务接口。关于统计仍依赖 `GET /api/v1/site/stats`，真实聚合后端尚待实现；404/故障显示原有说明，不回退成演示数字。统一发布层的服务端绝对截止仍需后端提供，详见 dock.md；无缓存策略时的60秒只是本地复用上限，不代表后端已提供撤回传播保证。

页面复用仅覆盖精选、全部动态、搜索及关于统计；静态栏目没有独立数据请求，旧文章/实体服务端页面沿用Next路由读取，统一接入导航与加载反馈。没有宣称移植AIHOT的完整事件、报告、机器出口或生产缓存链。

本轮同时检测到另一个聊天正在同main制作更新日志和反馈页，已获用户授权协调构建与统一提交，保留其源码与文档。

## 验证结果

- `pnpm lint`、TypeScript、生产构建通过；当前全仓逻辑检查44项通过（包括另一个聊天新增的日志/反馈检查）。Node 的既有模块类型提示仍存在，未因此改变项目模块模式。
- 导航专项13项通过：首访减少动效的慢首页、三个视口/动效模式的窗口顶部细线、改跳与晚到响应隔离、同URL静态刷新、关于预取/复用/刷新/离开中的共享请求、no-store策略变更、过期历史重新请求并恢复位置、错误重试、挂起服务端刷新时2秒内到达其他页面。
- 原有主导航42项浏览器回归在最终构建上全部通过，包含首次/回访、菜单/深链接、连续导航、刷新/重试、查询/游标、收藏/撤回、前进后退与滚动恢复；加载结束检查已改为统一aria-busy，适配可见加载文案移除。
- 关于页专项20项通过；菜单响应式专项5项通过。查看了1360×760桌面、390×844移动及减少动效的加载/就绪截图。浏览器异常记录为空。
- 独立代码复核提出的旧会话快照和首次revealing反馈问题均已修正；最终只读复核未发现确定阻断问题。

复现命令：

```powershell
pnpm lint
pnpm build
node --experimental-strip-types --test (Get-ChildItem scripts -Filter '*.test.mjs').FullName
$env:PULSE_PLAYWRIGHT_MODULE='C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs'
node --experimental-strip-types scripts/navigation-loading-browser-test.mjs
node --experimental-strip-types scripts/home-transition-browser-test.mjs
node --experimental-strip-types scripts/about-browser-test.mjs
node --experimental-strip-types scripts/sidebar-responsive-browser-test.mjs
```

产物均位于忽略的 `test-results/`：`navigation-loading/verification.json`、`pulse-sidebar/verification.json`、`pulse-about/verification.json` 及截图。测试仅启动隔离Next生产服务和确定性HTTP测试服务，没有触发采集、模型、推送或真实反馈投递。缓存时间测试使用浏览器受控系统时钟，保持动画时钟继续前进。
