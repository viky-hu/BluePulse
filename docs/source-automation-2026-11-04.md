# 现有 15 源收紧与自动采集入口（2026-11-04）

本轮按用户决定继续使用现有 15 个入口，不扩源。正文达到 300 个非空白字符且适配器确认是正文时，作为自动处理的最低内容条件；无需先取得附件或外链报告。摘要仍只能陈述实际采到的正文，不能声称已核实未读取的文件。旧稿可以进入文章库 `period=all`，不改写原始发布日期。模型判断相关、给出中文摘要和至少一个类别后，已有公开许可的来源自动进入公开列表，不要求人工审稿。来源摘录许可和全文许可各自保持原门禁，模型判断不授予转载权。

## 收紧的入口

- 中国政府采购网：中央公开招标列表中的标题或同一列表项上下文，必须同时出现警务任务／采购方线索和技术线索，才请求详情。只出现“数据”“平台”等宽词不再占用详情名额。
- NIST Information Technology、NIST Standards：RSS 标题或描述须明确出现 public safety、first responder、law enforcement、police、forensic、emergency communication、digital evidence、biometric 或 firefighter，才请求详情。活动页继续跳过。过滤数写入 `topic_filtered`；这是入口成本过滤，可能漏掉标题和摘要没有这些词的上游技术稿，不能视为模型质量结论。
- 其他 12 个入口的发现规则本轮未变；技术上采到的稿件仍由模型区分相关与否。

## 自动触发与失败诊断

在 `repo/backend` 中，对**已迁移的显式目标库**运行：

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.source_worker --execute --database-url sqlite:///D:/path/to/isolated.db --max-items 2 --retry-attempts 2 --report-dir data/source-worker
```

默认依次采现有 15 入口；`--source` 可以重复指定。`--cycles N --interval-seconds S` 可在一个进程内重复，且 N 限 1–32。Windows 任务计划程序可按需要定期触发同一命令；当前未注册系统任务。每次尝试分别写 `SourceRun`，报告含 robots/发现/详情诊断、请求路径与状态（不保存查询、请求头或响应体）、失败阶段与错误码、耗时、新增／修订／重复、正文状态与公开数。仅 `timeout`、`transport_error`、HTTP 500/502/503/504 做最多三次总尝试、指数退避；每次重走 robots 规则。robots 禁止、WAF/403/429 和解析失败不自动重试。

模型是单独显式开启的付费步骤：

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.source_worker --execute --database-url sqlite:///D:/path/to/isolated.db --max-items 2 --allow-paid-model --max-model-calls-total 4 --report-dir data/source-worker
```

先只读核验 `/models`，示例上限为每进程最多 **4 次外部调用**；后续五轴双评分接入后，相关稿通常需要 1 次分类加 2 次评分，详见[专项记录](dual-selection-scoring-2026-11-04.md)。正文不足 300 非空白字符的不调用模型。已保存结果会复用，断线未知结果不自动重发；输出不记录密钥。每轮按当前来源摘录权限重新投影已完成模型判断的材料，权限变化无需重新付费。这个上限只覆盖一次进程，不是跨进程预算服务。当前正式业务库来源为空，未启用定时采集；现有真实来源 `excerpt_allowed=false`，本轮没有更改或自动公开任何外站稿。

## 本轮证据

- 离线完整后端回归 **83 项通过**，覆盖受控重试、robots 禁止不重试、请求路径诊断、正文下限、NIST 过滤、许可变更后的无付费公开重投影和既有采集／公开行为。
- 在网络许可环境先分别只读预览：采购网列表 20 个链接、过滤后 0 个详情；NIST IT RSS 40 项、过滤 25 项、0 个详情；NIST Standards RSS 40 项、过滤 28 项、1 个详情正文。随后用新隔离库运行同三源一次：采购网和 NIST IT 为 `no_candidates`，NIST Standards 新增 1 篇 [法医遗传参考材料](https://www.nist.gov/news-events/news/2026/02/nist-releases-new-forensic-genetic-reference-material-help-crime)。每源一次尝试，模型调用 0，公开 0。逐源 JSON 和 SQLite 位于 Git 忽略目录 `backend/data/source-worker/2026-11-04-smoke/`。
- 同一隔离库追加 NIST Public Safety 限量触发：robots、RSS 和 1 条详情均成功，取得 6,266 字符正文并新增 1 篇；显式上限 1 次的真实模型调用实际 `applied=1`，判相关、评分 78。该稿原文标注日期在采集日之后，当前时间规则不会把它当作当日新稿；来源摘录许可仍关闭，所以状态为 `publication_hidden`、公开数 0。该次调用只证明单篇执行链，不校准模型准确率；原页为 [First Responders Foundation Models](https://www.nist.gov/news-events/news/2026/11/building-intelligence-first-responders-foundation-models-interoperable)。
- 对同一入口和隔离库再触发一次，记录 `duplicate=1`、既有 `applied` 回执 1、模型新调用 0，材料修订仍为 1。重试机制的故障路径由可控离线测试覆盖；这两次真实请求均一次成功，不能把它们当作真实网络重试成功证据。
- 这证明命令、过滤、诊断和单篇付费模型处理在限量运行中可用；0 个候选不等于站点故障，也不能据此断言收紧后的长期主题密度。三源过滤的漏选率、其余 12 源的真实自动调度、获许可后的真实稿自动公开和正式库运行仍待验证。
