# 自动出稿、许可、归组与精选实施记录（2026-11-06）

## 范围与状态

本轮在现有 15 个采集入口上增加了**待启用**的自动出稿任务接口和单次执行器；同时按用户本轮决定，把默认本地库现有 15 源的站内全文许可打开。接口只排队，HTTP 请求本身不抓取网页、不调用模型。没有注册定时任务，没有配置内部令牌，也没有执行本轮真实外站采集或付费模型请求。正式部署及跨日期可用率仍未验证。

原始实现依据为 `D:/AIHOT/packages/backend/src/events/group.ts`、`publication/publish.ts` 等及本仓库 [AIHOT 交接](aihot-model-pipeline-handoff-2026-11-03.md)。Pulse 本轮复用的是“Fact 内折叠报道、每组选择代表、精选快照、读取时重查公开资格”这些机制；以 SQLite/FastAPI 的本地工作流实现。AIHOT 的语义事件合并、Story、独立参与方热点和日报没有在此轮移植。

## 实现

| 环节 | 当前规则与位置 | 边界 |
| --- | --- | --- |
| 来源全文许可 | `backend/bluepulse_backend/source_permissions.py` 的显式 `--allow-full-text`；详情读取由 `api.py` 再次检查 `Source.full_text_allowed` | 只修改指定库中现有 15 源；新增库/来源仍按原默认门禁，撤销许可后详情不再给正文 |
| 自动任务 | `auto_publication.py`、`models.py`、迁移 `f6b1c732d900`；内部 POST 排队、GET 查状态；后台 CLI 单次 claim 并执行 `source_worker.run_cycle` | 默认无令牌，API 为 503；无调度器；每源最多 2 个详情，瞬时错误最多再试 2 次；模型需双重显式开关 |
| Fact 归组 | `fact_grouping.py`；只把规范标题完全相同且原发布日相同的公开稿放进一个 Fact；缺日期/标题为单篇组 | 这是保守规则，无法识别改标题同事件；同一通用标题误并仍需抽查；没有 Story 关系 |
| 精选 | 同文件从近 7 天、已公开、相关、正文门禁通过且完成归组的稿件中选最多 6 篇；先覆盖不同来源，再按发布时间填满，每 Fact 一篇 | 本轮遵从用户“先放评分”，不调用五轴模型、不标记 `featured_candidate`；`importance_score=0`，理由注明未评分。是近期自动编排，尚不等于经模型精选质量认证 |
| 公开读取 | `GET /api/v1/home/featured` 读最新六槽；`GET /api/v1/site/timeline` 读近 30 日已有精选快照中的 Fact；`GET /api/v1/site/groups/{fact_id}/reports` 读该 Fact 当前可见报道 | 读取时检查公开/撤回/来源许可；热点为空；同组未精选报道只在阅读组出现；时间线目前在 Python 中装载近 30 日候选，规模化前须改为分页 SQL |

自动任务的阶段为：受控采集 → URL/正文/日期入库与去重 → 可选真实模型分类及摘要 → 原有公开资格重算 → Fact 归组 → 近期六槽快照。`max_model_calls=0` 时仍可采集并整理**已有公开稿**，新稿不会凭空成为已分类公开稿；只有显式配置模型并获相关分类且满足来源/正文门禁后才可能自动公开。失败留下 `failed` 和错误类型；采集单源失败见任务 `report.collection.sources[*].attempts`。

## 本机一次性验证事实

- 修改前备份：`backend/data/real-public-2026-11-05/bluepulse-before-fulltext-2026-11-06.db`；迁移/归组前另存 `bluepulse-before-auto-2026-11-06.db`。备份与数据库均被 Git 忽略。
- 默认本地 `backend/data/bluepulse.db` 的 15/15 个来源已打开 `excerpt_allowed` 与 `full_text_allowed`；35 篇真实材料中 26 篇满足当前公开资格。公开详情实际返回一篇 2,626 字符的原文正文。这是本地数据状态，不代表外部网站授予法律意义上的再发布许可；本轮使用的是用户对产品展示策略的明确授权。
- 已对这 26 篇公开稿执行保守归组，得到 **26 个 Fact、26 个成员，均为单篇组**。因此真实库尚未提供跨来源同 Fact 的正向实例；三篇合成测试稿中，同标题同日的两篇成功归为一个 Fact。
- 生成 **1 个近期精选快照、6 个席位**，均为未评分的自动编排。匿名 API 的 `articles?period=all&limit=100` 为 26 篇、`home/featured` 为 6 篇、`site/timeline` 为 6 个已入选 Fact；其他公开稿不被伪装成精选。
- 数据库迁移后 `alembic check` 无待生成操作；最终后端全套回归 **96 passed、1 条已有依赖弃用警告**，聚焦时间线测试 2 passed。

上面是真实**存量**库的本机读取和归组结果。本轮没有跑自动任务的真实网络/模型路径；任务执行链只由隔离库的模拟采集测试覆盖。前端浏览器联调仍需在后端服务启动后复验。

## 接口和按需执行

在 `repo/backend` 完成迁移后，只有设置服务进程环境变量 `BLUEPULSE_INTERNAL_TOKEN` 才能调用内部接口。令牌不得放入前端、URL 或仓库。POST 返回 202，重复 `idempotency_key` 与相同参数返回同一个任务；相同键不同参数返回 409。`source_slugs` 省略为全部现有 15 入口；`max_items` 上限 2，`max_model_calls` 上限 50，默认 0。

```http
POST /api/v1/internal/auto-publication/jobs
X-Bluepulse-Worker-Token: <服务器端令牌>
Content-Type: application/json

{"idempotency_key":"manual-2026-11-06-a","source_slugs":["govuk"],"max_items":2,"max_model_calls":0}
```

```http
GET /api/v1/internal/auto-publication/jobs/{job_id}
X-Bluepulse-Worker-Token: <服务器端令牌>
```

排队后，操作者可用**已迁移的隔离数据库**先验证执行器；以下命令的数据库路径须与 API 所用路径一致。无模型模式只采集和更新现有公开稿：

```powershell
cd D:\311实验室实用项目\警务科技情报\repo\backend
.\.venv\Scripts\python.exe -m bluepulse_backend.auto_publication --execute --database-url sqlite:///D:/path/to/isolated.db
```

要处理新的未分类稿，任务的 `max_model_calls` 必须为正，执行时还须同时给出 `--allow-paid-model --max-model-calls-total N`，且 N 不小于任务上限。真实调用前会确认所配模型在提供方列表中；密钥仅从本地配置读取。不要把试验路径指向默认库，也不要在没有运营预算和并发控制时注册系统计划任务。

## “模型额度只按单次进程限制”的具体含义

现有 `source_worker` 和此任务 CLI 的 `--max-model-calls-total N` 只在**当前 Python 进程的内存**中递减。例如两个进程各设 10 次上限，合起来仍可能发出 20 次请求；第二天或重启后计数又从 10 开始。任务表存储每个任务的 `max_model_calls`，但没有按日期/账户累加的持久预算账本，也没有在调用前原子占用额度。因此现在无法保证“全系统每天最多 N 次或最多花费 X 元”。

单个任务的 `pending → running` 条件更新可防止两个 worker 同时领取**同一个任务**。但两个不同任务仍可并行采同一来源、处理同一稿件：网络与模型花费可能重复，修订/去重写入也可能竞态。现阶段没有全局或逐来源互斥租约、心跳和崩溃后接管机制；进程崩溃还可能留下 `running` 任务，需要人工诊断。

失败信息可在任务状态和逐源 `report` 中查看，但没有主动通知。连续 robots/403/超时、模型 401/402/429、待处理任务积压或长时间 `running` 不会自动提醒负责人。启用无人值守运行前，至少需要：持久的按日/账户预算预占与结算、逐来源或全局租约及过期恢复、按错误类型/持续时间的告警阈值和通知通道。即使补齐这些能力，也要另做实站并发及失败恢复验收。
