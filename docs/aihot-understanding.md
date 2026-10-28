# AIHOT 源码研究与 Pulse 移植依据

2026-10-28 补充：重新核对本地 `routes/changelog.tsx`、`features/changelog/text.tsx`、`routes/feedback.tsx`、`components/ui/Page.tsx`、`backend/site/meta.ts`、`operations/feedback.ts`、`admin/feedback.ts` 及 API／契约。更新日志是随代码部署的人工 JSON 数据，不含 push 自动总结；可选大版本绘图文件在快照中不存在。反馈是匿名 multipart → 校验／私有截图 → 数据库回执，飞书属于可选转发，本项目按用户要求排除。Pulse 的源码适配、缓存、精确接口、后端任务和反馈查看方式见根目录 `dock.md` DOCK-002／003；真实 FastAPI 反馈接收仍待组员实现。

研究记录日期：2026-10-11。范围：对 `D:/AIHOT` 下载快照及 Pulse 既有源码作静态阅读；未启动 AIHOT 自身的服务、数据库、采集、模型或推送，没有逐行全审。本文是长期定位索引，不是生产验收报告。Pulse 本轮基础功能已于 2026-10-25 完成限定范围验收，详见 [验收记录](aihot-foundations-verification-2026-10-25.md)；这不扩大 AIHOT 本身的研究验证范围。

## 1. 证据、快照与采用策略

`D:/AIHOT/.git` 不存在，因此不能提供 commit、tag 或 upstream 分支。文件目录时间集中在 2026-10-07，但文件时间不等于上游版本。`package.json` 声明 Node >=24.11；`apps/web/package.json` 声明 React 19.3.0、React Router 8.4.0、Tailwind 4.3.3、Vite 8.3.1。部署文件使用 PostgreSQL 17；后端 API 为 Fastify，任务为 pg-boss。版本是本地清单声明，不代表本机已经安装或生产正在运行这些版本。

复查快照可对以下文件计算 SHA256（2026-10-11 静态读取结果）：

| D:/AIHOT 原始文件 | SHA256 |
| --- | --- |
| `package-lock.json` | `BC076001F7D02A85C6BE942950710062968B5C2ACB720CE1203AE07816E5CD31` |
| `packages/backend/src/editorial/analyze.ts` | `CE7666625BD6B5D0E4EE98F955296E77A701F9C1C8ABB92A52757E29903B43AD` |
| `packages/backend/src/publication/publish.ts` | `FDAD99E051D57F8FCA6A939BE09A15232B07687ABF97C0CF55CC1F313CDB4850` |

已读架构、行业定制、精选、归组、信源、部署文档，并结合本文各节列出的实现核对。快照没有 `README.md`，入口是 `README.en.md`、`README.html`；英文 README 明确说明模型榜、Codex reset 监控、主题里程碑及作者自己的运营工具不随框架开源。本地 `site/modules/index.ts: MODULES`、`server.ts: SERVER_MODULES`、`web.ts: WEB_MODULES` 均为空，`modules/` 仅有 tsconfig。用户看到的线上菜单不能据此声称本地已有实现；本轮没有实时核验线上站点。

采用策略：Pulse 的业务策略尽可能采用 AIHOT，保留 Next.js 16 / React 19 / TypeScript / Tailwind 4 / GSAP 前端和 Python / FastAPI / SQLAlchemy / SQLite 后端。移植状态机、规则、契约及测试思路，不直接把 React Router loader、PostgreSQL SQL 或 pg-boss 搬进现有技术栈。先完成前端信息框架，缺失能力明确显示真实空态/待接入，随后由后端组员实施，再进行警务领域校准。

Pulse 基线依据：[宏观规划](system-construction-outline.md)、[Stage1](stage1-backend-plan.md)、[开发进度](development-progress-2026-10-06.md)、`D:/pulse/backend/bluepulse_backend/{models.py,api.py,editorial.py}`、`ingestion/{pipeline.py,model_adapter.py,lease.py}`。旧 Stage1 中“最低身份即可公开”已被当前 `public_article_conditions()` 收紧；不要把早期计划当作现状。本轮新增能力与旧基线分开记录，不能因路由存在而宣布 Stage2 或完整后台完成。

许可：`D:/AIHOT/LICENSE` 为 MIT，Copyright (c) 2026 数字生命卡兹克。复制实质代码应保留完整许可和版权声明。`NOTICE` 明确品牌名和 Logo 不在 MIT 授权中；保留 Pulse 品牌、`qlxf.svg` 几何及本地 Google Sans。来源新闻内容另受发布者许可约束；MIT 不自动授予全文转载权。

## 2. 页面、交互与 HTTP 依赖

原始路由入口：`D:/AIHOT/apps/web/app/routes.ts`；页面源码在同目录 `routes/`。服务端 HTTP 客户端：`lib/api.server.ts: apiGet, loadOr404, cachedPage`；站内 API：`D:/AIHOT/apps/api/src/routes/site.ts: registerSite, siteHandler`；跨进程契约：`D:/AIHOT/packages/contracts/src/site.ts`。Web 不读数据库、不持有模型密钥；公开站内 API 不读取管理员 cookie。

| 页面及交互 | AIHOT 接口/源码 | Pulse 对照、移植与缺口 |
| --- | --- | --- |
| `/` 精选、分类/频道/标签、阅读组展开、加载更多 | `/api/site/timeline` → `publication/timeline.ts: loadTimeline`；组内 `/api/site/groups/:factId/reports` → `loadGroupReports` | 既有 `/api/v1/home/featured` 是最多六席快照；主页面可保留封面六席与另设精选阅读流。归组/游标/阅读组需新后端，不能把六席等同 AIHOT 完整 timeline |
| `/all` 全部动态、时间/相关度搜索、筛选、翻页 | `/api/site/pool` → `publication/pool.ts: loadPool`；`routes/all.tsx` | 既有 `/api/v1/articles` 支持主题、地区、来源、实体、搜索、recent/importance、cursor；数字页与游标不可混用，先适配现有契约 |
| `/items/:id`、`/original`、收藏/已读/复制/分享/Markdown | `/api/site/items/:id`、`/:id/original`；`features/item/ReaderTools.tsx,ArticleBody.tsx,PosterSheet.tsx` | 既有 `/api/v1/articles/{uuid}` 返回原文、译文、正文/翻译状态、原站链接。许可、撤回、Markdown 和分享图后端需补；缺正文要明确说明 |
| `/hot`、`/story/:publicId`、趋势、后续进展 | `/api/site/hot`、`/api/site/stories/:publicId`、`/followups`；`publication/stories.ts: loadHot,loadStoryDetail,resolveStory` | 文章重要性排序不是事件热点。无事件后端时不造热门事件/曲线；合并事件返回 308 新地址 |
| `/daily`、归档、`/daily/:key`、周/月刊 | `/api/site/reports/:kind/latest-page`、`/:kind/:key`、`/:kind/navigation/:key`、日报月份接口 | Pulse 基线无报告模型/出刊流水。前端可先建立刊期阅读/空态，不能直接汇总当前文章假装已出刊日报 |
| `/topics`、`/topics/:slug` | `/api/site/topics`、`/topics/:slug`；`publication/topics.ts: listTopicSummaries,loadTopicPage` | Pulse 不采用独立主题模块；taxonomy 仅用于文章分类和检索筛选，entities 为保守名称匹配。此行仅记录 AIHOT 原实现，不作为 Pulse 菜单建设要求 |
| 搜索浮层、最近搜索、建议 | `features/search/SearchOverlay.tsx`；`/api/site/search/suggestions` | 可移植快捷交互与浏览器最近搜索；候选建议和搜索忙碌由后端提供，不伪造结果 |
| `/starred`、`/more`、外观主题切换/导入导出 | `routes/starred.tsx,more.tsx`；`lib/local-state.ts`；availability 接口 | 匿名本地状态可以直接采用；已撤回详情必须重新核验，不因本地收藏快照绕开公开范围 |
| 关于、反馈、条款、隐私、更新、Agent | `routes/{about,feedback,terms,privacy,changelog,agent}.tsx`；`site.ts`、反馈 API | 静态阅读框架可先做；真实反馈写入、反滥用/隐私与机器出口另需后端 |
| `/admin` 和各后台页 | `routes/admin/layout.tsx`、`lib/admin.server.ts`、`/api/admin/*` | 后续同站受保护；当前账户表/本机脚本不等于完整后台。公众不提供普通账号登录 |

AIHOT 采用 React Router 的 URL 路由、SSR 和正常导航，不在 GSAP 时间轴完成后才使路由具备语义。Pulse 可以让主页封面完成时记录“已看过”，正常菜单导航立即进入真实 URL；直接访问子页直接呈现子页稳定态。首次动画是否看过是 Pulse 的额外产品状态，AIHOT 并没有这一段 Pulse 封面动画可照搬。需要保留后退、刷新、深链接、查询参数和独立加载/错误/空态，不能仅在组件内部切换内容而 URL 一直不变。

## 3. 采集、身份、去重与修订

源码：`D:/AIHOT/packages/backend/src/sources/collect.ts`（抓列表→过滤→存材料→排处理；失败不推进成功游标）；`sources/{rss,web-list,json-list,x,mp}.ts`；`content/materials.ts: identityKeyFor, contentHash, upsertMaterial, decideTimeline, fillPublicationTime, isHistorical`；`content/provenance.ts`；外部入口 `apps/api/src/routes/ingest.ts`、`ingest/items.ts`。行业示例见 `industry/sources.json` 和 `docs/sources.md`。

同一材料身份优先显式 key、X tweetId、规范 URL，最后来源+URL+标题哈希；内容哈希由规范空白后的标题/正文/摘要组成。重复发现保留发现记录，真实内容变化才增 revision，保存 article_revisions；并发修改持有行锁。发布时间后补会重新判断历史状态，不能让旧分析继续代表新输入。聚合入口带来的官方链接可以经唯一官方发布者规则转归正确来源；来源身份与热度参与方身份需要分别维护。

`decideTimeline` 将超发现时间一小时以上的未来时间视为不可信；首次发现距原发布时间超过48小时、显式回灌、未知日期均标 backfill。历史材料按原时间归档，不伪装今天、不推送；未知日期等待可信日期。新信源首批默认30条/12个月，后续不无限扫更早存量。历史且陈旧/未知材料不创建事件和热度。初导当天的新消息并不全部被排除在事件之外，需看 `isHistorical()` 的具体条件。

参与方式 `editorial` 为编辑材料，`hot_signal` 只提供讨论证据，`isolated` 不公开；分级 T1/T1_5/T2/EXCLUDE_MP 和全文许可是不同维度。来源暂停不等于既有文章撤回。外推 `/api/ingest/items` 需 token、限量、限流，新建 external 默认不公开，所有入口共用材料规则。

Pulse：`ingestion/pipeline.py: canonicalize_url,_fingerprint,run_ingestion` 已有 URL 幂等、重复候选、来源结果；目前缺完整 revision/discovery/provenance 状态。可移植单一入口和输入版本模型；要适配警务采购公告修订、论文日期、转载归属及 robots/HTTPS allowlist，不替换已成熟的 NIJ/江苏/采购等 Python 适配器。不可把 first_seen_at 冒充 published_at。

## 4. 预筛、双评分、结构化与写作

源码：`D:/AIHOT/packages/backend/src/editorial/analyze.ts: runSelectionPrefilter,runSelectionScores,runStructure,runUnderstand,runAnalysis,normalizeAnalysis,analyzeArticle`；`editorial/{input,writing,prompts,models}.ts`；`industry/prompts/{prefilter,selection-score,structure,content-understanding,summarize-article,safety}.md`；`industry/selection.ts: SELECTION`；模型配置 `site/models.ts: PRESETS,DEFAULTS`。

预筛宽进：BLOCK 停止，PASS/UNKNOWN 继续；材料缺失下 BLOCK 不能当作确定无关。两次评分是独立调用，同标准同材料，`score1+score2 >= 2*threshold` 为够分，展示 floor(平均)。原 AI 阈值 T1=60、T1_5=65、T2=76，understandFloor=50；没有阈值的分级不参与精选评分。评分提示词内部按内容类型对 sig/nov/cred/reson/act 五轴加权，噪声压制、输入安全、事实边界不可丢失；模型输出契约是单 attentionScore，不要误写为已保存五轴分项。

结构化与评分并行，但写作等待结构化，分类/标签以结构化输出为准。scope 区分具体新闻、composite 综合稿与不足以确认的材料；事实框架、出处、条件供后续归组。够分及平均严格高于 understandFloor 的材料用理解式标题/答案先行摘要/理由，其余用短摘要写作。空正文/纯链接 X 帖保留链接、图片、引用，不调用写作/翻译模型制造补正文文案；真实 X 长文正常处理。提示词内容哈希代表版本，改提示词不自动重算已分析记录。

Pulse `model_adapter.py` 已有可注入兼容提供方，pipeline/processing/llm 已做中文标题、摘要、相关性、主题、精选候选和短篇译文；缺多步独立回执/双评分/结构化事实与版本冻结。应保留现有 Python adapter，拆分明确步骤和 schema，警务领域替换“重要/噪声”实例并用真实样本校准。参考 `D:/AIHOT/docs/selection.md`、`D:/AIHOT/scripts/eval-selection.ts` 及 Pulse selection 标注文档；避免凭感觉复制 AI 阈值。相关 ≠ 精选，采购公告 ≠ 已部署成效，厂商宣传 ≠ 独立效果证据。

## 5. Article—Fact—Story 与入选确认

源码：`D:/AIHOT/packages/backend/src/events/{group,recall,relate,merge,consolidate,corrections,digest}.ts`；`group.ts: groupArticle,recordSignal,resetAutomatic`；`recall.ts: RECALL_DAYS,rootFactOf`；`relate.ts: RELATIONS,PairSchema,BatchSchema,firmlyTied`；`publication/publish.ts: publishArticleTx`；`industry/prompts/group-*.md`、`docs/grouping.md`。

Article 是可追溯的一份材料；Fact 是同一次发生；Story 是该事件及其直接进展。fact_articles 的 primary/report 是证据，mention 是提及；综合稿不因提及被当作每件事的独立证据，不创建虚假的单一根事件。四关系 SAME_OCCURRENCE / SAME_STORY / UNRELATED / ROUNDUP，不能因公司相同就归一事件。召回最近14天事实，优先同 URL、引用/回复及标题摘要向量；未配向量时用字符 bigram 重合。模型判断关系和新增信息，格式/置信度不足不能当成功；关系评测与真实召回分别验收。

“够分”仅产生 selection_candidate。`publishArticleTx` 的直接入选表达式是 `selectionCandidate && article.grouping_status === "complete" && (f.selected === true || article.selection_adds_value !== false)`。这里要求 value **不为 false**，不是必须为 true：null 可通过，人工 `f.selected=true` 可覆盖 value=false，但仍不能跳过 candidate/归组完成条件。材料不足并非此表达式直接检查 scope；`events/group.ts` 对明确 `scope="unknown"` 且无 fact 的 unsupported 材料清理自动关系并 `markGrouped(...addsValue:false)`，进而影响入选；缺失的旧 scope 与明确不足另作区分，历史分支也有单独处理。分析与输入版本一致性在归组流程另有检查。

等待期间只进符合条件的全部动态，不获得精选席位、不产生同步记录、不推送。超过等待时长也不自动放行，10分钟后有告警/运行诊断，可人工重归组。重复新闻多份报道可入网页阅读组；没有新增信息的换皮报道或汇总保留全部动态。人工拆组、合并、覆盖由业务模块操作，同时更新公开结果与恢复记录。

Pulse 基线没有 Fact/Story/关系图，仅 ArticleTopic 和 ArticleEntity，实体关联是名称匹配。本轮“热点/日报”菜单壳不能代表关系后端完成。移植优先保留三层身份、证据角色、输入修订绑定与入选门禁，再实施向量召回；适配公安机构、项目、部署阶段和跨来源转载，后端阶段见交接稿。

## 6. 热点是独立讨论证据

源码：`D:/AIHOT/packages/backend/src/events/hot.ts: currentSignals,heatRows,computeHotRanking,behindSources,snapshotHeat,heatSeries,HOT_RULE_VERSION`；`events/group.ts: recordSignal,participantKey`；`publication/{hot,stories,story-evidence}.ts`。

最近48小时，24小时半衰期；同参与方在窗口只计一次，重复采集不增热。至少2个参与方且至少1个 editorial 参与方进入计算候选；社区可按作者，运营媒体矩阵通过 signal_group_id 合并为一个参与方。用可信来源时间定位证据，不以抓取时刻制造热度。热度信源只参与证据，不拥有普通详情页。前后6小时趋势只比较采集齐全的可比参与方；源落后、起监较晚时可返回 unknown/null，不能显示假下降；存储榜单在读取时重新检查公开范围。

Pulse importance_score 只代表内容判断，不能用于冒充这一热榜。可移植去重参与方、时间衰减、覆盖状态和可比趋势；警务领域要识别转载链、同机构官号、同一厂商稿件、采购镜像，缺覆盖时允许“资料不足”。后端需信号表、来源时钟、排名快照、事件图和读取层，不能只从前端访问量计算。

## 7. 日报、周报、月报

源码：`D:/AIHOT/packages/backend/src/reports/edition.ts: periodReports,dailyMemory,dailyEdition,arrangeDaily,periodEntries`；`reports/compose.ts: composeDaily,grounded,composeWeekly,composeMonthly,composeDueReports`；`reports/correct.ts`；`publication/reports.ts`；`site/site.ts: EDITION_TIMES,REPORTS`；`apps/worker/src/schedules.ts`。

日报默认每日08:00、前日08:00到当日08:00，规则编排不调模型。同事件一条，取报道最多事实里的权威代表；同日进展列下方，综合稿附到所涉及最重要事件。记忆最近7期去重；旧事件新进展只有当事方动作（非 commentary）或4家以上来源报道才争取正文，否则快讯。无精选但存在官方原帖且3个以上独立参与方的事件可补日报，不因此进精选/推送。重要性使用最高分、独立参与方、官方权威及跟进扣分；最多12正文、每来源最多2、最多10快讯；头条为第一条，2–4为看点。

每份精选按实际确认/公开时间跨截止归下一刊，不能回填并重写已出刊报告。周报默认周一10:00取20事件，月报每月1日10:30取30，均聚合已出日报、跨日同事件归一；模型只写总述及至少3件的栏目导读，不增删条目。`grounded()` 检查新名字/数字，不通过使用模板总述或省略栏目导读；这不是通用事实校验的全部保证。

每半小时补到期刊、失败/停机缺期，已有刊不自动重写，显式订正走 correct 模块。**源码优先的差异**：selection.md 有“无条目不出”的概括；当前 `composeDaily` 只有 entries=0 且 judgedReports=0 才抛错，已完成判断但无重大新闻可以输出 REPORTS.quiet 平静日报。Pulse 应保持“平静”与“上游没工作”两种状态。

Pulse FeaturedEdition/FeaturedSlot 是六条首页快照，不是 DailyReport/ReportEntry；公开日期筛选也不是日报。可移植纯规则日报及模型受限周月导读，需后端事件、事实、许可、选刊窗口、刊期幂等和证据引用。警务栏目与有效进展标准后续校准，不先假定已启用。

## 8. 统一发布层、许可、撤回、代表席位和 ledger

源码：`D:/AIHOT/packages/backend/src/publication/rules.ts: isPoolEligible,hasItemPage,isSelectable,bodyModeOf,mayRedistribute,isIndexable`；`scope.ts: listedCondition,selectedCondition,seatedCondition,evidenceCondition,ownFactEvidenceCondition`；`publish.ts: publishArticle,publishArticleTx,republishSource,syncLedger`（后者内部符号）；`representative.ts: representativePriority,pickRepresentative`；`v1.ts: selectedSnapshot,selectedChanges,ledgerEpoch,ledgerWatermark`。

写入时一次推导 publications：visibility、eligible、selected、selection_candidate、body_mode、seat、visible_after、revision；读取层共享领域政策，但**不是所有出口共用一个万能布尔过滤条件**。`listedCondition(now)` 要求 public+eligible+released；`selectedCondition` 要求 public+selected+visible_after已到，机器的 `seatedCondition` 还要求 seat；事件引用采用对应的证据角色/当前归属政策。

详情的 `rules.hasItemPage()` 只要求非 withdrawn 且来源 editorial，不要求 public、eligible 或列表收录；`detail.ts: loadItemDetail` 因而允许低相关、尚无中文摘要、未知日期等未列入列表的材料有详情页，通常 noindex，summary-only 另有受限呈现。Markdown 需进一步区分：虽然 rules.ts 注释把详情与导出并称，实际 `detail.ts: markdownAvailable,exportMarkdown` 额外要求 visibility=public，并有摘要、可显示原帖或许可全文可导出；它可不满足 listedCondition，但不能据 hasItemPage 推断非 public 详情也可导出。撤回和 hot_signal 不具普通详情/导出资格。

站内全文需 site_fulltext+确认正文，再分发需 syndicate_fulltext+full；许可均默认关。机器出口每 Fact 只有一个代表 seat，网页可保留多份报道。排序官方 T1、确实能代表主体的已确认发布者机构/个人、许可全文、分数、早时间、稳定ID；要读实际 `representativePriority`，不能认为来源写一个“官方”标签即可代表每件事。

撤回必须同步列表、详情、RSS、API、MCP、分享、SEO及报告引用。已出刊文字留历史，但当前引用不可公开时，移除依赖引用的导读/封面；不把旧报告当作撤回绕行通道。变更 ledger 使用事务锁保证 seq 顺序与提交顺序一致，selected_state/payload hash 防无意义 upsert；席位迁移会移除旧代表并增加新代表。客户端用 epoch/watermark/snapshot/changes，不能只用“最新发布时间”同步撤回。

Pulse `editorial.py` 当前已集中匿名公开/精选条件、尊重人工覆盖，但许可/发布快照/席位/ledger/所有出口尚不完整。可先沿用集中条件，后续独立 publication 服务与数据契约；SQL advisory lock、JSONB、Postgres 数组条件需适配 SQLite/SQLAlchemy 事务。不能把 AIHOT 完整 SQL 原封不动移植。

## 9. 缓存截止、搜索繁忙及浏览器状态

缓存源码：`D:/AIHOT/apps/web/app/lib/api.server.ts: cachedPage,pageHeaders`、`lib/page-reuse.ts: pageReuse,hasFreshPage`、`D:/AIHOT/apps/api/src/http/respond.ts`、`routes/site.ts`、`packages/backend/src/publication/sitemap.ts: loadSitemap`、`lib/cache.ts`。API 提供 Cache-Control/ETag/部分 X-Accel-Expires 绝对截止，SSR/浏览器复用不能重置旧内容寿命。pageReuse 只在当前 document 维护最多16页 URL+query 的 Map，expiresAt 来自服务端，刷新不持久化；浏览器上限300秒是上限，不能把所有响应强行缓存300秒。站点地图进程/磁盘/HTTP 共用截止，MCP no-store。代理需识别上游已消耗时间、禁叠加延长缓存；撤回在到期重新验证时生效。

搜索源码：`D:/AIHOT/packages/backend/src/publication/pool.ts: withSearchCapacity,SearchBusyError,loadPool`，4并行+8排队，排队最多3秒，溢出503+Retry-After=5；`siteHandler` 和 `lib/api.server.ts: loadOr404` 映射 busy 页面。繁忙不是无结果。Pulse 现有 SQLite FTS5 三字索引和短词 LIKE 回退可保留，Postgres 仍有差距；适配独立限流/容量保护、错误码和真实重试。

本地状态源码：`D:/AIHOT/apps/web/app/lib/local-state.ts: KEYS,getStarred,toggleStar,markRead,exportBundle,importBundle,rememberPage,useSyncExternalStore`；`restore.ts: saveSnapshot,readSnapshot,restoreAnchor,MAX_AGE_MS`；`session-cache.ts: sessionCache`。收藏上限500、已读5000、最近搜索10；主题、反馈草稿和更新已读也是浏览器状态。存储读取/写入失败可降级；同标签页自发通知、跨标签页 storage 事件同步；编辑前重新读取，坏收藏不被导入覆盖；version1 导入合并、不覆盖已有收藏，部分已读失败有返回状态。无普通账号、无跨设备自动同步。

列表 sessionStorage 快照30分钟，按历史条目 key 保存数据、滚动位置/锚点；内存缓存最多20条并合并延后写，页面离开刷出。`restore.ts: isReload()` 读取 navigation timing 的 reload 类型；`features/feed/Timeline.tsx` 初次 hydration 只在 `!isReload()` 时恢复保存列表和锚点：读者主动刷新取最新列表，后退/前进（包括重新加载 document 的 back/forward）恢复历史条目，不能写成“任何重新打开页面都恢复30分钟旧列表”。它是后退恢复，不是允许公开数据30分钟不核验；应与服务端公开数据截止分别处理。Pulse 可采用本地收藏、已读、历史、主题、导入导出与首次封面完成标记，使用 Pulse 命名空间并保留既有记录迁移；存储封禁不能阻断阅读。会话历史恢复、页面数据缓存、永久浏览器偏好是三个生命周期，不混成一套 TTL。

## 10. 管理员、人工权威和恢复成本

管理员源码：`D:/AIHOT/packages/backend/src/admin/auth.ts: passwordLogin,completeLogin,sessionPrincipal,endSession,cookie,safeReturn`；`apps/api/src/routes/admin-auth.ts: adminHandler,registerAdminAuth`；`routes/admin.ts`；`apps/web/app/routes/admin/layout.tsx`。管理员密码至少12位，或配置飞书登录及 union_id/email 白名单；随机 opaque token 服务端只存哈希，session30天，独立CSRF，HttpOnly/SameSite=Lax、HTTPS Secure；写操作校验 x-csrf-token，所有后台 no-store。配置/密码变更可使既有会话失效；生产拒绝 DEV_AUTH_ROLE 旁路；登录有尝试频率限制。公众请求不根据管理员身份增加可见数据。

后台并非仅服务器本地使用：Docker 文档明确在网站 `/admin` 登录。实际实现支持来源管理、抓取、内容诊断、覆盖、撤回、SEO、归组拆合、模型选用、评测、运行/未知回执、设置、反馈、审计。业务模块维护状态，后台不能直接绕过领域规则写表；人工覆写和模型原输出分开保存，重跑不可抹掉人工权威。

队列/回执源码：`D:/AIHOT/packages/backend/src/jobs/queue.ts: JobData,QUEUES,enqueue,stopBoss`、`jobs/{content,events,sources}.ts`；`providers/receipts.ts: logicalKeyFor,BudgetExceededError,ReceiptUnknownError`；`operations/recover.ts: recoverStaleWork,autoReleaseUnknownReceipts,releaseReceipt`；`apps/worker/src/{main,schedules}.ts`；`lib/shutdown.ts`。付费请求按任务、输入revision、provider/model/prompt/config 身份生成逻辑key，先持久化请求和 attempt，原始响应先存再用于业务。预算按 attempt 计分钟/小时/日，收到的结果可复用；“结果未知”不得由普通调用方随意重试。超过30分钟自动放行一次（未核对账单），再次 unknown 等管理员注明是否计费再放行；重新入队继续未完成提取/分析。不是绝对恰好一次计费承诺。

pg-boss 队列分别设策略/重试/过期，采集与通知不无条件重试；STOP_TIMEOUT_MS=195000，优雅关机等待进行中付费操作、部署服务停止期限要更长。collect/model/推送/IndexNow 安全阀仅 true 启用；`scripts/init-env.ts` 可能主动开采集/模型，研究不能运行它。

Pulse `ingestion/lease.py` 已有采集租约、心跳、幂等键；`operations.py` 有中断恢复，但重分析/补译未全面覆盖锁，未提交模型结果可能重复费用。AdminAccount 表不代表登录/session/CSRF/受保护路由完成，本机人工脚本不替代后台。可移植分步队列状态、回执先存、预算及 unknown 人工处置；SQLite 锁/任务调度实现需组员设计，不能直接引入 pg-boss 宣称已完成。

### 通知是独立投递子系统

源码：`D:/AIHOT/packages/backend/src/notify/selected.ts: pushSelected`、`selected-content.ts: selectedContent`、`deliver.ts: deliverContent,resendDelivery,markStaleDeliveries,resolveDelivery`、`feishu.ts: postWebhook,sendAlert,forwardFeedbackToFeishu`。内容群精选卡片、内部运营告警/反馈、管理员OAuth使用不同通道和配置；告警不发到内容群。Pulse 基线未实现这些目标、投递记录和人工处理链路，不因未来有普通阅读通知按钮就视为已有服务。

`selectedContent` 每次从当前 publications/override 读取：要求 public selected、未silent、有可信发表时间、T1/T1_5、非backfill且timeline在12小时内。`pushSelected` 先使用10分钟同标题租约抑制并发，再以 Fact（无Fact则Article）作为 dedupe 身份。`deliverContent` 按目标分别 claim `(target_key,dedupe_key)`；当前同Fact兄弟报道（以及因纠错换Fact的本文章）已处于 pending/sending/sent/unknown 都阻止再投同目标，不能只检查 dedupeKey 字符串。目标的 enabled_at 排除启用之前的发现内容，启用镜像群不回灌历史。

每发一个目标前重新调用 `selectedContent`，因此主群等待期间发生的撤回、静默、纠错会阻止镜像或更新其卡片；这是通知自身的当前公开/推送资格读取，不代表它直接调用所有列表 scope 谓词。目标 claim 事务短锁、网络发送不持锁；安全阀关闭写 skipped，不外发。`postWebhook` 需 HTTP成功且JSON code/StatusCode=0才确认sent，成功HTTP但无可确认回执可为unknown。

**通知 unknown 不采用模型回执的30分钟一次自动放行**。网络超时/发送中崩溃可能已到达群，绝不自动重发；15分钟过期 sending→unknown，尚未外发的 pending→failed，均交管理员。`resolveDelivery` 要人工确认sent/drop/resend及理由；resend核对当前资格、目标启用时间与安全阀，并用updated_at版本claim防并发重复处置。可移植目标级幂等、同新闻抑制、当前资格重读及人工处置；公安通知目标/权限、静默标准、群平台和时效后续配置，不能复用普通用户账户来假设已实现订阅。

## 11. 媒体、分享与机器出口

媒体源码：`D:/AIHOT/packages/backend/src/media/{imgproxy,upstream,renditions,images,prepare,poster,og}.ts`；`imgproxy.ts: proxiedImage,signature,verifyProxyRequest`；`prepare.ts: prepareArticleMedia,warmShareImage`；`apps/api/src/routes/{media,og}.ts: registerMedia,registerOg`。后端签名 URL 包含来源、mode、exp，代理验证签名/时效并在上游读取层约束请求，不能由浏览器暴露任意抓图代理；分享图从当前公开读取层获得文本及许可。前端 MediaGallery/Lightbox/PosterSheet/ReaderTools 提供媒体阅读、海报和复制。Pulse 已有媒体元数据但近期图片验收暂缓；可移植文字复制/链接分享，图片代理/二进制缓存/海报字体及撤回策略后续单独做，品牌仍用 Pulse。

公开出口源码：`D:/AIHOT/apps/api/src/routes/{v1,feeds,mcp,agent,static,og}.ts`；`packages/backend/src/publication/{v1,feeds,agent,llms,sitemap,detail}.ts`；`apps/web/app/lib/seo.ts`；`site/public/{openapi-v1.json,robots.txt}`。API `/api/v1/` 与站内 `/api/site/` 不同定位；RSS精选/全文/全部/日周月及分类版；`/api/v1/agent` 为 Agent Markdown，`/items/:id/markdown` 为文章导出；`/api/mcp` 工具读取最新、搜索、热点、事件和报告；llms.txt/sitemap/SEO/OG 都守同一 publication 范围。MCP Host/Origin 校验，响应 no-store，subscriptions/listen 明确不支持而非无限长连接。公开机器接口并不触发模型。

Pulse 现有 API v1 是本站自己的既有契约，不能因名字相同就声称兼容 AIHOT v1；需要正式版本/字段映射、分页错误、撤回与全文许可契约。先完成统一发布层，再增 RSS/MCP/SEO 导出，避免每个出口单独拼一套可见性。

## 12. 配置、部署和后续核验

配置层：`D:/AIHOT/site/site.ts` 为身份/文案/出刊时间/条款/部署说明，`site/models.ts` 为步骤模型；`industry/{taxonomy.ts,topics.json,sources.json,selection.ts,prompts/}` 为领域知识；`site/modules/{index,server,web}.ts` 和 `packages/contracts/src/modules.ts`/`packages/backend/src/modules.ts`/`apps/web/app/modules.ts` 为模块注册，不能在框架写死线上私有模块。Pulse 应建立等价的品牌、领域、模块配置边界，但不为不存在的模型榜或监控提供假实现。

部署依据：`D:/AIHOT/docs/deploy.md`、`docker-compose.yml`、`Dockerfile`、`deploy/`、`scripts/{migrate,seed,init-env,smoke,mcp-check}.ts`。web/api/worker 分进程，DB/setup另容器；SITE_URL 固定生成 RSS/SEO/分享绝对链接，不能从任意 Host 派生。更新顺序备份→构建→停止旧服务→迁移/seed→启动；迁移按完整文件名记账，不能改已发布文件；0055后单语句在线约束/CONCURRENTLY 索引是 Postgres 实践，Pulse Alembic/SQLite 必须另设计。安全阀、密钥仅后端、备份/日志清理/代理缓存是部署责任。

本轮核验限于静态源码/路径/文件hash。没有证明外站当前可达、模型能力稳定、数据库迁移可执行、unknown计费上限真实成立、HTTPS/CSRF/代理缓存已部署正确，也没有性能或生产覆盖结论。后续需按阶段以本地假服务验证撤回、修订重分析、重复付费复用、未知结果、停机补刊、热度参与方去重、浏览器存储失败；真实外部联调在明确启用安全阀后单独记录。大样本金标与留出集、来源许可、警务分类及条款最终内容仍需用户/领域人员确认。

实施顺序与可交付后端缺口详见 [AIHOT 后端阶段交接](aihot-backend-stage-map.md)。

### 源码直达索引

以下链接指向本机原始快照；移动到其他电脑时按上述 `D:/AIHOT` 原路径查找。文件中的符号名是定位依据，行号可能随更新变化。

| 研究主题 | 核心证据 |
| --- | --- |
| 架构与领域配置 | [architecture.md](D:/AIHOT/docs/architecture.md)、[customize.md](D:/AIHOT/docs/customize.md)、[site.ts](D:/AIHOT/site/site.ts)、[selection.ts](D:/AIHOT/industry/selection.ts) |
| 页面与HTTP | [routes.ts](D:/AIHOT/apps/web/app/routes.ts)、[registerSite](D:/AIHOT/apps/api/src/routes/site.ts)、[HTTP共享类型](D:/AIHOT/packages/contracts/src/site.ts) |
| 材料与版本 | [upsertMaterial / decideTimeline](D:/AIHOT/packages/backend/src/content/materials.ts)、[采集入口](D:/AIHOT/packages/backend/src/sources/collect.ts) |
| 判断写作 | [runAnalysis / normalizeAnalysis](D:/AIHOT/packages/backend/src/editorial/analyze.ts)、[五轴评分提示词](D:/AIHOT/industry/prompts/selection-score.md) |
| 事件关系 | [groupArticle](D:/AIHOT/packages/backend/src/events/group.ts)、[RELATIONS / schema](D:/AIHOT/packages/backend/src/events/relate.ts)、[召回](D:/AIHOT/packages/backend/src/events/recall.ts) |
| 热点 | [computeHotRanking / heatSeries](D:/AIHOT/packages/backend/src/events/hot.ts) |
| 报告 | [dailyEdition / arrangeDaily](D:/AIHOT/packages/backend/src/reports/edition.ts)、[composeDaily / composeDueReports](D:/AIHOT/packages/backend/src/reports/compose.ts) |
| 发布与同步 | [scope](D:/AIHOT/packages/backend/src/publication/scope.ts)、[publishArticleTx / ledger](D:/AIHOT/packages/backend/src/publication/publish.ts)、[代表选择](D:/AIHOT/packages/backend/src/publication/representative.ts)、[snapshot / changes](D:/AIHOT/packages/backend/src/publication/v1.ts) |
| 浏览器状态 | [local-state](D:/AIHOT/apps/web/app/lib/local-state.ts)、[restore](D:/AIHOT/apps/web/app/lib/restore.ts)、[session-cache](D:/AIHOT/apps/web/app/lib/session-cache.ts)、[page-reuse](D:/AIHOT/apps/web/app/lib/page-reuse.ts) |
| 管理权限 | [sessionPrincipal / passwordLogin](D:/AIHOT/packages/backend/src/admin/auth.ts)、[adminHandler / CSRF](D:/AIHOT/apps/api/src/routes/admin-auth.ts) |
| 成本与恢复 | [receipts](D:/AIHOT/packages/backend/src/providers/receipts.ts)、[unknown恢复](D:/AIHOT/packages/backend/src/operations/recover.ts)、[队列及关闭](D:/AIHOT/packages/backend/src/jobs/queue.ts) |
| 通知投递 | [pushSelected](D:/AIHOT/packages/backend/src/notify/selected.ts)、[当前资格](D:/AIHOT/packages/backend/src/notify/selected-content.ts)、[目标去重及人工恢复](D:/AIHOT/packages/backend/src/notify/deliver.ts)、[Feishu回执](D:/AIHOT/packages/backend/src/notify/feishu.ts) |
| 部署与许可 | [deploy.md](D:/AIHOT/docs/deploy.md)、[LICENSE](D:/AIHOT/LICENSE)、[NOTICE](D:/AIHOT/NOTICE)、[Pulse保留声明](../THIRD_PARTY_NOTICES.md) |
