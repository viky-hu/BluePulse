# AIHOT 机制移植：Pulse 后端差距与阶段交接

2026-10-31 热点榜交接：新增 [DOCK-007](../dock.md#dock-007热点榜参与者与24小时曲线)，本站前端按原榜单组件适配，精确预留 `GET /api/v1/site/hot`（浏览器经 `/api/bluepulse/site/hot`）。没有新增FastAPI实现，前端及受控接口验收通过，见 [热点榜验收](pulse-hot-verification-2026-10-31.md)；完整事件页仍未完成。此接口是本站camelCase读取，不是原AIHOT机器出口hot-topics（后者只给排名／计数，不给热度值）。

阶段B/E/H待办包括：Article—Fact—Story／primary-report证据与当前listed资格，可信源时间、当前参与方式及独立主体归一、source clock与覆盖、48h／24h半衰／6h可比趋势、原surge／new／rising门槛和规则版本；发布排名／小时complete快照及补采修复；读取时重核代表、撤回／归组／释放／媒体许可，不按数组重编号。主榜与内嵌条共用排名，保留sourceCount／participantCount／有限名单不同口径、头像排序／srcSet与受控代理、25小时边界槽／null缺测。缓存提供真实截止，前端30秒／16项不延长上游寿命；不能把前端或受控服务验证视为阶段E/H完成。后续事件读取与合并308／alias另行交付，不能用当前待接入路由替代。

2026-10-31 精选验收补充：前端及受控 HTTP 检查已通过，详见 [专项验收](pulse-featured-verification-2026-10-31.md)。DOCK-006 中时间线、归组、热点及统一发布权限的后端任务仍待实施与真实联调，不随前端验收改变阶段结论。

2026-10-30 精选前端交接：本轮已适配 AIHOT 精选时间线、同新闻阅读组、内嵌热点与共享阅读组件，新增两个精确同源代理；没有修改 FastAPI，也未完成真实业务联调。队友按 [DOCK-006](../dock.md#dock-006精选时间线同新闻阅读组与内嵌热点) 实施 `GET /api/v1/site/timeline` 和 `GET /api/v1/site/groups/:factId/reports`。地区沿用 domestic/foreign，topic 沿用七类稳定slug；timeline外层camelCase，item沿用Pulse UUID／ArticleCard，明确selected及可选sameEvent/channel/x。旧六槽仅用于封面，recently-collected不能补成精选。

依赖阶段B/D/E/H：统一公开／释放／撤回／许可、候选加归组完成门禁、Fact／Story与证据角色、同筛选代表／计数、稳定首次anchor及绑定筛选的游标、完整筛选后分组dayCounts。阅读组包含符合当前政策的selected及nonselected primary/report，排除mention，最多100篇、no-store；不同来源数排除代表来源，报道数去重。内嵌hot只随未筛选第一页返回，少于三条可见事件返回null，暂不要求完整热点榜接口；热度须独立参与方归一、48h窗口／24h半衰／6h覆盖比较，unknown不伪造箭头，头像由安全代理提供或缺省。人工覆盖必须保留，旧Article迁移不能用first_seen_at替代事实锚点。缓存须给可信截止，前端16项／60秒上限取taxonomy及所有批次最早截止；30分钟位置／打开标记不延长内容寿命，阅读组不复用报道快照。`/story/:publicId` 当前仅为待接入目标。最终前端测试另记，不能据此宣布阶段E/H或后端完成。

2026-10-29 收藏页补充：本轮仅前端复用 `/starred`、浏览器备份和独立已读标记，没有修改 FastAPI。现有 `/api/v1/articles/availability` 的每批100 UUID、`items:[{id,available}]` 与 `no-store` 可直接沿用；原版仅摘要状态、当前公开来源名仍需组员在同一匿名读取政策下扩展 `status/source_name`（详见根目录 DOCK-005）。正文采集状态不能代替全文许可，收藏快照不授予撤回内容读取权；统一发布政策仍属于后续阶段B。

2026-10-29 前端复用修订：严格保持 AIHOT 分类／卡片／日期结构，页内查询不套整页转场，不增独立说明行、骨架或统计行。日期无年份／今天；Mock 同标题标识、相关度禁用原因用 title。修订稿受控检查通过，见 [专项验收](pulse-all-verification-2026-10-29.md)；DOCK-004 后端待办及真实联调仍未完成。

2026-10-29 模块交接补充：[dock.md DOCK-004](../dock.md#dock-004全部动态分类筛选与全文检索) 记录 `/all` 复用现有 articles／taxonomy 的边界。后端需补新七类稳定 slug 注册、历史归类、分类提示词版本及人工覆盖，另行实现真实 total／pageCount／北京时间 todayCount、数字分页、全文相关排序、繁忙保护与统一发布／许可缓存。当前40条游标、全文最新和 taxonomy 通用查询不等于这些能力已完成；本轮不修改后端，前端验收与真实联调另记。

2026-10-28 模块交接补充：`dock.md` 的 DOCK-002 已安排 Next.js 从仓库 JSON 提供更新日志／版本元信息，无需重复 FastAPI 日志服务。DOCK-003 列出反馈接收、数据库迁移、私有截图、可信来源 HMAC、限流、状态／版本／审计、删除及本机 `feedback list/show` 查看命令；这些都是后端待办，前端完整表单不代表已可真实收集。用户明确不接飞书。网页反馈管理依赖本文件阶段 G 的服务端管理员权限链，不能提前开放匿名列表或图片。联调配置、限制差异及验收要求以 DOCK-003 为准。

记录日期：2026-10-11。这是依赖与交接稿，不是完成报告。静态研究见 [AIHOT 理解文档](aihot-understanding.md)。当前保留 Python/FastAPI/SQLAlchemy/SQLite 后端；AIHOT 的 Node/Fastify/PostgreSQL/pg-boss 是参考实现。前端 Next.js/GSAP 不换栈。用户策略：先前端框架，成熟机制以 AIHOT 为主，后续警务校准。完整管理后台尚未实现。

## 1. 当前可复用资产与真实缺口

基线为 [2026-10-06 进度](development-progress-2026-10-06.md)、[Stage1 原计划](stage1-backend-plan.md)及 `D:/pulse/backend/bluepulse_backend/` 当前实现。旧计划中的能力不能按文字直接认定完成。

| 能力 | Pulse 代码资产 | 差距 |
| --- | --- | --- |
| 采集/来源 | `ingestion/{adapters,pipeline,operations}.py`，各来源适配器、`config/sources.json` | 已有受控 RSS/API/HTML、URL 去重、来源结果；缺统一 material revisions/discovery/provenance、多种参与方式与时间回灌规则 |
| 模型/精选 | `ingestion/{model_adapter,llm,processing}.py`、`editorial.py` | 已有相关、候选、理由、标题摘要、短篇翻译及人工优先；缺预筛/双评分/结构化事实/分步回执/版本/入选归组门禁 |
| 存储/API | `models.py`、`api.py`、Alembic 至 `0007` 既有迁移 | 已有 Source/Topic/Article/Entity/ArticleMedia/IngestionRun/租约/FeaturedEdition；没有 Fact/Story、刊期、发布ledger。SQLite FTS5可用，Postgres 全文索引另验收 |
| 运行恢复 | `ingestion/lease.py`、`operations.py`、`worker.py` | 有采集锁/心跳/幂等/中断重跑；未提交模型结果可能重复计费，锁不全面覆盖重分析/翻译 |
| 管理 | `AdminAccount`、受控本机脚本、人工覆盖字段 | 没有完整同站管理员登录/session/CSRF/审计/运行后台。数据表存在不等于权限链完成 |
| 公众阅读 | `/api/v1/articles`、详情、taxonomy、sources、entities、home/featured、recently-collected | 支持真实文字阅读/检索；事件热点、日报与专题关系、MCP/RSS/许可层缺失。媒体已有元数据不等于图片系统验收 |

本轮基础前端路由、匿名浏览器记忆及 availability API 扩展已完成，2026-10-25 的 lint/build、离线 API 与浏览器检查见 [验收记录](aihot-foundations-verification-2026-10-25.md)。这不代表上述事件、报告和后台已经完成。

## 2. 前端先行的数据约定

公众匿名使用精选、全部动态、搜索、收藏/已读/历史与后续报告，不建设普通注册/账号/云同步。收藏存当前浏览器，清除或换设备不会同步，可导入导出；收藏缓存不赋予已撤回内容可读权。首次封面完成记忆属于前端偏好，直接打开子页应进入稳定态。

保留原 API v1 契约和 Python 适配器。前端仅经同源 HTTP 代理读后端，不放数据库/模型/管理员密钥，不在页面加载时触发付费模型。新增模块返回明确“尚未接入”“没有内容”“服务繁忙”“服务不可用”，不能以 mock 排名/日报充当真实后端。

后续同站 `/admin` 仅管理员；后台入口可隐藏但不能以“隐藏URL”代替服务端鉴权。公开响应对登录管理员和匿名公众相同；管理读取独立接口、no-store、写操作有 session+CSRF+审计。阶段安全要求参考研究 §10，不把 AIHOT 的管理员密码实现机械替代 Pulse 原 Argon2id 账号设计。

## 3. 建议依赖顺序

### 阶段 A：冻结公共契约及浏览器基础

范围：保留真实文章列表/详情与分类/来源/实体筛选，前端薄适配；将收藏可用性核验作为匿名读接口，移除普通账号文案。本轮基础部分已验收，覆盖与边界见上述记录。

AIHOT 来源：`D:/AIHOT/apps/api/src/routes/site.ts: registerSite`、`publication/availability.ts: itemAvailability`；浏览器 `apps/web/app/lib/local-state.ts`、`restore.ts`、`page-reuse.ts`。Pulse 使用既有 API 错误格式、UUID、游标与状态字段，不能复用 AIHOT 短ID/数字页假装契约兼容。

交付/验收：新增接口明确定义过滤/数量上限/非法ID/撤回/部分未知；匿名不获取隐藏数据。读权限与 `editorial.public_article_conditions()` 共用。前端真实空态、浏览器存储失败、坏数据、跨标签同步与深链接/后退不丢筛选。参考 AIHOT `restore.ts:isReload` 及 `features/feed/Timeline.tsx`：主动刷新应取最新列表，后退/前进恢复有效会话快照和锚点，不能将30分钟恢复TTL误用于主动刷新。完成条件由实际检查输出确认。

### 阶段 B：材料版本、时间与统一发布政策

依赖 A。先统一各入口，再增加事件和机器出口。

AIHOT 原路径：`D:/AIHOT/packages/backend/src/content/materials.ts: upsertMaterial,contentHash,decideTimeline,fillPublicationTime`、`content/provenance.ts`、`publication/{rules,scope,publish}.ts`。可移植 material 身份、原始/发现/更新/公开时间分离、revision 与分析输入绑定、历史/未知日期规则、站内全文/再分发许可、暂停与撤回分离。SQLite 不支持原 SQL 中的 advisory lock/JSONB，需 SQLAlchemy 事务和唯一约束实现；若选 Postgres 另提供迁移与并发证据，不默认换库。

建议领域数据：MaterialRevision/Discovery、Source 的 tier/participation_mode/publisher身份与许可、AnalysisRun 的 input_revision/prompt_version、Publication 的 visibility/eligible/candidate/selected/release时间/正文模式。命名由组员结合现有模型制定，本文不是预先要求照单建表。

发布政策按出口分别命名，不能抽成一个适用于所有用途的“public过滤”。AIHOT `scope.ts:listedCondition` 要public+eligible+released；`rules.ts:hasItemPage` 仅非withdrawn editorial，未收录/非public材料也可能有受限详情；实际 `detail.ts:markdownAvailable` 则另要求public及可导出摘要/原帖/许可正文，可不listed但不能仅凭详情存在就允许导出。Pulse是否采用这种分层详情政策需明确契约，现有集中条件先保留；验收覆盖“有详情但不在列表”“有详情但不可导出”“撤回各出口均拒绝”。

迁移旧 Article 保留UUID/原URL/人工覆盖，无法证明的历史日期/许可不推断补齐；明确旧精选兼容策略。验收重点：重复发现不增版本、真实变更增版本、模型旧结果不覆盖新版本、未知日期不伪装今天、撤回在所有已有公开接口隐藏、恢复/变更有审计。

### 阶段 C：付费回执、预算与分步任务恢复

依赖 B 的输入版本；应在大规模双评分/归组前完成。

AIHOT 原路径：`D:/AIHOT/packages/backend/src/providers/receipts.ts: logicalKeyFor,BudgetExceededError,ReceiptUnknownError`、`operations/recover.ts: autoReleaseUnknownReceipts,releaseReceipt,recoverStaleWork`、`jobs/queue.ts: JobData,enqueue,stopBoss`。借鉴逻辑任务key、attempt预算、先存响应再业务写、成功复用、结果unknown分类、一次自动30分钟放行及再次人工核账、优雅关闭。不能宣称“永不重复计费”；timeout-after-send 无法证明提供方未收费。

Pulse 保留 ModelAdapter，设计 Python 持久任务/租约方案，不引入 Node pg-boss。记录 provider/model/prompt/input_revision/config、原始响应/usage/成本来源、失败类别；敏感数据需脱敏。锁覆盖重分析/翻译与采集，明确停止等待。安全阀默认关闭，测试仅假服务。

验收：响应已存而业务未提交的重启复用；付费请求发送后失联进入unknown；预算按attempt熔断；模型/付费请求回执unknown仅允许一次30分钟自动放行，再unknown必须管理员核账；停机不漏任务/不无限自动重试。通知投递unknown不沿用此自动放行策略，见阶段I。以可控制假提供方注入故障，不用真实计费请求证明幂等。

### 阶段 D：预筛、双评分和结构化事实

依赖 B/C。AIHOT 原路径：`D:/AIHOT/packages/backend/src/editorial/analyze.ts: runAnalysis,runSelectionScores,runStructure,normalizeAnalysis`、`industry/prompts/{prefilter,selection-score,structure,content-understanding,safety}.md`、`industry/selection.ts`。

保留五维类型加权、双独立评分、噪声压制、材料安全与答案先行写作结构，替换警务实例、主题/机构字典。结构化与评分可并行，写作依赖结构化；相关/够分/确认入选是三个状态，不删除人工覆盖、不靠分数补足六席。提示词hash与输入版本保存，切换新提示不悄悄重算历史。

校准参考 Pulse selection-annotation-guide、selection-calibration 和 AIHOT `docs/selection.md`、`scripts/eval-selection.ts`。提交 development/holdout 样本、边界分层、precision/recall/coverage/失败率及门槛依据；不能直接认定 AI T1=60/T1_5=65/T2=76 适合警务。初步流程可先接提示词，但上线门槛另签明实际校准状态。

验收：PASS/UNKNOWN继续、BLOCK停止、两次必须完整、平均floor、scope不足不确认事件；空材料不虚构正文、采购/试点/验收分清事实、模型重跑保留人工决定。

### 阶段 E：Article—Fact—Story、确认门禁与热点

依赖 B/C/D。AIHOT 原路径：`D:/AIHOT/packages/backend/src/events/{group,recall,relate,corrections,hot,digest}.ts`；`groupArticle`、`RELATIONS`、`computeHotRanking`；`publication/{stories,story-evidence,representative}.ts`。

先实现 Fact/Story 和 primary/report/mention，四种关系及输入修订重归组，再加召回/综述。没有向量服务可用词重合召回，不为形态先部署向量库。精确参考 `publication/publish.ts`：`selectionCandidate && grouping_status === "complete" && (f.selected === true || selection_adds_value !== false)`；value=null不是false，可能通过，人工selected=true可覆盖value=false，但仍需候选及归组完成。scope不足主要由 `events/group.ts` 的unsupported分支（明确unknown且无fact）写addsValue=false，不能误写为selected表达式直接检查scope或必须value=true。等待归组只允许符合条件的全部动态，不因超时入选；人工拆合有审计，合并事件稳定ID重定向。

热点需独立参与方/矩阵归一、可信源时间、48小时/24小时半衰、source clock 与可比趋势，editorial/hot_signal 分离；政策原数字是否调整以后有领域证据再校准，不在前端自行赋权。未经来源时钟验证的趋势返回unknown，不生成假曲线。

验收：同新闻多源合Fact、同事件新发展连Story、同公司不同事分开、综合稿仅提及；新信息/同新闻/换皮去重边界；门禁覆盖complete+value=true/false/null、人工selected=true覆盖false、人工决定不绕过candidate/complete、明确unsupported与旧缺失scope分支差异；媒体矩阵/重复采集不增热；缺采集覆盖不显示假下降；撤回证据同步重算/读取过滤。

### 阶段 F：规则日报与受限周月刊

依赖 B/E，C用于周月模型。AIHOT 原路径：`D:/AIHOT/packages/backend/src/reports/edition.ts: dailyEdition,arrangeDaily,dailyMemory`、`compose.ts: composeDaily,grounded,composeDueReports`、`correct.ts`、`site/site.ts: EDITION_TIMES`、worker schedules。

独立 Report/刊期/引用模型，不复用 FeaturedEdition 冒充日报。规则挑选去重/来源限额/快讯；默认时间及12正文/10快讯/2每源/7期记忆可先按参考机制实现并记录配置。周/月只从日报选择20/30事件，模型写导读而不增删事实；引用当前许可/撤回重新核验。

验收：截止后确认进下一期、已出刊不自动重写、停机补缺幂等、无重大新闻与无资料判断区分、隐去已撤回引用及依赖导读/封面、模型产生新名字/数字时使用确定性回退。前端交付真实latest-page/index/detail/navigation，空刊期不是错误mock。

### 阶段 G：完整同站管理员与人工权威

应随 B/C/E 的管理写操作逐步实现，不需要等全部业务功能完成，但未鉴权前不暴露写接口。AIHOT 原路径：`D:/AIHOT/packages/backend/src/admin/auth.ts`、`apps/api/src/routes/{admin-auth,admin}.ts`、`admin/{content,runs,sources,models,settings}.ts`、`audit.ts`、Web `routes/admin/`。

Pulse 落实已有账号密码设计、随机可撤销session+CSRF、限速/安全cookie/生产禁止开发旁路。后台职责：来源配置/试抓、运行诊断/补跑、人工覆盖/撤回恢复、归组纠错、预算/模型步骤、unknown核账、反馈、审计；写操作由所属业务模块事务执行，不直接越层UPDATE。

验收：公众匿名401、错误CSRF403、过期/撤销session拒绝、管理请求no-store、重跑幂等、人工判断不被模型抹去、权威变更与公开结果/恢复记录/审计同事务。前端 `/admin` 可到达不等于这些权限和任务链路完成。

### 阶段 H：代表席位、同步ledger、RSS/MCP/SEO/分享

依赖统一发布层B、事件E、报告F；每增加公开出口都验证许可/撤回。AIHOT 原路径：`D:/AIHOT/packages/backend/src/publication/{scope,publish,representative,v1,feeds,agent,llms,sitemap,detail}.ts`；`apps/api/src/routes/{v1,feeds,mcp,agent,media,og}.ts`。

网页多报道阅读组、机器每Fact一个代表席位，selected snapshot+epoch+watermark+changes及remove事件；分页签名/错误/字段版本正式记录。缓存响应、进程、磁盘、SSR与浏览器共用绝对截止，MCP no-store，503搜索忙与空结果区分。媒体后端签名/时效/上游限制；全文站内与再分发独立许可。品牌字体、share路径、站点绝对URL使用 Pulse 配置。

验收：撤回/许可改变/代表迁移在网页、API、RSS、MCP、Markdown、报告、分享、sitemap一致；旧缓存不续命；ledger序列对应提交顺序、重复相同payload不产新变更、过旧/epoch变化有明确恢复；MCP非法Host/Origin拒绝；媒体不能成为任意URL代理。近期图片展示已暂缓，可先交付文字出口而明确媒体未完成。

### 阶段 I：独立通知投递与人工恢复

依赖B的发布状态、E的Fact身份及G的管理员处置；任务持久化可复用C的基础，但通知回执与付费回执拥有不同恢复政策。AIHOT 原路径：`D:/AIHOT/packages/backend/src/notify/selected.ts:pushSelected`、`selected-content.ts:selectedContent`、`deliver.ts:deliverContent,resendDelivery,markStaleDeliveries,resolveDelivery`、`feishu.ts:postWebhook,sendAlert,forwardFeedbackToFeishu`。当前Pulse无完整通知后端，本阶段不是本轮前端基础功能完成项。

契约：通知目标有enabled/enabled_at、目的（内容/内部告警反馈）、凭据引用；投递按target+dedupeKey唯一，状态pending/sending/sent/failed/unknown/skipped及attempt/version，公开内容资格/人工silent从当前publication重读。参考精选推送要求public selected、T1/T1_5、可信发表时间、非backfill且timeline12小时内；Fact为去重身份，无Fact退回Article，同Fact兄弟或自身旧Fact投递pending/sending/sent/unknown阻止同目标重复。短同标题租约抑制并发，目标enabled_at防历史回灌；主群和镜像每次发前重读当前资格与卡片。网络发送不持长事务锁，默认关闭外发安全阀。

unknown绝不自动重发：发送中崩溃/超时可能已送达，15分钟陈旧sending改unknown；从未发送的pending改failed。管理员核实群后确认sent/drop/resend，必须理由；resend重新检查目标和内容资格，版本claim防两人同时处置。HTTP成功不自动等于送达，需可确认平台code；模型unknown30分钟一次放行不适用于通知。

验收：同目标同Fact多兄弟/并发仅一条；纠错更换Fact不能重复投自身；新启用镜像不回灌旧内容；主群等待期间撤回/静默后镜像不发，修正后镜像用当前卡片；unknown恢复不触发网络自动重发，pending中断不冒充已送；人工resend并发、已撤回、目标停用、enabled_at及安全阀均校验；内容不误投内部告警群，告警反馈不进内容群。全部使用本地假webhook，不向真实群发验证消息。

## 4. 配置与上线交接要求

参考 `D:/AIHOT/site/site.ts` / `site/models.ts` / `industry/` / `site/modules/`，Pulse 应将品牌、警务领域规则、扩展模块分开。AIHOT 下载快照不含线上模型榜/监控；菜单“模型”分类不意味着应复制不存在的服务。保留已有实体目录作为真实能力，未来领域模块单独给契约。

每阶段交付：实际修改/新增迁移、运行配置与默认关闭的外部开关、API契约与例子、输入/状态/错误/恢复策略、离线测试结果、升级回退/数据影响、未完成项。SQLite与Postgres分别写验证边界。不能改写已发布历史迁移来消除问题，也不能用清空已有数据代替迁移方案。

部署依据 `D:/AIHOT/docs/deploy.md` 的三业务进程/备份/停止/迁移/seed/启动/缓存期限/优雅关闭，只移植行为；Pulse Python依赖、Alembic与服务管理有自己的实现。公开SITE_URL、TLS、反向代理/限流、保留策略、许可及条款实际部署需另验证。

实质复制保留 MIT 完整声明及 Copyright (c) 2026 数字生命卡兹克，Pulse 名称/Logo保持原品牌。MIT 不授权第三方新闻全文或 AIHOT 商标。研究静态通过不等于生产上线、所有信源可达或模型效果验收。
