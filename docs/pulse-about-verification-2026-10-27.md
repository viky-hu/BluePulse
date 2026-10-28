# Pulse 关于页复用与验收

日期：2026-10-27。工作分支 `main`；范围为关于页、必要的同源统计代理预留、Mock、二维码与接口交接文档。已有菜单字标及品牌文件的未提交改动保留。没有修改 Python 后端、队友分支、共享 p0 几何或菜单动画。

## 原始源码 → 复用内容 → Pulse 适配

| AIHOT 源码 | 复用内容 | Pulse 适配 |
| --- | --- | --- |
| `apps/web/app/routes/about.tsx` | 两段大标题、精选/日报入口、图下四阶段、数字格式、最近精选、制作人及二维码布局 | 警务科技文案、Pulse 本地字体与品牌、以白纸内容宽度而非屏幕宽度切换列数；路由使用 Next Link 和共享导航 |
| `apps/web/app/features/about/SignalRiver.tsx` | 原版种子几何、40–160 条信源线、束线、闸门、淘汰淡出、通过换色、报纸、流光、命中判断、阶段高亮 | 拆分绘制与 React 生命周期，useGSAP scope，p0 内滚动暂停、隐藏暂停、resize 归一化位置、减少动效静态状态及提示框边界 |
| `packages/contracts/src/site.ts` 和 `packages/backend/src/site/stats.ts` | SiteStats 字段、信源样本及最新 8 条精选组成 | 预留 Pulse UUID 接口，不复制 SQL；未知统计允许 null。真实数字、稳定抽样、刊期和公开过滤由后端后续实施 |

源码依据为 `D:/AIHOT` 的无 Git 下载快照，本轮重新核对相关实现，没有运行 AIHOT 自身数据库/worker 或核验线上站点。MIT 全文及 Copyright (c) 2026 数字生命卡兹克保留在 `THIRD_PARTY_NOTICES.md`。

## 最终行为

- `/about` 保留完整介绍、示意图和联系方式，读取 `/api/bluepulse/site/stats`；404 显示尚未接入，其余网络/格式故障显示暂时不可用，可重试。
- `/about?mock=1` 显式演示 100 条信源样本和现有 8 条可打开的 Mock 新闻，统计区标记演示数据；真实请求失败不启用 Mock。
- 信源悬停显示信源，而非逐线新闻摘要；束线、闸门与报纸保留原版说明。最近精选由通过的流光抵达驱动轮换，最短间隔 2.8 秒。
- 四阶段说明按内容宽度 800px 四列、520px 两列、更窄单列；团队区 820px 起左右排列。原 p0 容器及内滚动保持不变。
- 按用户追加要求，主标题缩小并使用 700 粗体，团队问候语同样为 700；不影响其他页面的展示字重约定。
- QQ 和微信使用用户重新提供的透明 PNG 原文件。可见码区分别约为画布宽度的 878/1046、633/804，因此微信显示宽度为 QQ 的 106.62%，使可见码区近似等大；不裁切、不修改原图，可点击完整查看。
- 两张已纳入项目的 PNG 与用户 Downloads 原文件 SHA256 相同。头像的三条路径、viewBox 和 vector-effect 已与 qlxf 几何核对。
- 统计请求初次结束后再报告 RouteReady，防止历史返回时按较短的加载中页面恢复滚动而被截断。

## 验证结果

| 检查 | 结果 |
| --- | --- |
| `pnpm lint` | 通过，无错误或警告 |
| `pnpm build` | 通过，TypeScript 与生产路由构建成功 |
| 关于页逻辑检查 | 2 项通过：统计格式/空值/无效 ID；窄白纸有限几何与 heat-only 不通过 |
| 既有路由及导航状态检查 | 2 个脚本通过；连同上项，Node test runner 共 4 项通过 |
| 关于页生产浏览器检查 | 20 项通过，未捕获浏览器异常 0 |
| 视觉复核 | 已查看 1360×760 桌面、390×844 移动端、团队二维码及 reduced-motion 截图 |

浏览器检查使用隔离的生产 Next 服务和受控 HTTP 测试服务，覆盖：延迟统计后的历史滚动恢复；显式 Mock 隔离；标题字重/尺寸；来源、束线、报纸提示及边界；四阶段键盘高亮；抵达轮换；缩放不重播；document hidden 暂停；组件离开停止绘制；精选/日报/新闻跳转与查询参数、刷新和前进后退；透明二维码大小；p0 外不可见暂停；移动端布局；减少动效；真实正常、部分空值、空数组、404、503、格式错误与重试；精确代理白名单。

共享导航浏览器脚本中旧关于页的标题与正文断言已随新结构更新；本轮没有重跑整套无关浏览器回归矩阵。Node 的 `MODULE_TYPELESS_PACKAGE_JSON` 提示是仓库现有模块模式提示，不影响通过结果，本轮未为消除它修改依赖或 package 模式。

### 复现

```powershell
pnpm lint
pnpm build
node --experimental-strip-types --test scripts/about.test.mjs scripts/home-routes.test.mjs scripts/home-view-transition.test.mjs
$env:PULSE_PLAYWRIGHT_MODULE='C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright\index.mjs'
node --experimental-strip-types scripts/about-browser-test.mjs
```

专项脚本使用 3120/3121 端口，结束后关闭自身的浏览器和服务。产物为仓库忽略的 `test-results/pulse-about/verification.json` 及对应 PNG。

## 后端状态与交接

根目录 `dock.md` 建立了可持续追加的固定格式，首项 `DOCK-001` 记录 AIHOT 原实现、Pulse 契约建议、统计口径差异、缓存、错误、示例与后续验收条件。

**当前状态：前端已预留，FastAPI 后端待实现；未完成真实业务联调。** 本轮的受控 HTTP 验证不代表统计接口已上线。日报期数、精选确认时间、来源热度参与模式、事件归组和机器订阅仍需后端支持；现有六席首页不等于日报。二维码为静态配置，不代表管理员上传或管理后台已实现。
