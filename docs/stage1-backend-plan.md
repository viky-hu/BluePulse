# Stage1 后端实施计划：公开资讯采集与阅读闭环

> 面向负责后端实现的工程师。本计划限定 Stage1 可交付范围、服务边界、数据/API 契约、失败行为和验收要求。它与 [`system-construction-outline.md`](./system-construction-outline.md) 配套。当前仓库只有 Next.js 前端，尚无已部署后端；前端目前用 mock 数据展示初始封面 p0–p5。

## 1. 目标与完成定义

交付一个可独立运行的 Python 后端，使 Blue Pulse 能够每日从配置好的国内外公开来源抓取中英文警务科技与重要上游 AI 资讯，完成规范化、去重、中文处理、筛选和自动发布，并向前端提供近期精选、分类筛选、文章列表和详情。管理员可以查看已发布内容、软删除/恢复文章、查看采集运行状态并手动补跑。

Stage1 的主要阅读单元是一篇 **Article**。同一事件的多篇报道仍是多篇文章，只执行 URL/指纹级重复识别；不合并成 Event。系统自动发布，不要求管理员事前审核。具备来源与基本标题的文章即使某些解析/翻译字段缺失，也不得在流水线中静默丢弃。

### 验收结果

1. 成功运行一次采集，可从文章列表查到处理结果，并打开带原站链接的详情。
2. 中文与英文来源均可进入处理流程；英文文章默认提供中文标题、摘要及可获取正文译文，同时保留原文。
3. 首页可返回最多六篇精选，按近24小时优先、不足时近7天补足；不足六篇时返回实际数量。
4. 匿名 API 可按时间、主题、国内/国外、厂商/模型、来源和关键词查询，不暴露管理接口。
5. 管理员可登录、查看公开文章、软删除/恢复、查看采集任务并发起补跑；动作有审计记录。
6. 定时任务失败、模型不可用、单一来源不可用时有明确状态和可预期回退，不导致其他来源整批中断。

## 2. 技术与运行边界

### 建议技术栈

- Python 3.12+（部署环境最终确认具体运行时）。
- FastAPI REST API、SQLAlchemy 2.x、Alembic、PostgreSQL。
- 独立 API 进程和独立 worker 进程；worker 内运行 `Asia/Shanghai` 每日 06:00 调度，并从 PostgreSQL 领取手动补跑任务与写入运行记录。
- 首版不引入 Redis、Celery、Temporal、向量数据库或图数据库。worker 单实例调度；任务锁、运行状态、幂等键及恢复策略放在数据库中。若后续并发或任务量超出单 worker 能力，再评估队列。
- 模型供应商通过 adapter 接入；供应商、模型名、API 密钥、超时与预算由部署配置注入，禁止将密钥提交到仓库。
- 服务器操作系统、容器编排、反向代理和数据库托管方式由目标部署环境决定，本文不锁定云平台。

### 进程职责

| 进程/模块 | 职责 | 禁止承担的职责 |
| --- | --- | --- |
| REST API | 公共文章读取、搜索、精选、来源/分类目录；管理员会话和管理操作 | 不在 Web 请求生命周期中执行全量抓取或长时间模型调用 |
| Worker | 定时采集、手动补跑、解析、去重、模型处理、文章发布、精选快照生成 | 不暴露匿名执行任意 URL、任意代码或任意模型提示的接口 |
| PostgreSQL | 来源/文章/标签/媒体/精选/运行/管理员/审计等结构化数据 | Stage1 不承担向量检索或图谱数据库职责 |
| 模型 Adapter | 翻译、摘要、短标题、主题/实体和重要性结构化输出 | 不直接写数据库、不发布文章、不访问其他系统 |

配置至少分为：数据库连接、API 会话密钥、管理员 bootstrap 凭据/建号参数、模型供应商凭据、来源配置目录、抓取限速与超时、调度时区与时刻、日志级别。实际环境配置模板应有字段说明，示例值不得包含真实密钥。

## 3. 来源与采集范围

### Stage1 来源范围

采用受控来源清单，首批覆盖中国及美国的中英公开来源，类型至少考虑：公安/执法与政府机构、政府采购或项目公告、研究机构/学术、警务科技媒体、重点 AI/科技厂商官方资讯。具体站点由后端负责人形成首批配置清单并随交付提交；每个条目需记录名称、规范 URL、地区（CN/US）、来源类型、语言、覆盖主题、采集方式、启停状态、请求频率/时区、来源可信等级、条款/robots 检查备注。

首批采集优先 RSS、公开 API 和稳定 HTML 页面。只有登录后可访问、验证码、强反爬或违反来源条款的内容不尝试绕过；动态站点若无稳定公开接口，不列为首批必达来源。PDF 可作为公开附件解析能力，不要求首版下载/存档所有大文件。

### 安全与礼貌抓取

- 仅访问来源清单允许的 HTTP/HTTPS 目标；遵守站点条款、robots 规则及配置的请求频率，设置 User-Agent、连接/读取超时、响应体大小上限和重试上限。
- 处理重定向时重新校验域名和目标 IP，拒绝 loopback、私有网段、link-local、云 metadata 等地址，避免 SSRF；默认拒绝非 HTTP(S) scheme。
- 单来源异常只记录该来源失败并继续其他来源；解析器不可执行页面脚本，不运行下载内容中的代码。
- 清理并转义 HTML 后输出前端，避免正文作为任意 HTML 注入；保存允许的文本与媒体链接，不默认镜像媒体二进制。

## 4. 采集处理流程

每次调度或手动补跑创建 `IngestionRun`，为每个来源写独立结果。流程如下：

```text
领取调度/手动任务
  → 读取启用的来源配置
  → 拉取 RSS/API/公开 HTML
  → 提取候选文章、正文和媒体元信息
  → 标准化 URL、日期、语言、原始标题和文本
  → canonical URL + 内容指纹去重
  → 语言/主题/地区/组织与模型标注
  → 模型生成中文标题、摘要、正文译文和重要性分
  → 字段校验、质量状态与失败回退
  → 自动发布文章
  → 成功完成后事务性刷新近期精选快照
  → 完成运行统计并记录各阶段结果
```

### 解析与规范化

- 统一时区为 UTC 存储；API 返回 ISO 8601 时间。地区展示使用“国内/国外”；Stage1 主要覆盖 CN/US，国家代码可作为来源/文章元数据保存，不作为前端一级国家菜单。
- 保存 `source_title`、`source_url`、canonical URL、来源 ID、`published_at`（可空）、`first_seen_at`、`fetched_at`、语言、作者（可空）、清理后的原文文本和解析状态。
- 文章详情包含媒体数组，至少表达媒体类型、来源 URL、缩略图 URL（如有）、说明文字/alt、展示顺序和解析状态。评论只在来源提供可公开、稳定且允许解析的数据时尝试；否则 `comments.available=false`，详情仍提供原站链接。
- 评论抓取默认关闭，只有来源配置明确启用且通过公开性、条款和稳定性检查时才解析；设置单篇上限并保存清理后的必要字段，不抓取登录可见内容或敏感个人信息。详情统一返回 `comments: { available, count, items }`；不可用时返回 `available=false`、`count=0`、`items=[]`，不能用空数组暗示“来源确认没有评论”。
- 完全重复按 canonical URL 唯一约束识别；不同 URL 的高度相似正文由规范化文本指纹/相似度规则标记重复候选，不自动丢弃不同来源的独立报道。保留重复关系和首见文章，便于审计。

### 模型处理契约

模型 adapter 为每个任务返回符合 JSON Schema 的结构化结果和调用元数据，不接受自由格式拼接数据库字段。单篇输出至少包括：`zh_title`、`zh_summary`、`zh_body`（仅在原文可解析且译文成功时）、主题 ID、标签、region、组织/厂商/模型候选、相关性、重要性 0–100、简短理由、语言、处理状态、provider/model/prompt 版本。

- 中文短标题目标约15字，保留原题关键信息；无法安全浓缩时使用可读的原始/翻译标题并标记 `title_fallback`。
- 摘要、标题和翻译不得增加原文没有的数字、事实或因果关系；重要陈述以来源原文为准。数据库保留原始标题及原文，供对照。
- 模型输出先做 schema、长度、必填字段和安全内容校验；非法输出最多按配置重试一次，仍失败时写入模型错误状态并继续可用字段处理。
- 翻译失败不删除文章：前台优先显示成功的中文字段，缺失部分显示原文并标明未翻译。摘要/正文解析失败时不生成虚构正文，显示可用标题、摘要状态和原站链接。
- 模型 API 超时、额度/密钥错误要记录为可查询错误类别；不把密钥或敏感请求头写日志。模型处理成功状态和文章发布状态分开存储。

### 自动发布与精选规则

- 一篇文章满足最低身份条件（有效来源、来源 URL、非空标题）即进入公开文章库；相关性低、翻译失败或正文缺失作为质量标记，不进入待审批队列。管理员可以事后软删除。
- 重要性取模型经过 schema 校验的 0–100 分；分数相同时按发布时间较新优先，再按稳定文章 ID 排序。需记录评估版本和简短理由，便于解释精选结果。
- 每日运行成功后生成新的精选 edition：先取 `generated_at` 前24小时内的文章按重要性排序；不足6篇时从近7天剩余文章补入；不重复文章；最多6篇。若7天内不足6篇，保留实际数量。窗口内无文章则返回空数组，不回退到更旧内容。
- 第1个位置为 p0，其余按 p1–p5。快照包含生成时间和实际使用的窗口（24h/7d）；新快照只在采集处理批次成功结束后原子替换当前快照，失败不清空已有精选。

## 5. 数据实体与关系

下列为逻辑实体，最终列名由实现统一采用 snake_case，并由 Alembic 管理迁移。公开 ID 使用不泄露数据库自增序号的 UUID/等价不可预测 ID。

| 实体 | 关键字段/关系 | 用途 |
| --- | --- | --- |
| `Source` | id、name、base_url、region、country_code、language、source_type、topics、trust_level、enabled、fetch_config | 配置文件同步后的来源元数据；运行时状态在数据库维护 |
| `Article` | id、source_id、source_url、canonical_url、source_title、zh_title、source_body、zh_body、zh_summary、language、region、published_at、first_seen_at、importance_score、relevance、quality_status、processing_status、model_metadata、deleted_at | 一条公开资讯及其原始/处理版本 |
| `ArticleTopic` / taxonomy | topic_id、article_id、primary flag；主题含稳定 slug 和中英文显示名 | 七个首版一级主题及扩展标签 |
| `Entity` / `ArticleEntity` | entity_type（organization/vendor/model 等）、canonical name、aliases、region、article relation | 厂商、模型、机构目录及文章关联；实体可渐进规范化 |
| `ArticleMedia` | article_id、kind、url、thumbnail_url、caption、alt_text、position、status | 图片/视频/附件元信息与外链 |
| `DuplicateLink` | article_id、duplicate_of、method、score、created_at | 标记相似重复，不混淆多来源报道 |
| `FeaturedEdition` / `FeaturedSlot` | edition_id、generated_at、window、slot（p0-p5）、article_id、rank、score | 固化当天/当前一版精选结果 |
| `IngestionRun` | id、trigger_type、scheduled_for、started_at、finished_at、status、counts、error_summary、idempotency_key | 每日任务和人工补跑状态 |
| `SourceRun` | run_id、source_id、status、counts、last_cursor、error_class、error_message | 单来源抓取结果和故障隔离 |
| `AdminAccount` | id、username、password_hash、is_active、created_at、last_login_at | 部署人员创建的管理员账号，无公开注册 |
| `AdminSession` | id、admin_id、token_hash、created_at、expires_at、revoked_at、last_seen_at | 持久化可撤销的管理员会话；只存 token 哈希，不存浏览器 cookie 原值 |
| `AdminAuditLog` | admin_id、action、target_type、target_id、timestamp、request_id、metadata | 登录、删除/恢复、手动补跑等审计事件 |
| `ArticleComment`（可选） | article_id、source_comment_id（可空）、author_label（可空）、body_text、published_at（可空）、source_url（可空）、status | 仅为显式启用且公开、允许、稳定可解析的来源保存最少评论信息；默认不采集 |

软删除通过 `deleted_at` 等状态表达；公共查询、精选和搜索始终排除已删除文章。保留恢复能力，不对管理员删除执行物理删除。原始文章正文、译文与模型处理元数据分字段存放，更新译文不得覆盖原文。

## 6. REST API 契约

API 前缀固定为 `/api/v1`，JSON 使用 UTF-8；列表统一 cursor 分页，默认 `limit=20`、最大 `limit=100`。文章列表和实体目录的默认排序为发布时间降序、稳定 ID 升序；`sort=importance` 使用重要性降序、发布时间降序、稳定 ID 升序。游标编码完整排序键与必要筛选版本，下一页边界不使用 offset，避免相同发布时间时重复或漏项。错误统一使用 `{ "error": { "code": "...", "message": "...", "request_id": "..." } }`。所有公开接口排除软删除文章。

### 公开接口

| 方法与路径 | 说明 | 参数/返回重点 |
| --- | --- | --- |
| `GET /home/featured` | 当前精选快照 | 返回 `generated_at`、`window_policy`、`items`（slot、article 简要卡片、importance），最多6条 |
| `GET /articles` | 资讯流、检索与筛选 | `period=24h\|7d\|30d`、`topic`、`region=domestic\|foreign`、`entity`、`source_type`、`q`、`cursor`、`limit`、`sort=recent\|importance` |
| `GET /articles/{article_id}` | 单篇详情 | 中文/原始字段、来源、时间、标签、实体、媒体、评论状态与可选条目、原站链接、质量提示 |
| `GET /taxonomy` | 主题及筛选枚举 | 稳定 ID/slug、名称、层级、启用状态 |
| `GET /entities` | 厂商、模型和机构目录 | `type`、`region`、`q`、分页；返回文章数量或关联入口 |
| `GET /sources` | 公开来源目录 | 来源类型、地区、语言、覆盖主题；不公开管理密钥和内部错误 |

`period` 以请求时刻为基准滚动计算。筛选条件采用 AND 组合；一个主题或实体可同时对应多篇文章。详情中的正文以清理后的纯文本/受限内容块返回，前端不得直接执行未经净化的来源 HTML。

`GET /home/featured` 示例：

```json
{
  "generated_at": "2026-09-23T22:00:00Z",
  "window_policy": "24h_then_7d",
  "items": [
    {
      "slot": "p0",
      "article": {
        "id": "7fbd2c2e-4fc2-4bb7-bec1-7dcb7a149347",
        "title": "公安大模型平台启动建设",
        "source_title": "原始来源标题",
        "published_at": "2026-09-23T15:20:00Z",
        "source": { "id": "source-id", "name": "来源名称" },
        "url": "https://example.org/news/123"
      },
      "importance_score": 92
    }
  ]
}
```

### 管理接口

| 方法与路径 | 说明 | 权限与行为 |
| --- | --- | --- |
| `POST /admin/session` | 管理员登录 | 校验凭据、限速；成功设置 HttpOnly/Secure/SameSite 会话 cookie，并记录登录审计 |
| `DELETE /admin/session` | 登出 | 撤销会话并写审计 |
| `GET /admin/articles` | 管理文章列表 | 含质量/翻译/解析状态与软删除状态；支持筛选和分页 |
| `POST /admin/articles/{id}/delete` | 软删除 | 从公开查询立即隐藏，记录管理员、时间和原因（原因可选） |
| `POST /admin/articles/{id}/restore` | 恢复 | 恢复公开可见性；精选快照在下一次成功生成时纳入 |
| `GET /admin/ingestion-runs` | 查看运行历史 | 含总体和分来源统计、错误类别，不含密钥 |
| `POST /admin/ingestion-runs` | 手动补跑 | 只允许创建受控采集任务，可选来源 ID；返回 `run_id`，不在请求中同步阻塞执行 |
| `GET /admin/ingestion-runs/{run_id}` | 查看运行详情 | 状态、阶段计数、来源结果、错误摘要 |

手动补跑任务以请求幂等键防止重复提交；同一时刻只允许一个全局采集 worker 执行任务。首版来源配置由部署人员修改配置文件并按运行流程加载，管理 API 不支持任意 URL 写入，也不提供来源 CRUD。

### 管理员安全边界

- 管理员账号只由部署人员通过安全 bootstrap/CLI 流程创建或更新，不提供注册、后台创建账号或默认弱口令。
- 密码使用 Argon2id 等现代密码哈希；会话 token 高熵、可撤销，浏览器 cookie 设置 `HttpOnly`、生产环境 `Secure`、`SameSite`，写操作需 CSRF 防护。
- 登录限速并避免区分“账号不存在/密码错误”；管理操作带 request ID 并进入只追加审计日志。
- 删除/恢复接口仅修改公开状态，不返回原文给匿名调用者；所有管理路由未认证时返回 401，非管理请求不能绕过公开查询过滤。

## 7. 失败处理、幂等与可观测性

| 失败场景 | 处理要求 |
| --- | --- |
| 单一来源超时/HTTP 错误 | 标记该来源失败，按有限退避重试；继续其他来源，记录状态码/错误类别和最近成功时间 |
| 来源页面结构变化/正文为空 | 保存候选文章和解析状态（若有来源 URL 与标题）；返回原站入口，不生成虚假正文；将来源标为需维护 |
| 模型超时/限额/无效 JSON | 记录模型任务错误与版本；最多按配置重试；保留原文并发布可用字段，中文字段清晰回退 |
| 内容重复 | canonical URL 唯一冲突转为幂等跳过；相似内容记 DuplicateLink，不阻断其他文章或来源 |
| Worker 进程重启 | 任务租约过期后可恢复；完成过的文章不重复插入；成功精选快照不被未完成运行覆盖 |
| 数据库不可用 | API 返回可识别 503，worker 停止写入并失败退出；日志不得打印凭据 |
| 没有精选候选 | 返回空 `items` 和最近快照元数据（如有）；不拿超过7天的旧文章凑数 |
| 管理员删除文章 | 事务写软删除和审计记录，所有公共列表/详情/精选立即不可见；恢复不清除历史审计 |

每次运行至少统计：来源数、成功/失败来源、发现数、新增数、重复数、解析失败数、模型成功/失败数、发布数、运行耗时。提供 `/health/live` 与 `/health/ready`；ready 检查数据库可用性，不触发采集。结构化日志包含 `run_id`、`source_id`、`article_id`、request ID，不包含 API key、cookie 或密码。

## 8. 测试与交付物

### 自动化测试

- 单元测试：canonical URL 清理、时区/日期规范化、内容指纹、主题和模型响应 schema、输出安全净化、精选排序/补足/去重规则。
- 解析器测试：RSS 与 HTML fixture 的中英文文章、缺失发布时间、无正文、图像/视频链接、异常结构与重定向拒绝。
- Pipeline 集成测试：新文章端到端发布；重复 URL 幂等；单来源失败隔离；翻译/模型失败仍保留原文；worker 重启恢复；失败运行不替换最后成功精选快照。
- API 集成测试：匿名列表/详情/筛选/分页；软删除后公开不可见；管理路由匿名 401；管理员登录、删除、恢复、审计；CSRF/限速关键路径。
- Worker 测试：`Asia/Shanghai` 每日 06:00 配置、手动补跑、唯一任务锁与重复幂等键。

### 提交给项目的后端成果

1. 可运行的 FastAPI 服务与独立 worker 入口。
2. PostgreSQL schema、Alembic 初始迁移和 bootstrap 管理员创建流程。
3. 有字段注释的来源配置模板及首批来源清单（标注地区、类型、采集方法、覆盖主题和访问检查结果）。
4. 模型 adapter 接口、至少一个可配置供应商实现，以及不依赖外部模型的 mock/test provider。
5. OpenAPI 文档、本文 API JSON 示例、运行配置样例和启动/迁移/补跑说明。
6. 单元和集成测试，以及运行状态/健康检查说明。

### 后端完成验收

- 从全新数据库可完成迁移、创建管理员、启动 API 与 worker；密钥不需写入代码。
- 一次采集可处理至少一个中文和一个英文 fixture 来源，生成并查询文章详情、媒体元信息和原文追溯链接。
- 重要性排序、p0–p5 与24小时/7天补足规则通过测试；不存在重复槽位。
- 列表分类/地区/实体/来源/关键词筛选和 cursor 分页有效；时间窗口使用 UTC 数据正确计算。
- 任何一个来源或模型失败都可在管理运行页/API 查到，不造成静默丢文或覆盖成功精选。
- 删除后的文章从所有匿名接口消失，管理员可恢复，审计记录完整。
- 自动化测试全部通过，并提供一份针对配置源的可重复 smoke test 结果；不得把外部源临时不可用当作测试通过的证据。

## 9. Stage1 明确不做

- 不合并多篇文章为事件，不维护项目生命周期、Claim/Evidence 图谱或自动事实裁决。
- 不提供趋势/Radar、知识图谱、日报/周报生成、邮件或即时通讯推送。
- 不做普通用户注册、收藏、个性化订阅或推荐。
- 不做来源配置后台；来源由版本化配置文件维护并审查。
- 不默认保存图片/视频二进制，不尝试登录绕过、验证码绕过或非公开评论抓取。
- 不因准备未来能力而首版部署向量数据库、图数据库、Redis 或多 Agent 框架。
