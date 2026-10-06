# Blue Pulse 后端（Stage1 主干）

目前已搭起来源采集、文章存储、精选快照和匿名阅读 API 的主链路。有可核对的摘要或正文时，配置的模型可判断相关性，生成中文短标题、摘要、主题、重要性分和独立的精选候选判断。仅有标题/元数据的条目保留为 `pending_model`，不调用模型、不公开展示；没有模型配置时同样保留原始材料等待处理。精选只选模型或已确认人工判断推荐的相关文章。

## Windows 本地启动

在 PowerShell 进入 `backend` 目录后运行：

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
alembic upgrade head
python -m bluepulse_backend.worker sync-config
```

本地默认使用 `backend/data/bluepulse-dev.db` 的 SQLite，不需要先安装数据库服务。准备切换 PostgreSQL 时，在运行迁移、API 和 worker 的每个 PowerShell 窗口设置：

```powershell
$env:BLUEPULSE_DATABASE_URL = "postgresql+psycopg://用户名:密码@localhost:5432/bluepulse"
```

启动 API：

```powershell
python -m uvicorn bluepulse_backend.main:app --host 127.0.0.1 --port 8000
```

另开窗口立即采集一次：

```powershell
python -m bluepulse_backend.worker ingest-once
```

只重试某个来源（不会访问其他来源），或补分析历史待处理文章：

```powershell
python -m bluepulse_backend.worker ingest-once --source gdelt-public-news
python -m bluepulse_backend.worker reprocess-pending --source openalex-policing-tech --limit 10
python -m bluepulse_backend.worker translate-pending --source nij-policing-tech --limit 10
python -m bluepulse_backend.worker backfill-entities
```

本机查看所有已启用来源最近一次运行状态及失败原因，或只补跑最近失败的来源：

```powershell
python -m bluepulse_backend.worker source-status
python -m bluepulse_backend.worker retry-failed
python -m bluepulse_backend.worker retry-failed --apply
python -m bluepulse_backend.worker retry-failed --source gdelt-public-news --apply
python -m bluepulse_backend.worker recover-interrupted
python -m bluepulse_backend.worker recover-interrupted --apply
python -m bluepulse_backend.worker ingest-once --source npcc-policing-tech --idempotency-key manual-npcc-20261006
```

`retry-failed` 默认仅预览，不访问网站；加 `--apply` 才执行。部分成功来源需另加 `--include-partial`，成功、跳过或运行中的来源不会默认补跑。`recover-interrupted` 默认只预览中断或租约已失效的运行；`--apply` 每次重跑一项。采集入口共用数据库租约锁（120 秒期限、20 秒心跳），与 `schedule` 撞车时返回 `busy`，不会并发采集。同一天的定时采集以及按来源补跑带固定幂等键；手动 `ingest-once` 可指定 `--idempotency-key` 防止重复提交。进程崩溃后先等租约到期，再执行恢复；恢复按原来源范围重跑，URL 去重避免重复入库，但未提交的模型调用可能重复计费。先运行 `python -m alembic upgrade head` 应用锁表迁移。外站 WAF 和 GDELT 限流不会因此被绕过。

单次采集输出包括各来源失败原因、模型调用数、不相关与延期处理数量。API/RSS 每个来源单次最多分析配置的 `max_analysis_candidates` 条新候选（默认 8，新增来源为 3–5 条），已入库 URL 不重复调用模型；其余候选可在后续采集处理。GDELT 返回 HTTP 429 后，后续运行会在 15 分钟内跳过该来源（输出 `source_skipped`），避免反复触发限流。对 WAF 交互式挑战会记录失败，不尝试绕过。

新增 `npcc-policing-tech`（NPCC 官方 HTML 列表及限量详情）和 `biometric-update-law-enforcement-rss`（执法生物识别分类 RSS）。NPCC 先按标题/导语筛科技主题，再读取详情；BU 只接受本站文章路径，最多补抓 3 篇详情。可先运行 `python -m scripts.npcc_smoke --limit 2` 与 `python -m scripts.source_quality_smoke --source biometric-update-law-enforcement-rss` 只读检查，再运行 `sync-config` 和单源 `ingest-once`。HTX 的动态列表仍是待办，未加入采集配置。

英文 `full_text` 正文在相关性分析通过后翻译为中文并另存 `zh_body`，原文 `source_body` 始终保留。为控制单篇模型调用与截断风险，当前仅自动翻译不超过 6000 字符的正文；长篇、缺正文或仅有摘要的文章按原文/摘要回退展示，不计作翻译失败。翻译按段落或句子边界分块，只有全部分块成功才保存中文全文；模型失败时文章仍可作为已处理内容展示，并记录 `translation_failures`。`translate-pending` 可按来源补译已入库、符合该限制的英文文章。采集报告的 `model_calls` 只统计相关性分析调用，翻译调用另计。

文章列表和详情现返回独立的 `body_status`（`full_text`、`abstract_only`、`summary_only`、`partial_text`、`metadata_only`）及 `translation_status`（`not_required`、`available`、`pending`、`failed`、`source_unavailable`、`too_long`）。新文章翻译失败会持久化；旧文章无法可靠追溯历史翻译失败，按现有正文和译文保守推导状态。详情页根据状态说明回退，始终保留真实原文链接。图片展示不属于本轮范围。

`/articles?q=...` 在已迁移的 SQLite 库使用 FTS5 三字片段索引检索原文/中文标题、原文/中文正文和中文摘要；不足 3 字的查询回退到模糊匹配。索引由数据库触发器在文章新增、修改、删除时更新，迁移会索引已有文章。筛选、排序和 cursor 分页规则不变。PostgreSQL 目前沿用相同字段的模糊匹配，全文索引与实机验证仍待完成。升级前备份数据库并运行 `python -m alembic upgrade head`。

或者启动每日调度 worker（Asia/Shanghai 06:00）：

```powershell
python -m bluepulse_backend.worker schedule
```

API 文档位于 `http://127.0.0.1:8000/docs`。前端开发源可用 `BLUEPULSE_CORS_ORIGINS` 配置，默认允许 localhost:3000。

## 来源和内容处理

- GDELT DOC 2.0：按配置关键词发现新闻标题与原站链接；API `seendate` 是索引发现时间，**不当作原站发布时间**。只对 `article_hosts` 显式允许的 HTTPS 主机和路径检查 robots 后尝试取正文；无法取到可信正文的条目由当前配置 `store_metadata_only: false` 计入 `metadata_skipped`，不再新增待处理记录，也不在前台冒充新闻。此前已经入库的标题级记录保留但不公开。当前配置的主机只是保守起点，不能覆盖任意 GDELT 返回的网站。
- Police1 Recently Published：读取公开 RSS 的标题、链接、时间和摘要；对本源允许的 HTTPS 同站文章在 robots 允许时限速尝试补正文。访问挑战、拒绝或正文抽取不足时保留 RSS 摘要；RSS 本身被 WAF 拦截时整源记失败，不绕过验证。
- OpenAlex：用标题和摘要范围内的布尔检索，再要求标题或摘要前段有明确警务领域与技术信号，减少泛论文章。保存题名、发布日期、作者和可取得的学术摘要；作者机构所在国不冒充论文讨论地区。缺摘要的结果不公开。
- NIST 官方 RSS：先接入 Public Safety 和 Forensic Science 两个栏目。仅读取近 180 天的同站新闻条目，排除活动页，不抓详情 HTML；RSS 摘要保存为 `summary_only`，由模型判断是否有足够的警务科技关联。NIST 其他栏目暂不启用：Cybersecurity 抽查时为空，Information Technology 与 Standards 范围过宽，需要再调筛选口径。
- GOV.UK Search + Content API：按 Home Office 和近 180 天范围检索警务 AI、人脸识别、无人机，标题/搜索摘要必须同时出现技术与警务信号；仅访问官方内容 API 的固定政府文档路径，最多取 5 篇新内容，已入库 URL 跳过。使用内容接口的首次发布日期，不把搜索索引更新日当作新文章日期。正文不足 600 字符或只是附件导语时标 `summary_only`，有足量正文才标 `full_text`；HTML 网页本身不爬取。新文章若在内容接口获得官方站点或其静态资源域名的图片，会保存图片链接、说明和替代文字；没有图片就不显示占位图。
- 中国政府采购网：受控翻阅中央/地方公开招标 HTML 列表，利用标题及列表中的采购人信息优先选择候选，再读取同站公告详情，提取标题、公告时间与正文；先按警务和技术关键词粗筛，再由模型判断相关性并生成结构化字段。只访问 `www.ccgp.gov.cn` 的配置路径，先读取 `robots.txt`，不跟随重定向，限制页面大小、翻页数、请求间隔和单次候选数。已入库 URL 在访问详情和调用模型前跳过。
- 美国司法部 NIJ 技术文章：受控读取公开 HTML 列表和同站文章全文，提取标题、发布日期、正文，再交给相同的模型处理流程。先检查 `robots.txt`，只访问 `nij.ojp.gov` 的技术文章列表和详情路径，限制页面大小、请求间隔、翻页数与单次详情数；已入库 URL 不再请求详情。此列表偏历史资料，不能替代实时新闻来源。
- 江苏省公安厅“警务动态”：受控读取公开栏目和同站文章全文，优先取标题明确涉及 AI、无人机、数智警务等技术的文章，再由模型判断是否相关及能否进入精选；普通警务新闻不会因为来自公安机关而直接推送。只访问 `gat.jiangsu.gov.cn` 的该栏目及对应详情，先检查 `robots.txt`，不跟随重定向，限制响应大小、请求间隔和单次详情数。部分文章转载自其他媒体，页面来源不等同于独立的一手效果验证。

来源配置位于 `config/sources.json`，主题位于 `config/taxonomy.json`；修改配置后须运行 `python -m bluepulse_backend.worker sync-config` 才会更新运行库。适配器只访问清单里的 HTTPS 主机，不跟随重定向；通用 API/RSS 响应上限为 8 MiB，GOV.UK JSON 和网页正文上限为 2 MiB。文章按 canonical URL 幂等去重；相同内容不同 URL 的文章会保留并标记重复候选。单篇详情解析失败不会丢弃同源其他文章，运行结果记录 `detail_parse_failed` 并标为部分成功。缺正文、无地区或尚未模型处理都会显式记录状态。公开 API 不展示 `metadata_only`，并将 `published_at` 与 `first_seen_at` 分开返回。

厂商/模型实体清单位于 `config/entities.json`，由 `sync-config` 同步到数据库。只有原始标题、中文标题、摘要或原始正文明确出现清单别名时才建立文章关联，同时记录命中字段和别名；这属于保守的名称匹配，不代表模型完成了实体消歧，也不代表实体与来源存在合作关系。新文章入库时自动关联；升级已有数据库后依次运行 `alembic upgrade head`、`sync-config`、`backfill-entities`。回填可重复执行，不会生成重复关联。

模型适配器默认读取仓库目录上一级的 `.env` 中的 `base_url`、`key`、`llm_id`。部署时也可设置 `BLUEPULSE_LLM_API_BASE`、`BLUEPULSE_LLM_API_KEY`、`BLUEPULSE_LLM_MODEL`，或用 `BLUEPULSE_ENV_FILE` 指定配置文件。密钥仅用于服务端请求，不会写入数据库或 API 响应。模型失败时保留原始资料并标记 `model_failed`；API/RSS 的不相关条目会记录为 `irrelevant` 以避免重复调用模型，但不会进入文章列表或精选。RSS/GDELT/GOV.UK 还要求原始材料中有明确技术信号；RSS/GDELT 的历史文章可由回填命令复核，输出 `rejected_existing` 数量。采购网的不相关公告不入库。

本机若选择 `DeepSeek-V4.1-Flash`，分类请求会使用 JSON 响应模式和 3000 token 输出预算，给该模型的推理阶段留出空间；英文译文也使用 3000 token 上限。若模型返回 `finish_reason: length`，不保存可能截断的结果。`Qwen3.8-Flash` 在 2026-10-06 的本机测试中，模型列表与鉴权正常，但极短的流式/非流式推理请求均在响应头阶段超时；同一服务商的 DeepSeek 模型正常。此情况更像该模型通道的问题，不宜仅靠无限增加客户端超时掩盖。

采集分析、采购公告分析和历史正文补译现通过 `ingestion/model_adapter.py` 的 `ModelAdapter` 接口调用。当前唯一的具体实现是 `openai_compatible`，由 `BLUEPULSE_LLM_PROVIDER` 选择（未设置时默认该值）；设置未知提供方会报错，不会静默切换服务。接口允许在离线测试中注入替身。模型分别输出“相关”和“首页精选候选”及推荐理由；精选不会再用相关性或分数自动补足六篇。已确认的人工判断单独保存，公开状态与精选优先服从人工决定，模型重跑不会覆盖它。旧文章迁移时默认不是精选候选，不会凭旧分数自动上榜。更完整的评分分项、模型/提示词版本和带权限的后台纠错仍待 P1 后续实施。

从 `backend` 目录单独测试该来源：

```powershell
python -m scripts.ccgp_smoke
python -m scripts.nij_smoke
python -m scripts.jiangsu_smoke --limit 2
python -m unittest discover -s tests -v
```

三个 HTML smoke 脚本会真实访问各自站点并输出抓取计数或失败类型，不写数据库。`ccgp_smoke` 现在显式禁用模型分析；正式 `ingest-once` 仍会调用已配置的模型。本机若无法连接 `www.ccgp.gov.cn`，采购网脚本会停在获取 `robots.txt` 的步骤，不会绕过站点限制。先运行 `alembic upgrade head`，再运行 `python -m bluepulse_backend.worker sync-config` 将新来源同步到数据库；随后可运行 `python -m bluepulse_backend.worker ingest-once --source jiangsu-police-news` 单独采集。Police1 的 RSS 若返回 WAF 交互式挑战，会明确记录失败，不尝试用浏览器伪装或第三方代理绕过。

RSS/API 来源可用不调用模型、不写数据库的只读质量检查：

```powershell
python -m scripts.source_quality_smoke --source openalex-policing-tech
python -m scripts.source_quality_smoke --source gdelt-public-news
python -m scripts.source_quality_smoke --source police1-recent
python -m scripts.source_quality_smoke --source nist-public-safety-rss
python -m scripts.source_quality_smoke --source nist-forensic-science-rss
python -m scripts.source_quality_smoke --source govuk-policing-tech
```

2026-10-05 本机抽查：OpenAlex 可获取多数摘要，但仍需模型判定专业相关性；NIJ、江苏公安、采购网样本均取到全文；Police1 RSS 遇到交互式 WAF，无法从本机抓取；GDELT 本轮 49 条均为标题级且没有允许站点正文，因此不会公开。新增 NIST 两个栏目各取到 3 条摘要级近期新闻；GOV.UK 官方 API 取到警务 AI 政策等 3 条，其中附件导语只作摘要级，其他两条为正文级。正式单源采集时，GOV.UK 3 条均分析并入库；NIST Public Safety 3 条中 1 条判无关、2 条进入文章库且都未进精选。NIST Forensic Science 尚未执行正式采集。**这不是所有来源都已稳定产出可展示文章的证明**。站点结构、接口、网络路径和查询结果会变化，需周期性复查。

已确认的 20 条标注可通过 `python -m scripts.selection_eval --limit 15` 对开发集做只读模型回放，输出逐例相关性/精选对照；留出的 5 条可通过 `--split holdout --limit 5` 在规则定稿后验证。回放会调用模型，但不修改数据库或人工标签。当前样本规模小，不能据此声称精选质量已经稳定。

要把已确认标注用于旧文章，先运行 `alembic upgrade head`，再执行 `python -m scripts.apply_selection_gold` 预览，核对影响范围后才加 `--apply` 写入。人工标为无关的文章不再由公开 API 提供；人工标为相关但仍待模型处理的文章不会提前公开。该操作可重复运行，同一案例不产生新改动，已有其他人工决定不会被覆盖。导入前应备份开发数据库；标注 JSONL 保持原样。

积压盘点用 `python -m scripts.pending_audit`，不调用模型。需要先处理人工确认且有摘要的文章时，可用 `python -m bluepulse_backend.worker reprocess-pending --source openalex-policing-tech --editorial-only --limit 2`；不要盲目对只有标题的 GDELT 记录全量调用模型。`python -m scripts.content_smoke` 只读检查一个公开来源从文章列表到详情、原站链接和精选快照的 API 链路。

重复验收可运行 `python -m unittest tests.test_full_flow -v`：用独立临时数据库和离线模型替身验证一篇明确相关的文章从采集输出、分类、摘要/翻译、存储，到公开列表、详情、精选与图片字段，不修改开发库。若后端 `127.0.0.1:8000` 和前端 `127.0.0.1:3000` 已启动，还可运行 `python -m scripts.content_smoke --source govuk-policing-tech --frontend-url http://127.0.0.1:3000`，只读核验当前库的一篇真实公开文章在 API 和前端详情页的同一标题；输出 `frontend_checked: true` 即通过。前端精选只使用近 7 天候选，空时会解释原因，不拿旧文或低价值内容凑位。修改来源配置后先执行 `sync-config` 才会生效。

## 公开 API

- `GET /api/v1/home/featured`
- `GET /api/v1/articles?period=30d&topic=research&region=foreign&q=police&sort=recent&limit=20`（`period` 还支持 `all` 浏览历史资料）
- `GET /api/v1/articles?period=all&entity=axon&source_type=media`（实体 slug 与来源类型可组合筛选）
- `GET /api/v1/articles/{article_id}`
- `GET /api/v1/entities?type=vendor&limit=20`（仅列出有关联公开文章的实体及文章数）
- `GET /api/v1/taxonomy`
- `GET /api/v1/sources`
- `GET /api/v1/health/live` 和 `/api/v1/health/ready`

列表使用带排序键和筛选指纹的 cursor 分页；公开列表、详情与精选只展示 `processed` 且未软删除、未被人工判无关的文章。待处理或已判定不相关的原始记录仍保存在后台供后续分析，不在公开接口展示。精选先服从人工 `select/reject`，无人工决定时使用模型候选判断；按近 24 小时优先、不足时从近 7 天补足，最多六条。候选不足则留空，不用低价值相关内容凑数。

前端文章库位于 `/articles`，站内详情位于 `/articles/{id}`。中文全文存在时详情页默认显示译文，并可展开英文原文；中文全文缺失时明确标注并显示可用的原文；连原文也缺失时显示提示与来源链接。
实体目录位于 `/entities`，实体与来源类型筛选在文章库中可组合使用。

## 后续主线

人工选稿首轮试标已缩至 20 条本地案例：在 `backend` 目录运行 `.\.venv\Scripts\python.exe -m scripts.selection_review`，然后打开 `http://127.0.0.1:8765/`。每页 8 条，提供待复核的中文摘要和标签建议；单项修改即时保存，点击“确认本条”后计入已复核。建议稿与人工标签分开，原 40 条文件保留备份，已有部分标注也包含在新队列中。正式标注写入已忽略的 `data/selection-pilot-20.jsonl`；口径和完成后的检查命令见 `../docs/selection-annotation-guide.md`。此页面只监听本机，不是公开 API。

尚待补齐：更多实体别名与可靠消歧、更多站点的详情网页正文解析、带权限的运行状态管理 API、管理员登录与软删除操作、系统级自动化测试和 PostgreSQL 全文索引／实机验证。采集入口已有跨进程锁与显式中断恢复，但尚未覆盖历史重分析／翻译等维护命令。当前采集入口是受控配置同步与 worker 命令，没有匿名触发任意 URL 的接口。
