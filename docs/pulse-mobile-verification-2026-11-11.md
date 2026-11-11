# Pulse 移动端验收

日期为 2026-11-11。AIHOT 依据是 `D:/AIHOT` 静态源码快照。Pulse 适配采用现有 Next.js、GSAP、p0 滚动和浏览器阅读状态。

| AIHOT 源码 | 复用行为 | Pulse 适配 |
| --- | --- | --- |
| `components/shell/TabBar.tsx`、`nav.ts`、`screens.ts` | 等宽底栏、安全区、选中态、重复点击、每个历史条目的栏目归属 | 五入口为精选／全部／热点／日报／更多。根页回到白纸顶部，再点刷新当前筛选。搜索记住所属栏目，日报归档和详情归日报，事件归热点。文章正文和原文用已有阅读工具栏。 |
| `components/shell/PhoneBar.tsx` | 左中右槽位、48px 工具栏、44px 操作区 | 左侧使用 Pulse 标志，≤360px 显示图形标志。栏目将标题或操作放到共享栏。页面切换期间锁定离场栏的操作，底栏继续接受下一次导航。 |
| `features/feed/Filters.tsx`、`components/ui/Sheet.tsx` | 右上触发、单列 48px 选项、选中勾号、可清除标签、焦点恢复 | 精选和全部动态复用 Pulse 的 Sheet、分类数据、查询参数和现有搜索页。保持 p0 滚动锁定和筛选等待反馈。 |
| `routes/more.tsx` | 按用途分组、收藏数量和更新标记 | `/more` 提供收藏、历史、搜索、Agent、关于、更新日志和反馈。阅读状态沿用本机存储。 |
| `features/report/ReportLayout.tsx`、`ReportNav.tsx` | 顶部刊种切换、近期刊期条、目录抽屉 | 日报胶囊视觉高 32px、触控区 44px。周报和月报继续显示为禁用。目录和正文定位以 p0 为准。 |

移动端绿底铺满视口。白纸横向留 6px 加左右安全区，底边距导航 8px。普通手机首页从首帧进入稳定态。关于页以 `intro=1` 主动重播原场景，完成后替换当前地址并移除参数。手机上的桌面侧栏由 CSS 从布局中移除。桌面侧栏与首次访问动效沿用原实现。

## 实测

- `pnpm lint` 与 `pnpm build` 通过。入口、页面归属、导航意图、浏览器状态、全部动态、日报和文章路由的相关脚本通过。
- 移动端专项 20 组通过，覆盖 390×844 的普通与减少动效状态、320px 极窄屏、768／769px 断点、1440px 桌面、浏览器存储拒绝和短屏安全区。检查了首帧和重播交接、筛选抽屉、焦点恢复、滚动、历史回退、日报锚点和阅读工具栏。加入了连续快速操作的回归用例，修复前能够点开离场页面的筛选抽屉，修复后用例通过。
- 桌面侧栏与响应式专项 5 组、日报 35 组、文章阅读 37 组通过。已查看手机首页、日报和新闻阅读截图。截图和逐项结果位于 `test-results/mobile-shell/`、`test-results/pulse-sidebar/responsive/`、`test-results/daily-report/` 和 `test-results/article-reader/`。
- 浏览器使用显式演示数据和本地 HTTP 测试服务。业务接口、采集、模型和部署状态沿用本轮开始前的版本。浏览器安全区及键盘占用空间通过视口模拟检查，尚无实体设备的软键盘和系统手势区验收。

复现命令

```powershell
pnpm lint
pnpm build
node --experimental-strip-types scripts/mobile-entry.test.mjs
node --experimental-strip-types scripts/mobile-screen.test.mjs
node --experimental-strip-types scripts/mobile-shell-browser-test.mjs
$env:PULSE_PLAYWRIGHT_MODULE = 'C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs'
node scripts/sidebar-responsive-browser-test.mjs
node --experimental-strip-types scripts/daily-report-browser-test.mjs
node --experimental-strip-types scripts/article-reader-browser-test.mjs
```
