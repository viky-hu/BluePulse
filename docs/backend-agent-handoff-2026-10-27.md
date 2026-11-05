# Blue Pulse 后端 coding agent 交接（2026-10-27）

> 给下一位负责后端的 coding agent。基线是本仓库 `main` 的 `8000c3a`；开始工作时先核对分支、HEAD、未提交改动和用户最新指令，不把本文当作永久不变的需求。本文件是交接，不是“所有功能已完成”的声明。

## 1. 项目究竟要做什么

Blue Pulse 是面向国内外警务科技的公开资讯系统。目标不是广义警务新闻门户，而是把公开来源中的**技术在警务上的应用、相关政策与值得跟踪的上游技术进展**，经过可追溯处理后供中文读者阅读。大模型、智能体、无人机是重点方向，既有七个主题分类继续保留；“相关”与“值得精选”是两次不同的判断。

一条内容应当沿同一条后端主链路前进：

`受控来源 → 发现/抓取 → 正文或摘要与原始时间 → URL 去重 → 相关性/分类/中文整理 → 存储和公开资格 → 各页面按各自规则读取`。

页面**只读预处理好的结果**，不在读者打开页面时爬站或调用付费模型。各页面共用文章身份、来源、原文链接、时间、状态和公开规则，但不能共用一份“换标题的新闻列表”：精选是判断后的选稿，全部动态是合格公开文章池，热点需要事件及独立参与方证据，日报需要真实刊期编排。首页六席 `FeaturedEdition` 不是日报。[AIHOT 机制研究](aihot-understanding.md)提供参考，实际移植依赖见[后端阶段图](aihot-backend-stage-map.md)；两篇是静态研究/计划，不能代替代码或运行验收。

## 2. 不可丢的用户要求与边界

- 技术筛选重点是“各类科技在警务上的运用和政策”。常规枪支弹药、防弹衣、普通运维招标等不能只因“警用/科技”就入精选；采购公告证明采购意向，不证明已部署或有效果。没有“公安”字样但有具体警务应用路径的重要上游能力可作为候选；泛泛的 AI 论文不自动收录。模型不得补写原文没有的金额、效果、机构关系。
- 保留固定七主题和现有 URL/slug：`policing`、`public-safety-tech`、`artificial-intelligence`、`cybersecurity`、`research`、`policy-standards`、`procurement-projects`。相关、精选候选、人工决定、正文可用性、翻译状态、是否公开必须分别表达。
- 首版以**文字可查、可读、可追溯**为优先；用户决定暂缓图片显示，不要为实现页面自行扩大到图片代理、缩略图或海报。已有媒体字段不等于图片系统验收。
- 公众匿名阅读；收藏、历史、首次入场记忆在当前浏览器，不需要普通用户账户或云同步。未来同站 `/admin` 必须有服务端管理员会话、CSRF、审计。`AdminAccount` 表和本机脚本不是已完成的后台。
- 本次明确选择的菜单是：内容＝精选、全部动态、热点榜、AI日报、主题；更多＝Agent 接入、关于、更新日志、反馈；顶部另有搜索。**不要添加模型榜或 Tibo/Codex 重置监控**。菜单入口与建设中页面不等于后端服务已存在。以[README 最新菜单清单](../README.md)与 `src/app/_components/home/navigation-config.ts` 为准。
- 保留 Python/FastAPI/SQLAlchemy/SQLite 后端、Next.js/GSAP 前端和 Pulse 品牌。参考 AIHOT 的业务机制与契约，不直接搬 React Router loader、PostgreSQL SQL 或 pg-boss。第三方代码遵循[许可说明](../THIRD_PARTY_NOTICES.md)；新闻全文的展示/再分发许可需单独判断。
- 来源只访问配置允许的公开目标，遵守 robots、条款、限速和响应上限；不绕过登录、验证码、WAF、付费墙。密钥仅在服务端 `.env` 或环境变量；不得提交 `.env`、`backend/data/`、真实标注文件及私有日志。

## 3. 当前代码与真实完成度

| 区域 | 现有实现 | 不要误认成已完成的能力 |
| --- | --- | --- |
| 采集 | `backend/config/sources.json` 有 11 个来源，适配器在 `backend/bluepulse_backend/ingestion/`；`pipeline.py` 统一入库，`operations.py` 提供状态、失败补跑和中断恢复。来源包括 API、RSS、受控 HTML。 | 配置数量不等于稳定可达；GDELT 限流、Police1 访问挑战、NIST TLS 问题曾出现。HTX 未接入。缺材料修订、完整 provenance、采集游标/历史回灌政策。 |
| 判断与人工覆盖 | `processing.py`、`llm.py`、`model_adapter.py` 处理相关性、中文标题/摘要、七主题、重要性与精选候选；短篇英文正文翻译；`editorial.py` 使人工决定优先。 | 尚无完整的独立预筛/双评分/结构化事实、提示词与输入版本、付费回执/预算/unknown 核账。20 条人工标注只是起点，不是门槛验收。 |
| 数据 | `models.py` 包含 Article、Source、Topic、Entity、ArticleMedia、FeaturedEdition、IngestionRun/Lease 等；Alembic 当前到 `0007_article_search_status`。canonical URL 幂等、内容指纹、SQLite FTS5 已存在。 | 无 Fact/Story、正式日报刊期、统一 publication/withdrawal/许可 ledger；PostgreSQL 全文索引及实机并发未验证。 |
| 公开 API | `api.py` 已有 `/api/v1/home/featured`、`/home/recently-collected`、`/articles`、`/articles/{id}`、`/articles/availability`、`/taxonomy`、`/sources`、`/entities`、健康检查。列表支持时间、主题、地区、来源、实体、关键词、排序和 cursor。正文/翻译状态分开返回；收藏可用性遵守现有公开条件。 | 无热点/事件、日报、Agent/MCP/RSS、反馈写入和管理接口。现有 `public_article_conditions()` 是本项目当前公开规则，不等于 AIHOT 更细的分层发布策略。 |
| 运行 | `worker.py` 有手动/每日 06:00 采集、只读状态、失败补跑与中断恢复；`lease.py` 管采集租约/幂等。 | 重分析/补译未全受同一租约保护；崩溃前未提交的模型调用仍可能重付费；没有完整管理运行页。 |

截至本次交接，本机 `backend` 下执行 `unittest discover` **86 项通过**。这是离线/受控测试的证据，不证明外站今天可达、模型服务稳定或真实前后端已全面验收。旧[2026-10-06 进度](development-progress-2026-10-06.md)记录的是当时快照，不能把其测试数和页面清单当成今天状态。

## 4. 逐页后端需求：同一内容底座，不同读取产品

| 页面/入口 | 现有数据入口 | 后端下一步需提供什么 |
| --- | --- | --- |
| `/` 精选 | `home/featured` 六席、`articles` 近期流、`home/recently-collected` 空态回退 | 先冻结“事实摘要 vs 关注理由”、候选/人工覆盖/发布时间/公开资格契约。前端当前读取精选时只映射 `item.article`，API 的外层 `featured_reason` 未进入卡片；这是需要与前端负责人对齐的接线问题，不要在后端重复编造字段掩盖。 |
| `/all` 全部动态及顶部搜索 | `articles` 的组合筛选、SQLite FTS、cursor；旧 `/articles` 仍可访问 | 明确公开池、历史文章与未知日期策略，保证筛选+分页稳定；搜索繁忙/故障要区别于零结果。不要另建一套采集或摘要。 |
| `/topics` 与 `/topics/:slug` | `taxonomy` 与 `articles?topic=...` | 当前是七主题目录及分类过滤。以后若做主题导语、代表事件、近期变化，应定义独立主题聚合契约，不能把实体名称列表或模型自由生成的描述伪装成已审核主题总结。 |
| `/articles/:id` | 文章详情、原文/译文、状态、来源与原站链接 | 补内容修订、证据定位、撤回/许可与日后同事件报道。不能凭空补缺正文；已撤回内容不可从收藏或其他出口绕行。 |
| `/hot` 热点榜 | **当前只有建设中页面，无热点 API** | 需先有 Fact/Story、独立来源参与方、去转载/矩阵重复、可信时间、来源覆盖/趋势状态。`importance_score` 或点击数不能冒充事件热度。 |
| `/daily` AI 日报 | **当前只有建设中页面，无刊期 API** | 需先有事件关系和发布规则，再建 Report/ReportEntry、时间窗口、去重、刊期幂等、引用及订正。不得把六席精选或当前文章列表直接命名为日报。 |
| `/agent` Agent 接入 | **当前只有建设中说明，无 MCP/RSS 接口** | 先完成统一公开范围、许可、撤回、机器端代表条目与版本契约，再加机器出口；页面打开不应触发模型。 |
| `/feedback` | **当前无写入服务** | 若后续实现，需反滥用、最小化个人信息、存储/删除政策及管理员处理路径；关于/更新日志目前是前端静态内容，不要求采集服务。 |
| 浏览历史、本机收藏、实体目录 | 浏览器本地状态、`articles/availability`、`entities` | 收藏/历史不需要账号；availability 只返回当前公开状态。实体当前是文章中的明确名称命中，不代表合作关系。 |

## 5. 推荐接手顺序：一次只交付一个可验收纵切片

1. **先核对现有阅读底座和首页契约。** 从 `editorial.py`、`api.py`、`pipeline.py`、前端 `HomeDashboard.tsx` 与最近的菜单验收读起；列出首页精选/近期流的字段、来源、排序和空态，修复应归属后端的契约缺口，前端接线问题交给前端负责人。先做离线 API 与真实数据库只读检查，不调用模型。
2. **再做材料修订、时间和统一公开政策。** 区分发表、发现、抓取、公开时间；旧文不刷屏；内容变化产生可追溯 revision；人工覆盖不丢；撤回与许可随各出口核验。不要改写已发布迁移，也不要迁移时猜补未知历史事实。
3. **然后做付费回执/预算/恢复，再扩复杂模型步骤。** 已存结果重试复用，发送后结果未知独立记录；不能承诺绝对不重复计费。重分析与补译纳入可靠任务边界，先用假提供方故障注入。
4. **有稳定文章版本和判断结果后做事件/热点。** Article 是单篇材料，Fact 是同一次发生，Story 是持续进展；同厂商不同项目不能误归组。热点依赖独立参与方，不从首页分数推导。
5. **事件和发布契约稳定后做日报，再考虑 Agent 机器出口与反馈。** 管理员鉴权、CSRF 与审计要随着每一项管理写操作逐步建设，不能等所有业务功能完成后才补；未经保护的管理写接口不得向公网开放。具体依赖与验收矩阵见[后端阶段图](aihot-backend-stage-map.md)，不要在一个任务里并行搭多个外观空壳。

每个纵切片应交付：数据库迁移（如需要）、服务端读取/写入契约、状态和错误定义、离线 fixture 测试、失败/恢复测试、对现有公开 API 的兼容性说明、与前端消费方的字段对照，以及“实际完成/仍未完成”的短记录。**页面存在 ≠ 功能完成；静态源码研究 ≠ 运行验收。**

## 6. 接手与安全验证

在本仓库根目录先核对 `git status --short`、当前分支与最新提交，并阅读[项目规则](../AGENTS.md)、[后端 README](../backend/README.md)、[操作说明](使用说明.md)、[AIHOT 研究](aihot-understanding.md)和[后端阶段图](aihot-backend-stage-map.md)。`D:/AIHOT` 在部分环境可能不存在；研究文档只是索引，移植具体功能前需取得并核对对应 AIHOT 原始源码，不能凭文档描述当成可运行实现。

协作规则：截至 `8000c3a`，仓库 `AGENTS.md` 记载“前端工作直接在 `main`，后端工作在队友分支，由用户决定合并”；本次提问者明确表示自己负责后端。接手时应先向当前分支及最新用户指令核对实际工作身份和合并安排，不以旧文档推断用户角色。不擅自改动、合并或删除其他人的分支；不要在后端任务中顺手重做菜单或动画。若需要前端字段/路由改动，列清接口及状态与前端负责人协作。

Windows PowerShell，在 `backend` 目录可先做不会访问外站/付费模型的检查：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m bluepulse_backend.worker source-status
.\.venv\Scripts\python.exe -m bluepulse_backend.worker recover-interrupted
```

首次新环境参考[后端 README](../backend/README.md)安装依赖、备份数据库、运行 `alembic upgrade head` 和 `sync-config`。**`ingest-once`、`retry-failed --apply`、`recover-interrupted --apply`、`reprocess-pending`、`translate-pending` 会写库，部分还会访问外站或调用付费模型**；只有在任务需要且已核对配置、预算和目标后运行。测试用临时库与假模型，不靠真实外站证明基础逻辑。

交接结论：现有文字资讯闭环可本地试用；热点、日报、Agent 接入、完整管理员、统一发布/许可及复杂 AIHOT 机制仍是后端工作。用户希望“慢工出细活，一个页面一个页面搞”，请从一个页面的数据产品和验收标准出发复用共通主链路，避免为每个页面重复采集、重复分析或制造假结果。
