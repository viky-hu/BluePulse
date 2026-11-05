# Blue Pulse 后端基础链路

本目录是 2026-10-27 从空后端重建的 **M0–M2 骨架**。当前可运行的链路是：`SourceAdapter → Candidate → URL/来源校验 → Material/Revision/Discovery → Analyzer → 已存结果恢复 → 公开资格 → /api/v1`。`MockSourceAdapter` 和 `MockAnalyzer` 用于离线检查；十五个限量真实来源入口和一个真实模型调用器只通过显式试验命令执行。正式数据库不自动填充测试资讯。

**2026-11-05 本地真实稿进度：** 用户明确允许现有 15 源的摘录展示后，在备份原空库的前提下，默认 `data/bluepulse.db` 已装入 35 篇有原文链接的真实材料，35/35 完成真实模型分类，26 篇可由公开 API 阅读；15 源各至少有 1 篇公开详情。全文许可仍关闭，只展示摘要、分类和原站链接。该库来自 11-03 限量实采并追加 11-05 的受控采集，尚非持续生产部署。逐源结果、运行命令和备份位置见[真实分类与展示记录](../docs/real-public-flow-2026-11-05.md)。

旧后端的人工选稿标注已从删除前备份恢复到忽略目录 `data/legacy-selection/`。20 条已确认金标准、40 条试标池和两份 95 条候选池的校验和与使用限制见[恢复记录](../docs/selection-recovery-2026-10-28.md)。这些数据未导入新数据库；旧标注脚本依赖旧模型，不能直接用于当前后端。

## 本地运行

在 `repo/backend` 下执行：

```powershell
uv venv .venv
uv pip install --python .venv/Scripts/python.exe -e ".[test]"
.\.venv\Scripts\python.exe -m bluepulse_backend.cli migrate
.\.venv\Scripts\python.exe -m bluepulse_backend.cli sync-taxonomy
.\.venv\Scripts\python.exe -m uvicorn bluepulse_backend.api:app --host 127.0.0.1 --port 8000
```

数据库默认在 `backend/data/bluepulse.db`，可通过 `BLUEPULSE_DATABASE_URL` 指向独立数据库。新数据库只含七个主题，没有来源或文章；前端看到真实空态。`启动BluePulse.bat` 仍只启动前端，后端须单独启动。

## 离线完整性检查

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.tmp/pytest
.\.venv\Scripts\python.exe -m bluepulse_backend.mock_check
.\.venv\Scripts\python.exe -m alembic -c alembic.ini check
```

`mock_check` 使用临时 SQLite 库和 `example.test`，输出逐源漏斗、处理结果与 HTTP 状态，退出后删除临时数据。它不会写正式库，也不会从网络采集。测试覆盖去重、修订、历史材料、来源失败、分析失败重试、结果未知、已存回执恢复、撤回、许可、精选门禁、分页与错误码。

## 限量真实试验

### 来源采集入口

GOV.UK publication 的英文 HTML 与 CSV 文字附件已接入限量提取；2026-11-04 的[复测记录](../docs/govuk-text-attachment-2026-11-04.md)记录了附件原链接、表格结构、资产主机 robots 与两种格式逐行一致的结果。同一表格不重复并入正文；PDF 与多媒体未处理。11-04 试验时来源公开许可仍关闭，11-05 的本地摘录许可变更另见最新记录。

2026-10-29 的前五站只读探针见工作区根目录[《前五信源采集探针》](../../前五信源采集探针-2026-10-29.md)。探针每站最多检查 3 个详情，只输出元数据与正文长度，不写业务库或调用模型：

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.top5_probe --source npcc --max-items 3 --execute --output data/probe-npcc-next.json
```

试验来源目录包括 GOV.UK、NIST Public Safety、NIST Forensic Science、中国政府采购网、NPCC News、江苏省公安厅警务动态、Police Digital Service、Biometric Update 执法栏目、HTX News、Police Science & Technology、StateScoop 执法技术栏目、NIST Information Technology、NIST Standards、Europol Newsroom 和 Singapore Police Force Police Life。NIJ 技术专题已按用户决定退出当前活跃目录，历史试验数据仍保留。选源依据、每源状态与采集门禁见[信源与采集链路记录](../docs/source-collection-2026-10-28.md)、[新增信源试验](../../新增信源试验-2026-10-29.md)、[第 6–9 项扩源试验](../../信源6到9试验-2026-10-29.md)、[新增五信源探针](../../新增五信源探针-2026-10-30.md)、[三站提取路径复查](../../三个信源提取路径复查-2026-10-30.md)、[Police Science 自动采集复测](<../../Police Science自动采集复测-2026-10-31.md>)、[新增三信源试验](../../新增三信源试验-2026-10-31.md)及[新增两信源试验](../../新增两信源试验-2026-10-31.md)。默认 `preview` 只读外站、最多返回 2 条且不写数据库或调用模型：

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.source_collection --source ccgp-policing-tech --mode preview --max-items 2 --execute
```

`--mode ingest` 需提供已迁移的 `--database-url`，材料保持待分析状态；`--mode ingest-analyze` 还需 `--allow-paid-model`，从工作区 `.env` 读取模型配置并在调用前核验 `/models`，通过 `--max-model-calls` 限制本次分析次数（1–5）。新建来源默认不允许对外摘录或全文展示；核对来源条款和内容质量后才可调整公开许可。入口不自动定时运行，也不导入旧标注。

### 自动触发与诊断（2026-11-04）

新的 `source_worker` 是可由 Windows 任务计划程序调用的命令入口，也能在一次进程中按间隔运行限定次数。每次对现有 15 入口最多取 2 条；网络超时、传输错误和 HTTP 5xx 最多重试 2 次，每次都是独立 `SourceRun`，不会重试 robots 禁止、403、429 或解析错误。结构化 JSON 诊断保存在 `data/source-worker/`。先对**单独已迁移库**运行，例如：

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.source_worker --execute --database-url sqlite:///D:/path/to/isolated.db --max-items 2 --retry-attempts 2 --report-dir data/source-worker
```

显式追加 `--allow-paid-model --max-model-calls-total 4` 才会核验模型并处理已采材料；该上限覆盖本进程全部来源和周期。当前相关稿通常占 **1 次分类＋2 次独立五轴评分**，所以 4 次上限通常只能完整处理 1 篇相关稿；额度不足时保存第一分并在下轮续做第二分。当前只需分类和公开时追加 `--classification-only`，不会进行五轴评分。可加 `--cycles 2 --interval-seconds 3600` 自动重复两轮；进程退出后预算不跨进程累计。模型断线结果未知时保留回执待处置，不自动重发。每份正文至少 **300 个非空白字符**才进入自动模型处理及公开资格；不强制打开附件，旧稿仍可进入 `period=all`。模型分类判相关、给出摘要和至少一类后，若来源已允许摘录，自动进入公开列表，无人工审核步骤。五轴双评分只决定精选候选及展示的 `importance_score`；各来源门槛默认未校准，完成两分也不会自动入选首页。每轮按当前来源权限重新投影已分析材料，许可打开或关闭都不重复付费。新来源代码默认许可仍关闭，模型结果不会自行更改许可；11-05 本地库已按用户授权显式打开 15 源摘录许可。详情全文仍由 `full_text_allowed` 独立控制。实测与边界见[自动采集及收紧记录](../docs/source-automation-2026-11-04.md)、[五轴双评分记录](../docs/dual-selection-scoring-2026-11-04.md)。

### 首批内部选稿试运行

首批 4 篇官方原文的[试运行结果](../docs/editorial-pilot-result-2026-11-03.md)从已有本地 `baseline-*.json` 和主题复核记录生成，不发网络请求、不调用模型，也不写默认业务库。在 `repo/backend` 下，使用一个**尚不存在或为空**的输出目录：

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.editorial_pilot prepare --selection-file config/editorial-pilot-4.json --input-dir data/source-validation --output-dir data/editorial-pilot/first-batch
.\.venv\Scripts\python.exe -m bluepulse_backend.editorial_pilot record --output-dir data/editorial-pilot/first-batch --review-file data/editorial-pilot/first-batch/review-first-pass.json
```

`prepare` 在独立 `editorial-pilot.db` 导入并重放同批候选，生成含正文与证据段落的本地 `packet.json` 和可编辑的 `review-template.json`。若需重新准备，请指定新的空目录。复核者填写 `decision=pending/advance/hold/reject`、姓名、理由、原页与逐项事实检查；`advance` 只有原页和证据锚点都核对后才可记录。`record` 将决定绑定材料修订与内容哈希，发现修订或来源许可变化即拒绝记录，写出带时间戳的内部结果文件。这里的 `advance` 仅指进入下一步人工编辑，**不修改材料公开状态、来源许可或正式库**；最终采用和公开仍须单独审批与政策核对。

### 15 源单日全流程试跑

2026-11-04 的[真实稿本地闭环试验](../docs/real-article-local-closure-2026-11-04.md)从 GOV.UK 限量采集 2 条、对其中 1 条做 1 次真实模型分类，在隐藏隔离库验证 0 公开；再复制为仅供本机测试的展示库，实际核对分类列表和详情页。运行命令、逐项结果及模型导读的事实措辞问题见报告。常规 `source_collection` 的 GOV.UK/NIST 路径已统一进行 robots 预检，失败不会继续访问搜索或 RSS。

[2026-11-03 实时端到端限量测试](../docs/live-end-to-end-2026-11-03.md)在新隔离库直接联网采集现有 15 个入口、每源最多 2 条；首轮 Europol robots 请求传输故障在同规则复测后成功，最终 30 条入库，4 条代表样本完成真实模型分类，真实稿公开数为 0。命令保留逐源请求、正文、日期、重放去重及 API 证据。新空目录运行（付费模型调用需显式开启，最多 4 次）：

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.live_end_to_end --execute --allow-paid-model --max-items 2 --max-model-calls 4 --output-dir data/live-end-to-end/next-run
```

仅采集与入库时省略 `--allow-paid-model` 并设 `--max-model-calls 0`；失败单源可在同一目录加 `--retry-source europol-news` 复测。不要把这次限量成功解释为跨日期稳定或全部 30 条完成分类。

[2026-11-03 试跑报告](../docs/full-day-pilot-2026-11-03.md)用 11-01 留存的 15 × 2 篇归档样本，在独立库完成导入、去重、分析回执、主题关系和 API 检查。它使用人工复核标签作为固定分析输入，30 篇均被处理；6 篇进入内部待审，15 篇暂缓，9 篇拒绝。真实稿因来源公开许可门禁而不会显示；分类列表和详情的正向接口契约由**另一独立库的合成许可样本**验证。正式业务库未写入、文章未公开。前端当前七类已对应新库 taxonomy；正式库须在部署准备完成后单独同步。

在 `repo/backend` 下指定新的空输出目录复跑：

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.full_day_pilot --output-dir data/full-day-pilot/replay-01
```

另对 4 篇代表样本做过真实模型分类试验，最大调用数与实际调用数都是 4；3 篇与人工口径一致，GOV.UK 附件证据不足的样本被模型判为主题相关，仍须由证据门禁暂缓。脱敏回执与限制见同一报告。确需重跑模型核验时，显式使用新的隔离输出目录和调用上限：

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.full_day_model_probe --execute --allow-paid-model --max-model-calls 4 --output-dir data/full-day-pilot/model-replay-01
```

### 文章去重与新旧稿

[去重与日期验证报告](../docs/dedup-freshness-2026-11-03.md)记录了归档 60 条入口样本的隔离回放：同 URL 后为 59 条材料，另识别 NPCC/PDS 一组不同 URL 的高置信同稿，独立正文为 58 份；StateScoop 4 条均判历史稿。入库只自动关联同标题、同发布日期、正文高度重合的同稿；镜像保留来源证据但不重复调用模型或进入公开列表。仅有日期的页面不会被当作精确到小时的发布，`24h` 列表排除这类材料。使用新空目录复跑：

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.dedup_freshness_pilot --output-dir data/dedup-freshness-pilot/replay-next
```

### 15 源逐日限量验证

采集方式、历史故障及 2026-11-01 首轮结果见 [15 源台账](../docs/source-validation-ledger-2026-11-01.md)、[稳定性与正文质量记录](../docs/source-validation-baseline-2026-11-01.md)和[主题质量抽查](../docs/source-quality-2026-11-02.md)。在 `repo/backend` 下每日执行一次；网络命令每入口最多 2 篇，不调用模型，原响应只在本地忽略目录保存每源首篇，`observation.db` 是独立观察库：

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.source_validation --max-items 2 --execute
.\.venv\Scripts\python.exe -m bluepulse_backend.source_validation_summary --output data/source-validation/daily-summary.csv
.\.venv\Scripts\python.exe -m bluepulse_backend.source_validation_compare
```

如需复测单源，在第一条命令加 `--source npcc` 等 slug。每次留下不同时间戳的 `baseline-*.json` 和 `review-*.json`；review 模板的 `topic_fit`（`direct/adjacent/off`）、正文清洁度、证据充分度和选稿适配度由人工填写，不能用 `full_text` 自动代替。单次专题质量抽样可显式运行 `--source npcc --max-items 5 --quality-sample --execute`；日常命令的默认上限仍为 2。标注后按采集日期输出样本主题密度：

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.source_quality_summary --as-of 2026-11-02 --run-from 2026-11-01 --run-to 2026-11-02 --new-only --output-csv data/source-validation/source-quality-2026-11-02.csv --output-json data/source-validation/source-quality-2026-11-02.json
```

`--new-only` 按本地归档的首次发现日排除更早已采 URL；逐日或滚动质量密度请保留此前基线文件。

此密度分母为已标注的来源 × 不同 URL，不能当成全站或未来供稿密度；JSON 另列跨入口同 URL/同标题重叠。汇总 CSV 按自然日及来源记录所有运行；同日重试不覆盖首跑，`same_snapshot_duplicate` 为本次同一候选重放的机制检查。`database_modes=longitudinal` 时的 `duplicate` 才反映观察库既有 URL；11-01 早期文件标为 `isolated`，其多次 `new` 来自不同临时库，跨日基数以 `observation-seed.json` 的 30 条为准。每天检查失败阶段和原始发布日期，约 14 天后再按独立日期评审；无新稿与访问失败分开统计。`observation.db` 与旧的单轮 `baseline-*.db` 均在 `backend/data/`，不会写默认 `bluepulse.db`。本轮未调用模型；后续若做模型质量抽样须单独指定少量样本和明确调用上限。

工作区根目录 `.env` 使用 `base_url`、`key`、`llm_id` 三个字段；密钥不得写入命令、日志、Git 或前端环境变量。试验命令：

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.live_pilot --execute
```

命令只读 [GOV.UK Search/Content API](https://docs.publishing.service.gov.uk/repos/search-api/using-the-search-api.html) 和 [NIST Public Safety RSS](https://www.nist.gov/coo/nist-rss-feeds)；NIST 从 RSS 发现后，再限量读取官方详情正文。每源最多两条，模型总调用最多两次。请求限制 HTTPS 主机、响应大小、超时、重定向和输入/输出 token 数。每次生成独立的 `backend/data/live-pilot-*.db`；两个试验来源均设置 `excerpt_allowed=false`，不会进入正式公开 API。脱敏结果写入工作区根目录的 `真实采集试验.md`。

模型调用前通过只读 `/models` 核验配置 ID。若未列出，采集仍运行但模型调用上限自动降为零。`started/unknown` 的付费尝试不会自动重发。继续试验应在核对服务端模型和旧回执后，使用 `live_pilot_resume` 只处理此前未调用的材料。

## 已有匿名接口

| 路径 | 当前状态 |
| --- | --- |
| `GET /api/v1/health/live`、`health/ready` | 存活/迁移就绪 |
| `GET /api/v1/sources`、`taxonomy` | 来源与七主题目录 |
| `GET /api/v1/articles`、`articles/{uuid}`、`articles/availability` | 公开文章筛选、详情、收藏可用性；保留 UUID、游标、snake_case |
| `GET /api/v1/home/recently-collected` | 最近收录的公开文章，最多六条 |
| `GET /api/v1/home/featured` | 读取显式精选快照；未生成时 `generated_at=null, items=[]` |
| `GET /api/v1/site/timeline` | 近 30 日已公开材料时间线，支持地区/主题筛选与分页；未精选、归组或生成热点时返回空值 |
| `GET /api/v1/entities` | 当前真实空目录；实体抽取还未接入 |

统一错误为 `{error:{code,message,request_id}}`，响应包含 `X-Request-ID`。`/openapi.json` 提供路径、参数和响应模型。`articles` 支持 `period/topic/region/source/source_type/entity/q/sort/cursor/limit`；`entity` 在实体链路建立前只会得到空结果。不存在、隐藏或撤回的详情统一为 404；历史材料仍可在 `period=all` 中阅读。默认只提供摘要和原站链接；来源许可明确允许时才返回全文。

## 目前边界

- 当前 15 个显式限量入口分布于 12 个主机；具体路径见台账。NPCC、江苏、PDS、StateScoop、Europol、采购网等有过本机连接阶段间歇故障；Police Science 有受控的 robots 自重定向处理。Government Technology 返回 WAF challenge，OpenAlex 按用户决定暂不考虑，NIJ 因当前专题入口少且旧文占比高暂停。各源尚无连续稳定结论。HTX、NPCC、PDS 等只有日期的页面已保存日期精度；定时触发命令已提供，但尚未注册系统任务或在正式库持续运行；站点条款自动核验仍未实现。试验适配器不绕过访问挑战。
- 自动公开资格现在要求 `full_text` 正文至少 300 个非空白字符；原有 `min_body_status` 数据字段保留兼容，不再允许以薄摘要自动公开。
- 模型调用器支持 `.env` 指定的 OpenAI 兼容 Chat Completions 端点。相关稿的分类与两次五轴评分分别写回执；`started` 或 `unknown` 尝试不会自动重发。来源精选门槛默认未校准，跨进程付费预算、五轴人工金标和模型评测仍待完善。
- 精选快照要求公开、够格、非历史且归组完成。Fact/Story 归组尚未实现，所以正式运行不会自行生成精选；mock 测试通过显式标记验证门禁。热点、日报、Agent、反馈及管理员接口尚未实现，不返回伪造内容。
- 本地 SQLite 便于离线测试；PostgreSQL 并发、游标、迁移和运行负载尚未验证。旧数据库未导入，也不能用这套新迁移直接升级旧库。

后续工作按工作区根目录的《后端重构计划》推进。项目内其他历史文档所写“旧后端已实现”均是 2026-10-27 删除前的状态。
