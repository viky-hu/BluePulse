# AIHOT 研究与 Pulse 基础改造验收记录

验收日期：2026-10-25。范围为已批准计划中的研究沉淀、匿名浏览器状态、共享 p0、真实路由和收藏可访问性接口，止于 README“本系统新增新功能新模块”之前。

## 结果

本轮基础改造的限定范围验收通过。生产构建、lint、14 项前端逻辑检查、10 项相关 Python 后端测试、28 项 Chromium 浏览器场景均通过。浏览器记录的未捕获异常为 0。

这不是 AIHOT 整套系统或生产部署的验收：AIHOT 仍仅做本地下载快照的静态研究；没有启动其服务、数据库、采集、模型或通知。完整管理员后台、事件/热点/日报、付费任务恢复和新菜单模块仍按后端阶段交接推进。

## 本次修复及回归

原接口模式下，搜索页可以一直停留在“正在载入资讯”。复现时浏览器没有未捕获异常，接口已被请求；同一条检查在修复前因 20 秒未结束加载而失败。

原因是 HomeDashboard 将可变草稿 `next` 提前作为 loading 状态提交；异步请求完成后直接修改并再次提交同一个对象，React 可能因为对象身份未变而跳过渲染。模拟数据同步返回曾掩盖这一问题。

修复将 loading 快照与结果草稿分离，并在同一个微任务中先发布 loading、再启动读取，兼容立即返回的 mock 和异步 HTTP。清理时仍中止请求、忽略过期结果。重新构建后，相同延迟接口检查通过；空结果、503、重试及在请求中继续导航也通过。

## 检查结果

| 检查 | 结果与边界 |
| --- | --- |
| `pnpm lint` | 通过，无 lint 错误或警告 |
| `pnpm build` | 通过，TypeScript 通过；首页、搜索、分类、历史、收藏、文章库、详情、实体及代理路由构建成功 |
| 前端逻辑 | 14 项通过：入场几何、白纸布局、分类树、导航状态机、URL/入口判断、浏览器状态和会话恢复 |
| Python 后端 | 10 项通过：availability 5、recently-collected 1、entities 2、article-search-status 2；使用临时 SQLite/TestClient，不修改现有业务数据库 |
| 浏览器 | 28 项通过；桌面 1360×760、移动 390×844、桌面 reduced-motion；使用隔离的生产 Next 服务与确定性 HTTP 测试服务 |
| 视觉 | 已查看桌面、移动分类及 reduced-motion 截图；p0 与动画终点几何一致，内部容器无横向溢出，菜单可操作 |

前端逻辑检查命令：

```powershell
node --experimental-strip-types --test scripts/intro-config.test.mjs scripts/white-paper-config.test.mjs scripts/topic-menu-config.test.mjs scripts/home-view-transition.test.mjs scripts/home-routes.test.mjs scripts/browser-state.test.mjs
```

浏览器检查命令：

```powershell
# 若项目未安装 Playwright，指向本机已有的 Playwright 模块；本次使用 Codex 随附模块。
$env:PULSE_PLAYWRIGHT_MODULE='C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright\index.mjs'
Remove-Item Env:PULSE_TEST_MODES -ErrorAction SilentlyContinue
node --experimental-strip-types scripts/home-transition-browser-test.mjs
```

后端分别执行 `python -m unittest discover -s tests -p <测试文件>`，测试文件为 `test_article_availability.py`、`test_recently_collected.py`、`test_entities.py`、`test_article_search_status.py`。本机运行时通过 PYTHONPATH 复用 `backend/.venv/Lib/site-packages` 及 backend 包路径。

## 浏览器覆盖

- 首次完整入场仅在全部完成后写入标志；未完成便刷新不标完成。回访刷新没有短暂挂载初始封面。首次直达搜索后返回首页仍为稳定态。
- 三种视口/动态模式的终点几何、菜单、搜索和分类 URL；桌面快速连续导航只到最后目的地，共享底板不重建。
- 收藏持久化、同页按钮更新、跨标签页移除同步、详情收藏/取消、阅读历史、返回 p0 原位置及前进后退。
- 真实文章链接按 Ctrl 点击可在新标签页打开稳定态详情。
- HTTP 延迟响应后加载结束；主动刷新重新请求；分页游标进入 URL；修改筛选清除旧游标；已提交筛选刷新后保留。
- 空结果、503 错误均能成为终态；文章同 URL 重试重新读取服务端详情。
- 请求中可继续通过菜单排队导航，有加载反馈；旧响应不会将最终收藏页覆盖为旧搜索页。
- 原文章库及实体筛选 URL 进入共享 p0。
- 已撤回文章保留收藏快照并禁用详情链接；availability 接口失败保留“未知”及链接，不误判撤回。
- 损坏存储保留原始数据并使用内存收藏；localStorage/sessionStorage 被拒绝时仍可导航、收藏及回首页。

30 分钟过期、不因读取续期、命名空间隔离、500 条收藏上限、去重、损坏会话保护及写入失败还通过独立逻辑测试覆盖。availability 的 100 个 UUID 上限、格式错误、顺序/去重、单次 ID 查询、公开可见性和 no-store 通过真实 Python 路由测试覆盖。

## 产物与保留项

浏览器脚本生成 `test-results/aihot-foundations/verification.json`（28 条记录，`browserErrors: []`）及 desktop/mobile/reduced 和分类截图；该目录按仓库规则忽略。最终浏览器运行记录时间为 `2026-10-25T13:48:11.537Z`。

本次业务代码仅修改 HomeDashboard 的加载状态提交，补充浏览器检查与研究进度文档；没有修改 Logo、字体、双 SVG 几何或动画时间线。README 后续新增模块草稿按原字节保留。

测试服务使用 3100/3101 端口，脚本退出后关闭。没有调用真实信源、付费模型或推送服务。浏览器的 HTTP 服务是可控制的契约测试服务，Python 公开条件另由 TestClient 验证；未进行生产反向代理、真实数据全链路、跨浏览器矩阵或 AIHOT 本地交互验收。

运行环境有 Node 的 TS 模块类型提示，以及 Starlette/httpx、Alembic 和 Python datetime 兼容性提示；检查无失败。本次没有为消除提示而升级依赖。

研究依据见 [AIHOT 源码研究](aihot-understanding.md)，后续工作见 [后端阶段交接](aihot-backend-stage-map.md)。
