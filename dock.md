# Pulse 前后端接口对接总册

更新日期：2026-10-27。本文是可持续追加的模块对接报告。**建议契约不等于后端已实现；Mock 验收不等于真实业务联调。**

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
| DOCK-002 | 更新日志与未读提示 | `/changelog` | Next.js `GET /api/bluepulse/site/{changelog,meta}` | 已实现真实文件数据，待本轮验收；无 FastAPI 依赖 |
| DOCK-003 | 匿名反馈、草稿与截图 | `/feedback` | `POST /api/bluepulse/site/feedback` → 建议 FastAPI `/api/v1/site/feedback` | 前端及代理已预留，真实接收与查看待后端实施 |

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
