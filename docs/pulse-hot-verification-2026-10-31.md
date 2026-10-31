# 热点榜源码复用与前端验收

验收日期：2026-10-31（Asia/Shanghai）。在 `main` 的精选页基线 `b99a0c2` 上实施，仅修改热点前端、必要的读取／导航集成、验证脚本和交接文档；没有修改 FastAPI、队友分支、p0几何、封面六槽或Logo。

## 原始源码 → 复用内容 → Pulse适配

直接阅读 `D:/AIHOT` 非Git下载快照，以下证据是静态来源核对，不是源站运行或生产验证。

| AIHOT原始实现 | 复用及适配 |
| --- | --- |
| `routes/hot.tsx` 的 Lead／Runner／Row／HeatPanel／Voices／Badges／StoryLink | 首条主卡、随后两张副卡和其余列表；原排名／徽标／趋势、标题摘要、最新进展、来源与参与者、封面／热度面板／紧凑曲线、整卡链接和全部条件分支。保留服务端排名缺口，不补齐条目。 |
| `features/hot/{Sparkline,Delta}.tsx`、`curve.ts` | 原25小时边界槽、null分段、少于三点不画、零基线、单调曲线／渐变面积／端点；未知趋势“暂不比较”和原变化百分比呈现，不套用内嵌条另一种箭头组件。 |
| `Faces.tsx`、`SourceAvatar.tsx`、`Badge.tsx` | 复用已移植共享实现，保留六个editorial头像、余量、失败首字、分组名单、未列出计数、独立操作及body portal；p0内部滚动、Escape、外点和resize关闭。 |
| `PhoneBar.tsx`、原页标题与说明、`app.css` | 原窄屏操作／大标题／副文案／吸顶标题、桌面实时圆点／更新时间和说明折叠。标题出现以h1移出为依据；原披露展开动画本地化，reduced-motion保留静态圆点与所有操作。 |
| 契约、site API、`publication/{hot,stories,scope,representative}.ts`、`events/{hot,group}.ts` | 原字段与公开读取语义，精确同源 `site/hot` 代理；不移植React Router、Fastify、SQL或worker。后端任务见DOCK-007。 |

热点实现共置于 `src/app/hot/`，薄路由挂接现有MainShell；仅以600／760／1040px内容断点、窄纸换行及尺寸约束适配原布局。保留原组件配色、圆角、字号及头像大小，沿用Pulse字体和品牌。没有新增成功态说明行、统计、筛选或骨架。

## 实际检查结果

| 检查 | 结果 |
| --- | --- |
| `pnpm lint` | 通过，0 error／warning |
| `pnpm build` | 生产构建、TypeScript与路由生成通过 |
| 全部现有前端逻辑脚本及阅读组边界 | 72项通过，含7项热点契约／曲线／缓存检查 |
| `scripts/hot-ranking-browser-test.mjs` | 24组通过；1360×760桌面、390×844移动、桌面reduced-motion；浏览器异常0 |
| `scripts/featured-feed-browser-test.mjs` | 28组通过，含延迟阅读组核验、深锚点返回及过期列表重建 |
| `scripts/all-feed-browser-test.mjs` | 18组通过 |
| `scripts/navigation-loading-browser-test.mjs` | 13组通过 |
| 独立只读源码审查 | 原组件分支／曲线／样式、数据边界、缓存、p0集成及交接复核通过 |

热点受控检查涵盖：0／1／2／3／10条、原排名缺口、主卡封面／大曲线／不足三点、各徽标／趋势、null断线／唯一SVG渐变、真实图标与失败降级、六头像／余量／分组名单、原说明折叠／窄屏定位、事件目标／返回锚点、刷新、404／503／代理超时、畸形字段／非法JSON、重试、精确白名单、预取合并、当前菜单刷新、no-store／Age耗尽及晚到结果隔离。演示只在原h1标识，普通入口从不自动回退。

复现命令：

```powershell
$tests = @(rg --files scripts -g '*.test.mjs')
node --test @tests src/app/_components/feed/group-request.test.mjs
pnpm lint
pnpm build
node scripts/hot-ranking-browser-test.mjs
node scripts/featured-feed-browser-test.mjs
node scripts/all-feed-browser-test.mjs
$env:PULSE_PLAYWRIGHT_MODULE = 'C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs'
node scripts/navigation-loading-browser-test.mjs
```

浏览器脚本启动独立Next生产服务和本地确定性HTTP服务，未启动采集、模型或通知。Playwright复用现有运行时，可用 `PULSE_PLAYWRIGHT_MODULE` 指定路径。Node已有 `MODULE_TYPELESS_PACKAGE_JSON` 提示保留，没有为消除此提示改动包配置。

截图和检查／请求回执在忽略目录 `test-results/hot-ranking/`，桌面、移动和reduced-motion截图已查看；卡片内部及p0均无横向溢出。其他三套回执分别在已有 `featured-feed/`、`all-feed/`、`navigation-loading/` 目录。测试截图中的封面和图标是受控图形，不代表真实警务新闻素材。

## 检查中修正的问题

- 枚举必须是实际字符串；拒绝可被String转换伪装成up／new／editorial的JSON数组，避免错误趋势或遗漏头像。
- 预取索引与返回数据都规范化查询参数顺序，避免相同地址的缓存命中后一直显示加载状态。
- 窄屏吸顶标题对齐原h1触发点，保留原说明展开动画；白纸窄列明确约束热度面板宽度和网格，避免宽高比与最小高度将内容撑出卡片。
- 精选回归原先在Playwright再次自动滚动前采集期望位置，误报329px偏移。诊断实际点击／保存／返回均为9830，而更早采样为10159，前后卡片几何一致；现在按目标文章点击捕获阶段的实际离开位置校验，保留原40px误差断言。没有修改产品MainShell、阅读组或滚动恢复实现，也没有放宽断言。

## 真实状态与后端依赖

本轮证明前端完整消费、精确代理和受控状态行为。正式 `GET /api/v1/site/hot`、独立参与方热度、source clock／覆盖、排名及小时complete快照、公开证据／文本／头像／封面读取仍待FastAPI实现和真实联调。页面存在不代表后台、归组或排名任务已完成。

`/hot?mock=1` 为显式隔离演示。正式 `/hot` 在接口缺失时显示待接入，合法空榜与故障分开；不以文章重要性、点击数或静态演示新闻生成正式排名。`/story/:publicId` 仍为诚实待接入目标，完整事件详情及合并308另行交付。

完整字段、计算口径、计数／名单差异、25点曲线、媒体许可与撤回、30秒／上游截止及后端签收条件见根目录 [DOCK-007](../dock.md#dock-007热点榜参与者与24小时曲线)。MIT完整许可及版权保留在 `THIRD_PARTY_NOTICES.md`。
