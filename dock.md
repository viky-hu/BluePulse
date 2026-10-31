# Pulse 前后端接口对接总册

更新日期：2026-10-31。本文是可持续追加的模块对接报告。**建议契约不等于后端已实现；Mock 验收不等于真实业务联调。**

技术边界：Pulse 保留 Next.js 16 / React 19 / TypeScript / Tailwind 4 / GSAP，以及 Python / FastAPI 后端。复用 AIHOT 的组件、业务机制和契约思路，不移植 React Router loader、Fastify、PostgreSQL SQL 或 pg-boss。

## 维护方式与固定格式

每个新增模块使用稳定编号（`DOCK-001` 起），在下表登记；按以下七节追加，不重写其他模块的历史结论：

1. **功能与状态**：页面、使用者、本轮交付、前后端各自状态及未完成依赖。
2. **AIHOT 源码证据**：前端入口、契约、API 路由、后端读取及相关配置，写出真实文件和符号。
3. **AIHOT 原始数据流与契约**：谁请求谁、字段语义、交互如何消费数据、缓存与权限实际行为。
4. **Pulse 建议及差异**：可直接复用的内容、框架适配、领域差异、现有代码依据、接口与统计口径。
5. **请求响应示例**：方法、路径、字段、空值、数量边界、可用的本地演示地址。
6. **缓存和异常**：未接入、真实空结果、暂时故障、超时、取消及公开可见性；Mock 单列。
7. **验收条件与变更记录**：区分静态核对、前端测试、契约测试和真实后端联调，记录日期及结果出处。

状态用“已实现 / 前端已预留，后端待实现 / 部分实现 / 待真实联调”；不把接口设计、静态资料或测试服务写成生产能力。

| 编号 | 模块 | 前端入口 | 接口 | 当前状态 |
| --- | --- | --- | --- | --- |
| DOCK-001 | 关于页统计、信源河与最近精选 | `/about` | 建议 `GET /api/v1/site/stats` | 前端已预留，后端待实现 |
| DOCK-001 附项 | 团队头像和联系方式 | `/about` | 本轮静态资源，无新增后台接口 | 已实现静态展示 |
| DOCK-002 | 更新日志与未读提示 | `/changelog` | Next.js `GET /api/bluepulse/site/{changelog,meta}` | 已实现真实文件数据并通过本轮前端验收；无 FastAPI 依赖 |
| DOCK-003 | 匿名反馈、草稿与截图 | `/feedback` | `POST /api/bluepulse/site/feedback` → 建议 FastAPI `/api/v1/site/feedback` | 前端及代理已预留，真实接收与查看待后端实施 |
| DOCK-004 | 全部动态、分类筛选与全文检索 | `/all` | `GET /api/bluepulse/{articles,taxonomy}` → FastAPI `/api/v1/{articles,taxonomy}` | 前端及受控接口验收通过；新分类数据、相关度、数字分页及统计待后端补齐，待真实联调 |
| DOCK-005 | 收藏可用性与本地阅读备份 | `/starred` | `GET /api/bluepulse/articles/availability` → FastAPI `/api/v1/articles/availability`；备份只读写浏览器 | 现有布尔接口可沿用；前端扩展适配已实现，明确权限状态／当前来源名待后端扩展和真实联调 |
| DOCK-006 | 精选时间线、同新闻阅读组与内嵌热点 | `/` | `GET /api/bluepulse/site/timeline`、`site/groups/:factId/reports` → FastAPI `/api/v1/site/…` | 前端和精确代理已实现；归组、发布读取、热点与真实联调待后端实施；本轮最终验收另记 |

## 共享前端：页面复用与缓存截止（2026-10-28）

此项不新增业务接口，也不改变 DOCK-001 的统计字段。Next 同源代理透传 `Cache-Control`、`X-Accel-Expires`、`Age`、`Date`。精选、全部动态、搜索与关于统计的页面缓存保留最多60秒，遇到服务端更早截止时提前失效；`no-store/no-cache` 不进入当前document复用或列表数据快照。多接口组合取最早截止，预取与实际进入合并相同URL的请求，刷新和重试强制取新。

后端建议为公开可复用响应提供与真实读取缓存一致的 `X-Accel-Expires: @<Unix秒>`，保留生成响应的Date及缓存消耗的Age；不得在代理/SSR再次把旧结果寿命从零开始。禁止复用时用 `Cache-Control: no-store` 或 `no-cache`，必要时同时给 `X-Accel-Expires: 0`。前端没有策略时的60秒仅为本地回退，不能视为统一发布、撤回或许可缓存链已完成。无需后端返回新的业务JSON字段。

位置/锚点仍可保存30分钟；数据超过自身期限后重新请求再恢复位置。主动刷新、重试或新的不可复用结果会移除旧feed快照，避免返回更早的可缓存结果。关于统计当前仍待 FastAPI 实现，404和故障不缓存，不以Mock冒充联调。源码和验证见 `docs/pulse-navigation-verification-2026-10-28.md`。

## DOCK-001：关于页统计、信源河与最近精选

### 1. 功能与状态

匿名读者了解 Pulse 的工作流程，从关于页进入精选、日报或文章详情。图表是流程示意，**不是逐条新闻的实时运行状态，也不证明事件归组和成刊能力已启用**。

- 前端已实现：页面组成、四阶段统计展示、Canvas 信源河、悬停提示、聚焦高亮、抵达事件驱动的精选标题轮换、显式 Mock 和故障状态。
- 预留：同源代理 `/api/bluepulse/site/stats` → FastAPI `/api/v1/site/stats`，只允许这一个精确新增路径。
- 后端待实现：统计聚合、真实信源样本、最近精选读取、可靠的精选确认时间统计及日报期数。
- 后端现状：`backend/bluepulse_backend/api.py` 已有 sources、articles、home/featured、recently-collected；`editorial.py` 已有 `public_article_conditions()` 和 `featured_article_condition()`。这些不能等同于新统计接口或完整 AIHOT 发布层。

### 2. AIHOT 源码证据

证据是 `D:/AIHOT` 的无 Git 本地下载快照。本轮于 2026-10-27 重新核对相关源码；未启动 AIHOT 数据库、worker 或外部服务，不代表线上运行验收。

| 环节 | 文件与符号 |
| --- | --- |
| 前端页面、数字、最新标题、联系方式 | `D:/AIHOT/apps/web/app/routes/about.tsx`：`loader`、`stagesOf`、`Latest`、`Maker`、`onArrive` |
| 画布与悬停 | `D:/AIHOT/apps/web/app/features/about/SignalRiver.tsx`：`layout`、`paintStatic`、`paintPaper`、`onMove`、`tick` |
| 共享契约 | `D:/AIHOT/packages/contracts/src/site.ts`：`SiteStats`、`SiteContact` |
| 站内读取 API | `D:/AIHOT/apps/api/src/routes/site.ts`：`/api/site/stats`、`/api/site/contact` |
| 数字与样本 SQL | `D:/AIHOT/packages/backend/src/site/stats.ts`：`loadSiteStats`、`querySiteStats` |
| 发布过滤 | `D:/AIHOT/packages/backend/src/publication/scope.ts`：`selectedCondition` |
| 联系方式及头像 | `D:/AIHOT/packages/backend/src/site/contact.ts`：`loadContact`、`loadMakerAvatar`、`packCode` |
| 文案配置 | `D:/AIHOT/site/site.ts`：`ABOUT`、`REPORTS` |
| 页面缓存 | `D:/AIHOT/apps/web/app/lib/api.server.ts`：`cachedPage`；`page-reuse.ts`：页面内存复用 |

Pulse 对应实现位于 `src/app/about/`；页面、配置、数据、Mock、画布生命周期和几何绘制分别组织。完整 MIT 许可及 `Copyright (c) 2026 数字生命卡兹克` 见根目录 `THIRD_PARTY_NOTICES.md`。

### 3. AIHOT 原始数据流与契约

`about.loader` 并行请求 stats、contact；任一失败单独降为 `null`，静态介绍仍能显示。Web 经 HTTP 读 API，不直接连接数据库。API 端统计结果一次返回给页面，**移动指针和流光抵达都不会发新闻请求**。

| 原字段 | AIHOT 实际含义 |
| --- | --- |
| `sources`、`sourceKinds` | 启用来源总数，以及按采集 kind 的分布。kind 为 `x_search/rss/web_list/mp_account/json_list`，不是 government/media 等业务分类 |
| `items` | `publications` 中 visibility 不为 withdrawn 的数量，含热度专用材料；并不等于公开阅读列表数量 |
| `selected` | 满足 `selectedCondition(now)` 的数量；该条件包含 public、selected 和已到公开时间 |
| `dailies` | reports 表中 kind 为 daily 的记录数；不是首页精选席位数 |
| `day.collected` | 非撤回材料中 discovered_at 在过去 24 小时内的数量，含热度专用材料 |
| `day.selected` | 当前符合精选公开条件，且 timeline_at 在过去 24 小时内的数量 |
| `sampleSources` | 启用来源样本，最多 180 个；按 `md5(id + UTC 日期)` 再按 id 排序，每日稳定抽样；名称经过 `publicSourceName` |
| `latest` | 最新 8 条公开精选的 id、title、source；按 timeline_at、article_id 倒序 |

原信源样本字段为 `{ name, kind, heatOnly }`。Canvas 按宽度生成 40–160 条线，循环绑定样本，不保证每个来源独占一条且全部绘出。按预设种子生成束线、闸门和保留束，这是示意几何；`heatOnly` 会阻止对应流光产生抵达事件。

前半段悬停显示来源名称和类型；汇束处显示“同一件事”；闸门后显示入选或未入选说明；报纸显示日报说明。标题只在 `onArrive` 后轮换，最短间隔 2800ms；宽屏位于报纸下方，窄屏移到图下。用户已确认保留原版语义，**本轮不增加逐线新闻摘要接口**。

缓存有三层：统计进程缓存 fresh 10 分钟、最大 stale 1 小时；stats/contact API 带 ETag，HTTP 缓存 300 秒；关于页 `cachedPage(300)` 并参与页面复用。本文记录其原始行为，不声称这些 TTL 已在 Pulse 实现。

### 4. Pulse 建议及差异

建议匿名只读 `GET /api/v1/site/stats`，保留 AIHOT camelCase 字段以减少组件改写；它是 Pulse v1 下的站内展示扩展，不宣称兼容 AIHOT 公开 v1 API。前端代理沿用现有错误格式和 UUID 文章身份，不引入短 ID。

- `sources` 与样本只包含允许对公众展示的启用来源；最多返回 180 个样本，用固定站点日期的稳定抽样。本轮 Mock 返回 100 个样本，不能当作真实来源清单。
- **Pulse 的 `items`、`day.collected` 建议仅统计公开可读文章**：复用现有 `public_article_conditions()`，`day.collected` 使用 `first_seen_at`，不能用原始发布时间代替采集时间。这与 AIHOT 的“非撤回材料总量”不同，避免绕过当前公开读取边界。
- `selected` 与 `latest` 同时使用公开条件及 `featured_article_condition()`，保留人工覆盖优先。后续建设统一发布层时集中替换读取政策，覆盖撤回、延迟发布及来源权限，不各自维护一套过滤。
- `latest` 最多 8 条，使用 UUID；当前缺 AIHOT timeline_at，可先按可信 published_at、first_seen_at 回退和 UUID 组成稳定倒序，用“最近精选”标识，不能声称这是最新确认入选时间。未来确认时间字段上线时同步调整并记录。
- `day.selected` 需要“入选确认/公开”时间记录；现有模型候选或采集时间不能代替，暂返回 `null`。`dailies` 在真实刊期模型和出刊能力就绪前返回 `null`，不能用 `FeaturedEdition/FeaturedSlot` 计算。
- `sourceKinds` 与 sample.kind 来自采集适配器/入口配置，不来自 `Source.source_type`。RSS 映射 `rss`，HTML 列表映射 `web_list`，结构化 API 映射 `json_list`；无法确认的保留实际 kind，前端使用通用“信源”提示。
- `heatOnly` 需要明确的来源参与模式；Pulse 当前无该模式时对普通编辑来源返回 false，不根据媒体名称或相关性分数推断。Mock 的 true 只演示原版机制。
- 数字为可靠的非负整数或 `null`。`0` 表示确实为零，`null` 表示当前无法可靠统计；不能混用。前端在空值时省略对应数字，不写“0期日报”。
- 所有内容已经在 API 聚合，前端 hover/标题切换不请求全文、不触发采集或模型调用。

### 5. 请求响应示例

浏览器：`GET /api/bluepulse/site/stats`。服务端转发：`GET {BLUEPULSE_API_URL}/api/v1/site/stats`。无正文、无用户身份参数。

以下为**契约示例**，不是实际站点统计：

```json
{
  "sources": 2,
  "sourceKinds": { "rss": 1, "web_list": 1 },
  "items": 146,
  "selected": 12,
  "dailies": null,
  "day": { "collected": 7, "selected": null },
  "sampleSources": [
    { "name": "警务科技公开资讯示例源", "kind": "rss", "heatOnly": false }
  ],
  "latest": [
    {
      "id": "4ed2a8d4-efb7-4ce6-8a43-4ee36f27d001",
      "title": "警务科技研究成果示例标题",
      "source": "警务科技公开资讯示例源"
    }
  ]
}
```

全部字段必须存在；`sourceKinds` 可为 `{}`；数组可为空。尚不可统计的 sources/items/selected/dailies/day 数字返回 null。sourceKinds 中的数量必须为非负整数，样本包含非空名称、kind 和布尔 heatOnly；latest 为合法 UUID 和非空标题、来源。前端读取适配会拒绝错误包、负数、超限样本和无效文章 ID。

本地演示：`http://localhost:3000/about?mock=1`。使用确定性的 100 条信源样本及现有 8 条 Mock 新闻；最近精选进入 `/articles/{uuid}?mock=1`，不会产生悬空文章。统计区域标记“演示数据”。移除 mock 参数才访问真实接口，任何故障都不会自动回退到演示数据。

### 6. 缓存和异常

本轮浏览器和代理上游读取均 `cache: no-store`，不新增页面数据持久缓存或自动轮询。代理上游超时 6 秒，前端总等待上限 8 秒；离开页面取消前端请求。将来若引入 AIHOT 式 ETag/共享缓存，需明确撤回时效和绝对到期，不能叠加延长旧数据寿命。

| 情况 | 展示/行为 |
| --- | --- |
| 200、合法零值或空数组 | 真实显示 0；不显示无内容的最近精选块；保留流程示意 |
| 200、部分数字 null | 省略该数字，其余图文正常显示 |
| 404 | “站点统计尚未接入”，提供重新读取按钮 |
| 503/504、网络或格式错误 | “站点统计暂时不可用”，保留介绍、二维码和示意图，可手动重试 |
| 导航离开/旧请求取消 | 不更新已离开页面，不显示故障提示 |
| `mock=1` | 独立演示样本，不请求统计后端，不因真实服务故障启用 |

重新点击当前栏目或手动重试会重新取数；导航保留现有共享 p0、首次入口和浏览器历史机制。统计不写入收藏/历史存储。

### 7. 验收条件与变更记录

- 前端验收：lint、生产构建、窄白纸几何、数据格式、真实零值/空值/错误状态，以及桌面、移动端和 reduced-motion 交互。
- 契约测试：本地受控 HTTP 服务提供响应，核验代理路径、错误传递和前端展示；不启动真实采集、付费模型或推送。
- 后端交付验收：实际公开过滤、人工覆盖、撤回、延迟发布、稳定抽样、统计口径、24 小时边界和 UUID 详情可达。**本轮未完成真实 FastAPI 联调**。
- 2026-10-27：建立总册；DOCK-001 前端接口、原版动画及 Mock 实施。验证结果见 `docs/pulse-about-verification-2026-10-27.md`。

### 附项：团队头像与联系方式

AIHOT `SiteContact` 为 `{ wechatQr, feishuQr, makerAvatar }`。二维码默认扫描 `site/brand/contact/qr-{slot}.*` 并以 `/contact/` 提供；数据库 settings 的 `contact_qr` 覆盖包内配置。后台上传可更新带内容 hash 的文件名。头像来自 ABOUT.maker.avatarSourceId 对应信源的 icon_url，再经图片代理；失败时隐藏。

Pulse 本轮使用 `src/app/about/_config.ts` 的静态联系方式：`public/contact/qr-qq.png` 是用户更新提供的第一张 QQ 招新群透明图；`qr-wechat.png` 是第二张负责人微信透明图，原始字节保留、不裁切，点击可查看完整原图。按透明区域内的实际码区占比，微信图片显示宽度为 QQ 的 106.62%，使两枚码的视觉尺寸接近。头像复用 `public/logo.svg`，几何来自 qlxf.svg，未更改原始 viewBox 或路径。

当前无需新增联系信息 API、上传接口或管理员页。未来需要运营配置时，可移植原版“静态默认 + 受保护管理配置覆盖”的机制；使用 `qqQr` 和 `wechatQr` 等真实平台语义，不把 QQ 填进 feishu 字段。后台写入必须有服务端管理员 session、CSRF 和审计，静态二维码展示本身不证明这些能力已完成。

## DOCK-002：更新日志与未读提示

### 1. 功能与状态

匿名阅读 Pulse 开发更新，支持日期分组、四种类型及总数、随筛选变化的月份目录、月份锚点、正文段落／列表／粗体、重要公告和菜单未读红点。按白纸内容宽度 760px 切换左右栏，窄白纸保留可操作筛选。普通模式与显式 Mock 的已读标记隔离；无云同步。

本轮真实数据是仓库 `site/changelog.json`，SSR、菜单版本和 Next.js 只读 API 共用。**不需要组员再建设一套 FastAPI 日志服务或数据库表。** 这不是假接口或后端缺失时的演示回退。

### 2. AIHOT 源码证据

- `D:/AIHOT/apps/web/app/routes/changelog.tsx`：loader、ReleaseBody、Day、分组、类型及月份索引；`features/changelog/text.tsx`：Inline、dateHeading。
- `apps/web/app/components/ui/Page.tsx`：ReadingLayout、AsideCard；`components/shell/Sidebar.tsx`：useChangelogDot；`lib/local-state.ts`：setChangelogSeen、useChangelogSeen。
- `packages/backend/src/site/meta.ts`：loadChangelog、siteMeta；`apps/api/src/routes/site.ts`：changelog/meta 的 ETag 与缓存；`packages/contracts/src/site.ts`：ChangelogRelease、ChangelogResponse、SiteMeta。
- `site/changelog.json` 和 `docs/customize.md §7`：作者手工维护条目与 latestVersion。快照没有 push 自动生成摘要的实现。可选 FeatureRelease 绘图文件在本快照不存在。

### 3. AIHOT 原始数据流与契约

作者把新条目写到 JSON 最前，并修改 latestVersion；API 进程读取并缓存文件，页面 loader 经 HTTP 获取，页面复用期限 300 秒；根 loader 读取 meta，文档内不持续重新验证。进入日志页设置当前浏览器已读版本，版本变新时再出现红点。这些机制不等同于 GitHub webhook、实时 push 分析或自动发布。

### 4. Pulse 建议及差异

保留 `latestVersion: YYYY-MM-DDTHH:mm`、`releases[]`；条目为 `{date,time,kind,title,body,urgent?}`，kind 为更新／优化／公告／下线，body 为字符串数组，`- ` 开头合并列表、`**文字**` 加粗；urgent 为 true 时显示重要样式。数据在构建／读取时校验日期、排序及最新版本一致性。

已回看 main 的全部本地提交历史，合并为读者可感知变化。日期依据北京时间提交记录，不是可证明的 push 或上线时间；未提交的已验收工作归本次开发批次。没有读者变化的研究、临时提交、协作约定不单列。初始化工程与 Logo 导入汇入后续首屏条目。

Next.js 的精确静态路由优先于既有 catch-all 代理；不要把这两个路径加入 FastAPI 代理白名单，也不要维护第二份数据。后续维护者修改 JSON、校验并部署即可；仅 git push 并不会令未部署的服务器更新。版本在文档加载时进入共享菜单，不轮询服务器。

### 5. 请求响应示例

```http
GET /api/bluepulse/site/meta
200 OK
Cache-Control: public, max-age=60, s-maxage=60
ETag: "内容哈希"

{"changelogVersion":"2026-10-28T17:52"}
```

`GET /api/bluepulse/site/changelog` 返回同文件完整 `{latestVersion,releases}`，缓存 300 秒。两者支持 If-None-Match／304 空响应，无需账户、cookie 或模型调用。文章的权限策略不适用于这些开发说明；日志不得包含密钥或未公开材料。

### 6. 缓存和异常

HTTP TTL 分别 300／60 秒；本地已读标记长期保留，筛选与阅读位置仅使用既有 30 分钟会话恢复。这是三个不同生命周期。存储拒绝时已读标记仅内存有效，损坏数据保留，跨标签通过 storage 同步。刷新读取当前部署的数据；历史返回恢复筛选和有效滚动位置。无匹配类型显示真实空态。

### 7. 验收条件与变更记录

本轮检查数据有效性、筛选数量／月份目标、ETag、预取不标已读、跨标签消点、月锚点及内部滚动、刷新／前进后退、窄白纸与减少动效。实际结果记录在 `docs/pulse-changelog-feedback-verification-2026-10-28.md`。AIHOT 证据仅静态源码，不代表运行过其服务器。

## DOCK-003：匿名反馈、草稿与截图

### 1. 功能与状态

本轮前端实现完整表单、来源页、选填邮箱、单图选择／拖拽／粘贴／移除、本地草稿、发送防重、回执、错误与限流等待。**FastAPI 接收、数据库、私有截图及反馈查看命令均未实现**；普通模式默认关闭发送，不会真实入库。演示模式只在本机生成明确标注的 #10001，不联网、不冒充服务端回执。

用户明确排除飞书：不安排飞书凭据、内部群、转发任务、上传后删除或转发失败重试。其他原版逻辑按现有 Python 栈适配。

### 2. AIHOT 源码证据

- `D:/AIHOT/apps/web/app/routes/feedback.tsx`：表单、Draft、readDraft/writeDraft、screenshotType、pick/submit、附件预览与成功页。
- `apps/api/src/routes/feedback.ts`：readForm、multipart 解析、12MiB bodyLimit、POST 201；`packages/backend/src/operations/feedback.ts`：submitFeedback、sniffImageType、feedbackSourceHash、rateLimit。
- `packages/backend/src/admin/feedback.ts`：listFeedback、updateFeedback、banSource/unbanSource、feedbackScreenshot、eraseFeedback；`packages/contracts/src/admin.ts`：AdminFeedback。
- 原版 `notify/feishu.ts`、forwardPendingFeedback 仅作为差异证据，Pulse **不移植**。

### 3. AIHOT 原始数据流与契约

浏览器文字草稿保存在 localStorage，截图只在内存中；提交 multipart，API 校验来源、邮箱及图像，私有目录保存图片，再插入数据库，成功返回编号。原版可选后续飞书转发；持久入库是回执前提，不依赖转发是否成功。原版前端 2000 字／5MiB，服务端容错为 5000 字／8MiB，不能写成双方限制完全相同。

### 4. Pulse 建议及组员实施清单

按以下顺序交付，保留 UUID 文章身份和既有 FastAPI／SQLAlchemy／Alembic，不移植 Fastify、SQL 模板或 pg-boss。

1. **数据迁移和匿名接收**：Feedback 保存自增编号、content、email、page_url、私有 screenshot_key、source_hash、status（默认 new）、note、created_at、updated_at；FeedbackBan 保存 source_hash、reason、操作者和时间。以真实事务提交后返回编号；数据库失败删除本次孤立附件，避免文件已写而记录丢失。
2. **校验**：content trim 后 2–5000 字；email 选填、最长 200 字且格式有效；pageUrl 选填、最多 500 字，接受 http(s) 或站内相对路径，不允许凭据／可执行协议；超过边界返回明确校验错误，不静默截断关联地址。原版会截断地址，Pulse 改为拒绝以保留证据准确性。浏览器输入同步采用 200 字邮箱／500 字关联页面。
3. **截图**：最多一张，原始字节最多 8MiB；请求总计 12MiB。按真实字节检查 PNG/JPEG/WebP/GIF 并完整解码，像素上限 60,000,000；前端仍只提供 PNG/JPEG/WebP、5MiB。为每条反馈生成独立随机文件名，拒绝路径穿越；私有目录建议 `backend/data/feedback-screenshots/`，不经 public／任意下载接口暴露。相同图片的两份反馈不得共用会相互删除的文件。
4. **来源与反滥用**：使用稳定服务端 secret 对“可信客户端 IP + UA 类别”做 HMAC，保存来源标识而非原始 IP；生产禁止开发 secret。每来源每分钟最多 5 次，封禁返回 403，超频返回 429 与 Retry-After=60。多进程限流必须共用持久存储，不能仅依赖各进程内存 Map。反向代理必须覆盖用户自带 X-Real-IP，Next 的 `BLUEPULSE_TRUST_PROXY=1` 仅在此信任链建立后启用；否则保持关闭，开发环境仅使用实际连接地址。不要信任浏览器任意上传的转发头。
5. **先交付本机查看与处置**：扩展现有 `python -m bluepulse_backend.cli`，保留 bootstrap-admin。增加 `feedback list --status new --page 1 --q 关键词`（50 条／页、按创建时间倒序）、`feedback show <id>`（完整文字／邮箱／关联页／状态／备注／updated_at／私有截图绝对路径）。命令仅在后端机器使用，不因此开放匿名管理 HTTP。
6. **本机管理命令**：`feedback update <id> --status resolved --note "处理说明" --version <updated_at>`、`feedback erase <id> --reason "删除原因"`、`feedback ban <source_hash> --reason "原因"`、`feedback unban <source_hash>`；管理员身份需由受控本机参数关联已有有效管理员，缺失身份拒绝管理写入。状态为 new/triaged/replied/resolved/spam；replied 是手动联系后的标记，不代表系统自动发了邮件。更新校验乐观版本，处置及审计同事务。删除清空个人材料并移除私有图片，保留最小处理记录和审计；处理完成或用户要求时执行删除，截图不套用飞书模式的自动过期规则，备份包含未删私有文件。
7. **后续网页后台**：在同站管理员会话、CSRF、服务端鉴权、审计落地后，增加 `/admin/feedback` 的列表、筛选、详情、授权截图读取与上述操作。当前不新建可匿名访问的反馈列表，也不让反馈编号成为公开查询凭证。
8. **联调启用**：完成下述测试后，将 Next 服务端 `BLUEPULSE_FEEDBACK_ENABLED=1` 并重启／部署；页面和代理同时读取该配置。默认关闭，不能只改前端按钮。TLS 反向代理部署必须设置 `BLUEPULSE_SITE_ORIGIN=https://实际公开域名`，防止 Next 内部监听地址和公开 Origin 不同导致误拒绝；不读取任意客户端 X-Forwarded-Host 来放宽来源校验。若配置与后端状态不一致，显示服务不可用并保留草稿。

### 5. 请求响应示例与查看方法

```http
POST /api/v1/site/feedback
Content-Type: multipart/form-data; boundary=...

content=文章中的原文链接打不开
email=reader@example.com
pageUrl=/articles/<uuid>
screenshot=<可选的一张图片>
```

成功：`201 {"id":123}`、`Cache-Control: no-store`。错误沿用 Pulse：`{"error":{"code":"rate_limited","message":"提交太频繁，请稍后再试。","request_id":"..."}}`。code 至少区分 invalid_request/forbidden/rate_limited/temporarily_unavailable；400 校验、403 封禁、413 太大、429 限流、503 服务故障。回执只在记录持久提交后产生。前端仅接受 **201 + 正整数 id**；200、缺 id 或错误 JSON 不清草稿。

后端完成后，用户在后端机器执行：

```powershell
Set-Location D:/pulse/backend
uv run python -m bluepulse_backend.cli feedback list --status new
uv run python -m bluepulse_backend.cli feedback show 123
```

以上是**待实现命令**，当前运行会失败。show 应输出截图本机路径，用户可在该机器查看；无需飞书、公开下载链接或等网页后台完成。将来 `/admin/feedback` 已完成并验收后，才可告知用户在网页查看。

### 6. 缓存和异常

反馈 POST、错误及管理读取均 no-store。Next 精确代理只转发 multipart 和必要请求标识，不转发 cookie／Authorization；15 秒上游超时，最多缓冲 12MiB，超限即时拒绝。普通模式关闭时返回 503 feedback_not_connected，完全不访问后端。代理不跟随重定向。

前端先读取草稿再开启 400ms 自动保存，离开补存；损坏原数据不覆盖，拒绝存储时明确提示内存暂存。显式 from > 已有草稿关联页 > 最近站内页／同站 referrer；截图不会写 localStorage。失败保留文字和附件；发送禁用表单并有同步守卫。超时或断网可能已经入库，不能断言“没有发送”；提示结果无法确认，避免连续重复发送。后端本轮契约未承诺网络未知结果的跨请求幂等。

### 7. 验收条件与变更记录

- 后端：合法纯文字／带图真实入库；格式、空值、2/5000 字、8MiB/12MiB、像素及伪图片；重复附件独立删除；写库失败无孤立文件；可信 IP、5 次限流、封禁和多进程一致性；私有截图权限；版本冲突、删除和审计；CLI 查看／筛选／处理；无飞书外发。
- 前端与代理：草稿初始化不被空值覆盖、离开／刷新恢复、存储拒绝、live/mock 隔离；pick/drop/paste/remove；发送防重；201 有效回执、400/403/413/429/404/503、错误 JSON、断网与未知结果；桌面／窄白纸／reduced-motion。
- 本轮仅以本地受控测试服务证明契约与界面，**不代表真实 FastAPI 联调或真实反馈收集已完成**。实际验收见专项记录。


## DOCK-004：全部动态、分类筛选与全文检索

### 1. 功能与状态

匿名入口 `/all` 本轮按已批准计划及后续源码复用纠正复用 AIHOT 全部动态页，放入 Pulse 共享 p0。交付范围包括分类、搜索、北京时间分日时间轴、卡片、当前浏览器收藏／已读及40条游标翻页；不新增独立主题模块。修订稿前端及受控接口检查已通过，详见 [专项验收](docs/pulse-all-verification-2026-10-29.md)，不代表真实后端已补齐或完成联调。

- 既有后端已实现：文章列表、taxonomy、公开文章过滤、全文匹配、recent／importance 排序和绑定筛选的游标。
- 本轮不修改后端。`product/practice/paper/law/embodied/public-opinion/low-altitude` 的 taxonomy 注册、历史文章归类及持续分析分类仍需后端组员确认、补齐；仅有 topic 查询参数不代表这七类已有真实数据。
- 前端按真实 taxonomy 区分“分类暂不可用”和“已注册但没有内容”，不以关键词或旧宽分类近似替代。真实总量、页数、今日总量、相关度和繁忙保护不能从40条结果推导。

### 2. AIHOT 源码证据

本轮重新静态核对 `D:/AIHOT` 下载快照，未运行其服务；完整 MIT 与 `Copyright (c) 2026 数字生命卡兹克` 见 `THIRD_PARTY_NOTICES.md`。

| 环节 | 原始源码及符号 |
| --- | --- |
| 页面、查询、筛选保留与排序 | `apps/web/app/routes/all.tsx`：`loader`、`AllPage`、`pageHref` |
| 分类、搜索、活动条件 | `apps/web/app/features/feed/Filters.tsx`：`CategoryTabs`、`SearchField`、`ActiveFilters` |
| 分日、数字页、卡片与时间槽 | `features/feed/DayList.tsx`：`DayList`、`Pagination`；`FeedItem.tsx`；`Timeline.tsx`：`DayHeader`、`TimelineSlot`；`components/ui/Tabs.tsx`：`PillTabs` |
| 契约与 API | `packages/contracts/src/site.ts`：`PoolResponse`；`apps/api/src/routes/site.ts`：`/api/site/pool` |
| 读取、检索、数量和繁忙保护 | `packages/backend/src/publication/pool.ts`：`loadPool`、`POOL_PAGE_SIZE`、`POOL_MAX_PAGES`、`withSearchCapacity`、`SearchBusyError`、`directMatchCondition`、`publicMatchCondition` |
| 浏览器状态与有效期 | `apps/web/app/lib/{local-state,restore,session-cache,page-reuse,api.server}.ts` |

上述相对路径均相对于 `D:/AIHOT`；Pulse 依据为 `backend/bluepulse_backend/api.py` 的 `list_articles`、`list_taxonomy` 及 `editorial.py` 的 `public_article_conditions()`。

### 3. AIHOT 原始数据流与契约

原 `all.loader` 读取 URL 的 q、tab、page 和筛选，经 Web HTTP 客户端访问 `/api/site/pool`，返回 `PoolResponse`。每页40条、最多50页；真实 total、pageCount、todayCount、freshness 支撑数字页、今日数量与更新时间，超出末页会保留条件跳转末页。默认最新检索为标题／摘要等直接匹配，全文相关是另一路排序，不能混写为 Pulse 的同一能力。

`DayList` 按北京时间组织 `timelineAt`，复用 `TimelineSlot` 和 `FeedItem`，已读状态由本浏览器提供。搜索和分类修改保留彼此条件并清页码。原检索容量保护限制并发4、队列8，排队超过3秒或溢出返回503及 Retry-After；这是 AIHOT 原实现，Pulse 当前未因此获得限流能力。原公开列表使用 `listedCondition`；不能直接搬 SQL 或用有详情等同有公开列表／全文分发许可。

### 4. Pulse 建议及差异

Pulse 保留 Next.js／FastAPI 和 UUID，独立 `src/app/all/` 组件负责页面，`_data.ts` 承担纯数据／URL helper，`_cache.ts` 承担数据缓存；不移植 React Router loader、PostgreSQL SQL 或全站壳层。按 p0 实际宽度排布工具栏、吸顶日期与移动时间栏，保留品牌与导航动效。

顶层分类为全部、国内、国外、产品、实战、论文、法制、具身、舆情、低空；地区和内容分类单选互斥，地区对应 `region=domestic/foreign`，后七类对应上述新 topic 键。旧宽分类深链完整保留在请求中，不静默映射到新分类，也不为它额外添加 legacy 筛选 chips 行。仅 `/all` 默认 `period=all`，不改变其他阅读入口的默认时间。搜索 q 与分类互相保留，改变条件重置游标；Enter、清空、斜杠聚焦及输入法需前端验收。

当前 q 真实匹配原题／中文题／摘要／正文；SQLite 满足条件时走 FTS5，否则转义 LIKE。搜索统一 `sort=recent`；旧 importance 搜索链接归一并丢弃旧游标，非搜索的 importance 浏览仍保留。importance 不能冒充全文相关度。前端“全文相关”入口禁用，通过 title 属性说明待接入，不添加搜索模式说明行。未知发布时间的原 time 节点显示“待核”，title 明确真实发现时刻，不额外添加“发现于”行或伪装发布时间。

2026-10-29 用户追加的源码复用约束覆盖初稿视觉处理：分类控件直接沿用 `Tabs.tsx:PillTabs` 结构，选中 thumb 位于 active link 内部；md 尺寸为36px高、16px横向 padding、14px字号，不压缩为9px padding／13px字号。`/all` 到 `/all` 的查询更新使用普通 push，不触发 Pulse 整页 GSAP 淡入淡出；AIHOT `all.tsx` 的 busy 反馈是保留旧列表、仅 opacity 0.5，不添加骨架卡片。

日期按 `Timeline.tsx:DayHeader` 与 `lib/format.ts:monthDay` 的月日加星期排布，遵从用户要求不显示年份或“今天”。恢复 `TimelineSlot` 的64px／22px时轨、`parts.tsx:SourceLine` 与 time 同行；移动端标题17px两行、摘要14.5px两行，不显示 topics；`components/ui/Score.tsx:ScoreLabel` 按85／70阈值复用分层胶囊。移除另加的 region 标签、每页条数行、legacy chips 行；Mock 只在同一 h1 文本标注演示，不独立加说明行。异常内容沿用 `components/ui/Page.tsx:EmptyState` 布局，仅保留真实必要回退；后端缺口在本文交接，不再转化为新增页面组件或额外文字行。

后端交接：注册七类稳定 slug 与中文名；给出多分类规则、历史回填方案、分类提示词版本与输入版本绑定，保留人工覆盖且避免重分析覆盖人工结果。若补数字页／统计，须定义同一筛选和公开范围下的 total、pageCount、北京时间 todayCount，以及时间未知／回灌文章口径、最大页深和越界策略；不可直接将游标当数字页。相关度需独立稳定排序和与条件绑定的游标／分页契约。繁忙保护需定义容量、取消、超时、503／Retry-After 与客户端重试行为，不能只靠按钮 loading 防止服务过载。

### 5. 请求响应示例

以下为当前契约示意，不是联调数据；本地页面入口为 `http://localhost:3000/all`，分类例为 `/all?topic=product`，搜索例为 `/all?q=警务`。

```http
GET /api/bluepulse/taxonomy
GET /api/bluepulse/articles?period=all&limit=40&sort=recent
GET /api/bluepulse/articles?period=all&limit=40&sort=recent&topic=product&q=警务
GET /api/bluepulse/articles?period=all&limit=40&sort=recent&region=domestic
```

代理映射到同后缀 `/api/v1/`。taxonomy 返回 `items`，元素为 `id/slug/name_zh/name_en/parent_id`（`parent_id` 可空）。articles 返回 `items/next_cursor/limit`；items 内含真实卡片、`topics` slug 数组及可空 `summary`。列表最多返回请求的40条，`next_cursor=null` 表示无下一页；其他请求的 limit 当前允许1–100。后续页原样携带 next_cursor 和完全相同的筛选／排序；筛选不匹配时后端400 `invalid_cursor`。返回上一页依赖本会话游标历史，直达而无历史时回第一页，不构造 pageCount。当前响应没有 total、pageCount、todayCount、freshness，不能补造。

### 6. 缓存和异常

保留共享的服务端绝对截止策略：同标签页本地最多60秒，合并 articles／taxonomy 取最早截止，尊重 Cache-Control、X-Accel-Expires、Date、Age；no-store／no-cache 不进入可复用列表快照。30分钟历史／锚点恢复独立于数据寿命，过期重新请求再恢复位置。刷新／重试强制新取，旧请求取消或晚到不能覆盖新的搜索／分类结果。

taxonomy 未注册与 taxonomy 请求失败不能变成“零篇”；已注册且 articles 成功空数组才是真实无结果。列表故障保留查询并可重试；游标失效明确处理，不无限重试。Mock 如用于前端检查应显式标识、与真实缓存隔离，不能作为分类、统计或后端完成证据。

后端仍需使发布、撤回、证据和全文许可在列表、详情、收藏可用性及未来出口一致生效，并返回与真实读取缓存一致的截止头；不得用客户端缓存延长已撤回／无权内容的公开寿命。当前复用 existing public_article_conditions 不代表完整 AIHOT 发布层已经移植。

### 7. 验收条件与变更记录

2026-10-29：追加本节并按用户纠正对齐原组件结构／尺寸、简单查询导航和无额外 UI。最终修订稿 lint、生产构建、26项相关逻辑、18组全部动态浏览器场景和13组共享导航场景通过；桌面1360×760、移动390×844及 reduced-motion 截图已复核。最终源码审查无阻断项。完整来源映射、检查范围及复现方法见 [专项验收](docs/pulse-all-verification-2026-10-29.md)。使用受控 HTTP 测试服务，没有将 Mock／静态研究视作真实 FastAPI 联调完成。

验收须覆盖搜索／分类互相保留与重置游标、地区和内容互斥、旧深链请求保留且不添加 chips 行、缺分类与真空结果、40条游标上下页与无历史回首、发现时间标识、收藏／已读、真实全文最新与禁用相关入口、统计不伪造、缓存截止／竞态／历史恢复。新分类注册和历史归类、真实统计／数字页、相关度、繁忙保护及统一发布许可缓存需后端契约测试和真实联调另行签收。

## DOCK-005：收藏可用性与本地阅读备份

### 1. 功能与状态

匿名收藏页 `/starred`，使用现有 p0 白纸和内部滚动。前端复用 AIHOT 的标题／工具、本机提示、导入回执、空态、收藏卡片和取消操作。收藏500条、已读5000条、浏览历史30篇分别管理；导入导出无需登录或服务端写接口。清除浏览器数据或换设备不会自动同步。

状态：前端已实现并经受控接口检查；现有 FastAPI 布尔可用性接口静态核对已实现。本轮不改后端，真实部署联调尚未进行；原站的仅摘要权限和当前来源名待组员扩展。

### 2. AIHOT 源码证据

- `apps/web/app/routes/starred.tsx:StarredPage,reportText`：工具、文件操作、批次核验、卡片、权限提示和返回锚点。
- `apps/web/app/lib/local-state.ts:exportBundle,importBundle,mergeLocalData,markRead`：version 1 备份、2,000,000字符上限、已有收藏优先、已读合并、部分写入失败。
- `apps/web/app/components/ui/Presence.tsx`、`components/shell/nav.ts`、`components/icons.tsx`：提示出入场、收藏入口及图标。
- `packages/contracts/src/site.ts:ItemAvailability`、`apps/api/src/routes/site.ts`、`packages/backend/src/publication/availability.ts:itemAvailability`：`public|summary-only|unavailable`、当前来源名及详情公开资格。路径均相对 `D:/AIHOT`。

### 3. AIHOT 原始数据流与契约

收藏是浏览器快照，不是服务器收藏表。页面 hydration 后读取本地列表，对 ID 分批请求 `/api/site/items/availability`（每批100，避免过长请求行）。返回按 ID 映射的 `{status,sourceName?}`；读取层遵循 `hasItemPage`，并不要求必须在公开列表中。不可用收藏保留快照及移除入口，不能通过旧收藏读回撤回正文。

原版导出 `{version:1,starred,read,theme}`。导入不覆盖已有同 ID 收藏，归一化字段，按 savedAt 新到旧排序，上限外／无效记录计入跳过；先保存收藏，再保存已读，已读失败单独报告。模块导入扩展在该下载快照中为空，本轮不制造额外按钮。

### 4. Pulse 建议及差异

Pulse 保留现有 UUID、收藏键 `blue-pulse-starred-items-v1` 和历史键。新增 `blue-pulse-read-items-v1`，首次缺失时从既有历史迁移已读 ID；后续阅读同时写已读和历史，导入已读不生成历史、清空历史不清已读。`?mock=1` 的全部浏览器键追加 `:mock`，与真实数据隔离。外观系统未建设，导出 theme=auto、导入忽略 theme。

现有 FastAPI `backend/bluepulse_backend/api.py:article_availability` 接受每批最多100个 UUID，返回 `items:[{id,available}]`，中间件设 `no-store`。前端严格校验每批 ID 唯一且完整、available 为布尔；映射 true→public、false→unavailable。旧响应无需升级即可使用。

建议组员按同一详情公开政策，在每行保留 available，并可选增加 `status:public|summary-only|unavailable`、`source_name:string`。summary-only 仍可打开受限详情，因此 available=true；unavailable 对应 false，不返回私有来源名。状态与布尔不一致时前端视该批次为未知。**不能依据 body_status、翻译失败或采集不到正文推断来源许可。**统一全文许可和发布层仍按阶段B实施。

### 5. 请求响应示例

```http
GET /api/bluepulse/articles/availability?ids=00000000-0000-4000-8000-000000000001
```

现有真实契约：

```json
{"items":[{"id":"00000000-0000-4000-8000-000000000001","available":true}]}
```

可选扩展（前端已兼容，**后端待实施**）：

```json
{"items":[{"id":"00000000-0000-4000-8000-000000000001","available":true,"status":"summary-only","source_name":"当前公开来源"}]}
```

空 ID 返回 `{items:[]}`；非法 UUID 或超过100条返回422。默认只读取当前浏览器已有收藏，不能空页自动填入测试新闻。显式 `/starred?mock=1` 只核对已有 Mock 文章，不请求真实接口、不自动创建收藏。可在 `/all?mock=1` 或演示详情收藏后查看。

### 6. 缓存和异常

每批100个 ID 并行核验，前端 `cache:no-store`、12秒超时；任一批失败仍保留其他批成功。失败／缺项／重复项／错误字段属于未知，保留原收藏与可尝试的详情链接，不显示撤回结论。退出页面、ID集合变化、mock切换或当前菜单刷新时取消旧核验；结果与请求键绑定，旧结果不能覆盖新列表。

本地列表读取完成即可显示并报告 RouteReady，网络核验不阻挡阅读或返回锚点恢复。现有30分钟位置快照只恢复滚动，不缓存可用性结果，也不延长公开权限有效期。

导入允许重复选择同一文件并防重复执行；损坏的已有收藏不被覆盖。收藏持久化失败整次导入失败，已读写失败报告部分成功。普通收藏／阅读沿用现有内存降级提示。备份仅包含显式收藏元数据及已读 ID，不含文章正文、账号、管理员凭据或浏览历史。

### 7. 验收条件与变更记录

2026-10-29：完成前端源码适配与接口交接。专项逻辑、浏览器检查及截图见 [收藏页验收记录](docs/pulse-starred-verification-2026-10-29.md)。检查覆盖500／5000上限、迁移、备份往返、重复／非法导入、持久化失败、部分成功、跨标签同步、批次部分故障、撤回／仅摘要、刷新重核验、窄白纸和返回位置。

受控 HTTP 返回扩展字段只证明前端消费能力；不能视为真实 FastAPI 已实现来源许可、来源更名或 AIHOT 完整统一发布层。真实联调需组员补齐字段与权限一致性测试后单独签收。

## DOCK-006：精选时间线、同新闻阅读组与内嵌热点

### 1. 功能与状态

匿名读者在 `/` 按北京时间阅读已确认精选，使用分类、日期折叠、连续加载、本浏览器收藏／已读和同新闻其他报道；未筛选首屏可显示当前热点。完整复用所选 AIHOT 前端机制并适配 Pulse，后端仍由队友实施，本轮不修改 FastAPI。

- 前端已实现：`src/app/_components/featured/` 的编排、读取、校验、缓存、显式 Mock 和时间线；`_components/feed/` 的共享工具栏、FeedItem、DayHeader、TimelineSlot、阅读组、Faces、SourceAvatar、Sheet、Lightbox、Presence、Badge。`/all` 同时使用共享组件，分类状态各自由 URL 控制。
- 精确同源代理已预留：`GET /api/bluepulse/site/timeline` 和 `GET /api/bluepulse/site/groups/:factId/reports`；不开放任意 `site/*`，不新增写接口。
- 后端待实现：Fact／Story、入选归组门禁、固定时间锚点、同范围代表／计数、公开阅读组、独立参与方热点及发布／撤回／全文许可统一政策。新接口尚待真实联调；最终前端验证由专项记录另记。
- 既有 `home/featured` 六槽只服务 Pulse 封面，不能代替 timeline。原首页最近采集／全部动态回退不再充当精选内容。`/story/:publicId` 目前仅为诚实的待接入目标；完整事件页、热点榜后端、日报均未由本轮完成。

### 2. AIHOT 源码证据

2026-10-30 直接复查 `D:/AIHOT` 静态下载快照与 Pulse 本轮实现；未启动或验证 AIHOT 服务、数据库、worker 或线上站点。

| 环节 | 原始源码及关键符号 |
| --- | --- |
| 首页、筛选和搜索归属 | `apps/web/app/routes/home.tsx: loader, Home`；`features/feed/Filters.tsx: CategoryTabs, FeedBar, SearchField` |
| 分日、折叠、分页、位置 | `features/feed/Timeline.tsx: Timeline, DayHeader, TimelineSlot, AUTO_BATCHES` |
| 卡片与条件内容 | `features/feed/FeedItem.tsx: FeedItem`；`parts.tsx: SourceLine, MediaThumbs, StarButton`；`ReadingGroup.tsx: useReports, GroupSources, GroupButton` |
| 热点与头像 | `features/feed/HotTopics.tsx: HotTopics, TrendMark`；`features/hot/Faces.tsx: Faces`；`components/ui/SourceAvatar.tsx` |
| 交互基础 | `components/ui/{Sheet,Lightbox,Presence,Badge,Tabs}.tsx`：抽屉、图片浏览、折叠、入选／同新闻标记和选中滑块 |
| 跨进程契约和 API | `packages/contracts/src/site.ts: TimelineResponse, TimelineCard, GroupInfo, GroupReportsResponse, HotStripEntry`；`apps/api/src/routes/site.ts: /api/site/timeline, /api/site/groups/:factId/reports` |
| 公开读取与代表 | `packages/backend/src/publication/timeline.ts: loadTimeline, countTimelineDays`；`groups.ts: loadGroupReports`；`hot.ts: loadHotStrip, rankingExtras`；`representative.ts: pickRepresentative` |
| 资格、归组和热度 | `publication/{scope,publish}.ts: selectedCondition, listedCondition, evidenceCondition, publishArticleTx`；`events/{group,relate,hot}.ts: groupArticle, recordSignal, RELATIONS, computeHotRanking` |

Pulse 请求／共享类型真值为 `src/app/_lib/feed-types.ts`；原有 ArticleCard／Source 字段真值为 `_lib/home-data.ts`。本轮不复制 React Router loader、PostgreSQL SQL 或 pg-boss；来源许可见 `THIRD_PARTY_NOTICES.md`，保留完整 MIT 与 `Copyright (c) 2026 数字生命卡兹克`。

### 3. AIHOT 原始数据流与契约

`home.loader` 把非空 `?q` 转到 `/all`，经站内 HTTP 请求 timeline。API 并行读取 `loadTimeline` 和未筛选首屏 `loadHotStrip`；原筛选为 channel/category/tag。timeline 先在相同筛选及 `selectedCondition(now)` 下按 Fact／独立 Article 形成卡片，再在同范围精选证据中选择代表，最后装载展示字段并再次检查公开范围，避免读期间撤回仍泄露。

同次发生的重复报道折叠为一个 Fact；同一 Story 的新发展另有 Fact，不把旧新闻顶回列表头。归组卡片使用第一次出现的稳定时间锚点；`anchorAt` 决定分日和时轨，不是代表文章的抓取时间。原查询按 anchor 倒序及稳定组键排序，游标绑定筛选。`dayCounts` 对返回日期统计完整筛选后归组集合，不是本批条数。

代表优先级在调用者限定候选范围内为 T1、经核实的当事机构／个人、许可全文、分数、较早时间及稳定 ID。不能跨筛选借用代表。阅读组来自同 Fact 的公开、eligible、已释放 primary/report 证据，包含未入选报道；mention 不算证据。`additionalSourceCount` 为排除代表来源后的不同来源数，`reportCount` 为不同文章数；不等于热度独立参与方数。原组接口最多100篇，无可见成员返回404。

分数只产生候选。原门禁为 `selectionCandidate && grouping_status === "complete" && (override.selected === true || selection_adds_value !== false)`；null 不等于 false，人工决定保留，但不跳过候选和归组完成。归组等待只允许符合条件的全部动态，不因等待超时自动入选。资格、公开时间、撤回、证据角色、站内全文与再分发权限必须统一落实在后端读取政策。

热点来自独立参与方归一后的48小时证据，24小时半衰、可信源时间和采集时钟；至少两个参与方且一个 editorial 才进入计算候选。与六小时前的比较只使用两窗覆盖可比的参与方，资料不足返回 `unknown`。`publication/hot.ts` 读取榜单后重查当前公开证据，少于三条可见事件不展示内嵌条。热度不是文章 importance_score、报道数量或浏览器点击量。

### 4. Pulse 建议及差异

Pulse 保留品牌、本地 Google Sans／微软雅黑、p0 白纸、封面六槽、菜单和导航转场；移除 AIHOT 的重复整页背景与框架，以 Next.js 路由及 p0 内部滚动适配组件。筛选替换为现有国内／国外和七类稳定 slug：`product/practice/paper/law/embodied/public-opinion/low-altitude`；`all` 只表示无筛选，不是新主题模块。taxonomy 未注册的类明确不可用，不用近似旧类补齐。

- 新后端 `GET /api/v1/site/timeline`：`region` 为 `domestic/foreign` 或省略；`topic` 为七类 slug 或省略；`cursor` 不透明或省略；`limit` 默认20、最大40。响应 camelCase 外层保留 AIHOT 结构，item 复用 Pulse ArticleCard 的 snake_case 字段和 UUID，不转换为 AIHOT 短 ID。timeline item 必须明确 `selected:boolean`；可选 sameEvent/channel/x 沿用共享 FeedArticle。普通 `/articles` 可增同样的可选元数据，旧响应缺字段不推断入选或同新闻关系。
- `key`、`factId`、`storyPublicId` 为稳定公开字符串，满足 `^[a-zA-Z0-9_-]{1,80}$`，不暴露数据库行号作为临时身份。`anchorAt` 是服务端时间线事实，不以 `first_seen_at`、前端当前时间或新代表时间替代。分组代表、计数、成员读取共用当前筛选；`dayCounts` 每个返回日期都给完整分组总数。
- `GET /api/v1/site/groups/:factId/reports` 使用同一 region/topic；最多100篇，字段见下节；匿名 no-store，不读取管理员权限或触发采集／模型。文章详情和外链继续使用当前 UUID 与允许公开的 originalUrl。
- 内嵌热点只随无筛选 timeline 第一页返回；其他页／筛选为 null，不要求为此另建独立 `/hot` 接口。最多五条，窄内容宽度三条；Faces 最多六个 editorial 头像，`+N=participantCount-已显示头像数`，包含 signal。participants 名称供悬停名单；iconUrl 可缺并退回名称首字，iconSrcSet 可选，由后端提供经过安全图片代理的 URL。前端不临时抓来源图标或自算热度／趋势。
- 热点链接优先 `/story/:publicId`，其次 `/articles/:uuid`，最后 `/hot`；当前 story 只显示待接入状态，不把静态目标写成完整事件模块。未知趋势不显示箭头。
- 精选和 `/all` 共用 FeedToolbar、FeedItem、DayHeader 和时轨；菜单进入重置当前栏目，历史返回恢复原筛选／位置。搜索去 `/all` 并保留筛选，旧 `/?q=…` 重定向。页内筛选不触发整页淡入淡出，不增加可见辅助说明行、虚构统计或新指标。
- IntersectionObserver 以 p0 scroller 为根，预距900px；首批计入三批自动加载，之后显示手动加载。按 card.key 去重，cursor400重读头部；筛选／刷新／离开中止更多请求并丢弃过期响应。760px工具栏、600px卡片、640px热点均按内容宽度响应；日期依用户既定要求仅月日和星期，无年份／今天。日期折叠、桌面阅读组展开、移动抽屉、原帖媒体／引用条件分支保留。

### 5. 请求响应示例

浏览器 `GET /api/bluepulse/site/timeline?region=domestic&limit=20` → `{BLUEPULSE_API_URL}/api/v1/site/timeline?region=domestic&limit=20`。下例仅说明形状，不代表真实警务新闻或业务统计；字段定义以共享类型为准。

```json
{
  "filters": { "region": "domestic", "topic": "" },
  "cards": [{
    "key": "fact_demo_01",
    "anchorAt": "2026-10-30T01:00:00Z",
    "item": {
      "id": "00000000-0000-4000-8000-000000000001",
      "title": "警务科技资讯示例",
      "source_title": "示例原题",
      "published_at": "2026-10-30T01:00:00Z",
      "first_seen_at": "2026-10-30T01:10:00Z",
      "language": "zh", "region": "domestic", "country_code": "CN",
      "url": "https://example.com/report",
      "source": {
        "id": "00000000-0000-4000-8000-000000000101",
        "name": "示例公开来源", "slug": "example", "region": "domestic",
        "country_code": "CN", "language": "zh", "source_type": "government", "topics": ["practice"]
      },
      "importance_score": 80, "processing_status": "processed", "parse_status": "parsed",
      "topics": ["practice"], "summary": "示例摘要。", "featured_reason": "示例理由。",
      "selected": true, "sameEvent": null, "channel": "news", "x": null
    },
    "group": { "factId": "fact_demo_01", "additionalSourceCount": 1, "reportCount": 2 }
  }],
  "nextCursor": null,
  "hot": null,
  "dayCounts": { "2026-10-30": 1 }
}
```

所有外层字段必须存在；无筛选响应 filters 的 region/topic 为 `""`。真空结果为 `cards:[]`、`nextCursor:null`、`dayCounts:{}`；`group:null` 为无阅读组，不能省略。hot 为 null 或 HotStripEntry 数组；条目字段为 `rank/title/heat/trend/storyPublicId/itemId/participants/participantCount`，trend 枚举 `up/down/flat/new/unknown`，participants 为 `{name,kind:"editorial"|"signal",iconUrl?,iconSrcSet?}`，无事件／文章目标用 null。少于三条可见热点返回 null。

浏览器 `GET /api/bluepulse/site/groups/fact_demo_01/reports?region=domestic` → FastAPI `/api/v1/site/groups/fact_demo_01/reports?region=domestic`：

```json
{
  "factId": "fact_demo_01",
  "reports": [{
    "id": "00000000-0000-4000-8000-000000000001",
    "title": "同一新闻的报道示例",
    "source": { "name": "示例公开来源" },
    "timelineAt": "2026-10-30T01:00:00Z",
    "originalUrl": "https://example.com/report"
  }]
}
```

reports 可包含代表本身，前端展示时去掉 parentId；不以删除代表后的行数回写业务统计。正式实现应校验参数、UUID、日期、稳定排序／游标绑定与安全 URL。原帖／图片／引用字段完整结构见共享 `MediaView/XPostView`，不从缺正文或来源名称猜测。

### 6. 缓存和异常

当前 document 最多16个精选页面数据项，本地寿命最多60秒；timeline、taxonomy 与所有已加载批次取最早上游截止。沿用 `Cache-Control/X-Accel-Expires/Age/Date`，`no-store/no-cache` 不进入可复用数据快照，SSR／代理不能重新延长旧结果寿命。后端仍需提供真实截止与撤回失效政策，前端上限不是统一发布链已完成的证明。

30分钟仅用于历史位置、加载批数、日期折叠与阅读组打开标记。过期返回先重读头部及恢复锚点所需批次，再恢复位置；主动刷新回到新头，重试强制取新。阅读组始终 no-store，仅保存打开标记，不把报道正文／列表当作可复用会话快照；返回重新核验，重新核验404清空旧行，首次失败显示可重试状态。前端读取等待上限12秒；共享同源代理上游仍为6秒，超时返回504，离开取消请求不显示故障。

| 情况 | 前端真实状态 |
| --- | --- |
| timeline 404 | 精选服务尚未接入，可重试 |
| timeline 200、合法空 cards | 当前筛选确实没有精选，不能补最近采集或演示新闻 |
| 503／504、网络、无效包 | 精选暂时无法载入，保留重试；不冒充空结果 |
| 不可用 taxonomy 分类 | 分类暂不可用，不自动近似或替换为其他类 |
| 更多请求 cursor400 | 读取新头、重置批次及折叠，丢弃旧游标列表 |
| 旧筛选／已离开请求返回 | 忽略，不覆盖当前结果 |
| 阅读组重新核验404 | 显示零行，不继续展示撤回前的快照 |

演示仅显式 `/?mock=1`；h1 标识“演示”，演示 timeline／taxonomy／阅读组及浏览器状态、缓存键均与普通模式隔离。不会因为真实接口错误自动切到 Mock，不自动给普通浏览器填入测试新闻；Mock 文章跳转保留 mock 参数。

### 7. 验收条件与变更记录

2026-10-30：建立 DOCK-006；完成所选前端源码的共享组件适配、精选编排、请求契约和后端交接。2026-10-31：最终 lint／生产构建、42项逻辑、28组精选浏览器场景、18组全部动态及13组导航回归通过；桌面／移动／reduced-motion 视觉复核和独立源码审查完成。复现、修正与验证边界见 [精选专项验收](docs/pulse-featured-verification-2026-10-31.md)。这些结果不代表真实 FastAPI 业务联调完成。

前端验收须覆盖桌面／移动／reduced-motion、共用 `/all` 回归、URL筛选独立、搜索／菜单／历史、三批自动再手动、key去重、cursor400、日期折叠／锚点、阅读组重核验及失败、媒体／引用／头像降级、超时／取消、跨批截止与 mock隔离。受控 HTTP 契约检查须核验精确白名单、转发路径、状态与缓存头，不代表 FastAPI 真实业务完成。

后端签收须另行验证：候选与确认入选门禁及人工覆盖；同发生归组／新发展分Fact；固定anchor／稳定游标及完整分日统计；同范围代表、不同来源／报道计数、primary/report与mention隔离；最多100篇成员；独立参与方归一、48h／24h／6h覆盖与unknown趋势；撤回、延迟发布、全文权限及所有公开出口一致；截止后旧缓存不可续命。真实后端接口、数据迁移、权限与联调完成前不得把本模块标为业务完成。
