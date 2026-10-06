# BluePulse 选稿标注指南 v1

本指南配合 [`bluepulse-execution-roadmap.md`](./bluepulse-execution-roadmap.md) 的 P1 使用。它是人工标注和评测的首版口径；当前采集模型提示已按下述边界收紧，并输出独立的精选候选判断。20 条样本的只读回放已可运行，结果见 [`selection-calibration-2026-10-01.md`](./selection-calibration-2026-10-01.md)；长期稳定的精选门槛与更大样本评测尚未完成。示例数据见 [`selection-gold.example.jsonl`](./selection-gold.example.jsonl)。

## 1. 两个判断分开做

先看**是否有实质性的警务科技关联**，再把相关内容归入七类主题，最后判断**是否值得精选**。七类是整理信息的栏目，不是七张独立的入场券：警务应用、AI 与大模型、公共安全技术装备、网络与数据安全、政策与标准、采购与项目、研究成果。大模型、智能体和无人机是重点方向，**不是替代七类的封闭清单**。范围包括科技在警务任务中的运用、试点和评估，直接规范这些技术的政策，以及具有具体能力变化和明确影响路径的重要上游技术进展（尤其中国和美国的模型与厂商动态）。不能只因采购方是公安机关、装备供警员使用，或一篇材料能归入“政策/研究”，就认定相关。低价值的相关资料可以进入全部动态；不相关资料不公开。正文缺失时只依据确实可见的标题/摘要判断，并记录证据不足，不根据网址、常识或模型记忆补写内容。

| `gold.relevance` | 判断标准 |
| --- | --- |
| `direct` | 明确涉及科技在警务任务中的运用或建设、具体技术研究与安全治理，或直接规范此类技术的政策；七类主题只用于随后分类。 |
| `potential` | 未必出现警务词，但属于可能影响警务科技的重要上游技术、模型、智能体、无人机、评估或治理进展；需说明**实际新信息及影响路径**，泛 AI 评论不算。 |
| `irrelevant` | 既无上述警务科技内容，也无值得追踪的上游进展；例如一般案件、人事消息、纯会议通稿、常规枪支弹药/防弹衣及其普通性能标准、缺少单项进展的跨年专利目录。 |
| `uncertain` | 原文/摘要不足以做出上述判断，暂不自动公开。 |

`gold.select` 使用 `select`、`reject` 或 `uncertain`。`select` 表示值得进入首页精选候选；它不表示技术效果已经得到验证。`irrelevant` 必须是 `reject`。`uncertain` 表示需要更多原文或人工复核。与七类主题有关但信息增量很少的资料可标 `direct` + `reject`。

首轮校准案例：04 跨年份专利目录为 `irrelevant`，因为不是一项可追踪的新技术进展；10、16 的常规防弹衣标准为 `irrelevant`，虽然可用“政策与标准”描述材料类型；13 的算法监控与隐私治理为 `direct` + `reject`，议题相关，但主要是印度法律框架讨论，并非重点地区新实施的科技政策。警务网络/视频系统的日常采购与运维可以是 `direct` + `reject`，相关不等于前沿或精选。若枪械或防护装备确有新的智能感知、计算、自主能力及明确警务用途，仍按实质技术内容逐案判断，不按物品名称机械排除。

## 2. “值得精选”的工作量表

对相关资料评估四项，总分 100；这只是编写判定理由的统一尺度，**门槛尚未确定**：

1. 主题与读者关联（0–30）：警务科技报道说明服务哪个任务；上游 AI 进展说明为何影响本平台关注的技术方向，而非只出现宽泛术语。
2. 信息增量（0–25）：是否有新能力、新结果、新规则或值得借鉴的方法。
3. 证据强度（0–25）：区分营销说法、官方宣布、实验结果和有条件的实际评估。
4. 实践可用性（0–20）：流程、规模、成本、约束、失败条件是否足以帮助读者判断。

原站发布时间用于排序，不混入价值分。官方公告可以证明“公告发布/试点启动”，不能自动证明“效果已验证”。摘要只写原文事实，推荐理由才写平台的分析判断；两者都不能加入原文没有的数据。

## 3. 固定字段与标注方式

标注文件为本地 JSONL，一行一个对象。`scripts/selection_dataset.py export` 只导出最少的来源、标题、原始链接、发布时间和内部文章 ID，不导出正文及当前模型处理状态；会按来源和处理状态均衡抽样。输出放在已忽略的 `backend/data/`，不要直接提交或外发；导出时会粗略遮盖标题中的邮箱、电话号码和身份证号，仍需人工复核其他可能的个人信息。标注时打开原站或已授权的内部材料查看正文。

`gold` 字段：

- `relevance`：`direct` / `potential` / `irrelevant` / `uncertain`。
- `select`：`select` / `reject` / `uncertain`。
- `primary_topic`：相关资料必须选一个现有七主题 slug；无关/不确定可填 `null`。已确认的无关样本若保留主题，仅用于记录材料类型，不意味着公开入库或推送。
- `content_kind`：`research`（技术研究）、`equipment`（产品装备）、`deployment`（落地案例）、`policy`（政策标准）、`industry`（行业动态）、`procurement`（采购/招标）；相关资料必须选一个。
- `evidence_level`：`marketing`、`announcement`、`lab_test`、`pilot_observation`、`field_evaluation` 或 `unknown`；这里描述**原文提供的证据**，不等于来源可信度。
- `reason`：一句话写与七类主题或重要上游技术进展的关联及精选/不精选原因；`potential` 必须写清新信息和影响路径。

至少保留 20% 的 `split=holdout` 条目不参与改提示词或调门槛。先由读者或领域人员独立标注难例；有分歧的条目复核后再定金标准。当前先试标 20 条（其中 5 条留出），从原 40 条中选出并保留已填写的部分标注；原 40 条及最初导出的 95 条均保留作备份。这批样本按旧的广义警务科技检索获得，含普通警务消息负例，但大模型、智能体、无人机和重要上游 AI 正例不足；它适合小规模试标，不能独自校准最终精选门槛。

## 4. Windows 使用方式

在 `backend` 目录运行：

```powershell
.\.venv\Scripts\python.exe -m scripts.selection_dataset export --output data/selection-candidates-20261001-v2.jsonl
.\.venv\Scripts\python.exe -m scripts.selection_dataset validate --input data/selection-candidates-20261001-v2.jsonl
```

`export` 只读本地 `data/bluepulse-dev.db`，若输出文件已存在则拒绝覆盖。`validate` 检查枚举、必填项、无关/精选冲突和重复案例 ID，并报告已标/待标数量；待标本身不是错误。可先对示例运行 `validate --input ../docs/selection-gold.example.jsonl` 了解完整格式。

首轮 20 条可以用本地网页标注。在 `backend` 目录运行：

```powershell
.\.venv\Scripts\python.exe -m scripts.selection_review
```

用浏览器打开终端显示的 `http://127.0.0.1:8765/`。页面每页显示 8 条原始标题、可用原文/摘要与原站链接，并展示单独保存的**建议摘要、依据类型、建议标签和理由**。建议来自当前可见材料，不是已确认事实；“仅依据标题”的摘要不会补写正文细节。已有人工值优先显示，并提示与建议的差异。修改下拉项即保存，一句话理由停止输入约 0.7 秒后保存；逐条核对后点击“确认本条”，才把页面上的完整标签计入“已复核”。未确认的建议不自动当作人工金标准。请勿同时启动多个标注服务或直接编辑 JSONL。服务仅监听本机 `127.0.0.1`；正式标注写入 `backend/data/selection-pilot-20.jsonl`，不会写入文章数据库。完成后检查：

```powershell
.\.venv\Scripts\python.exe -m scripts.selection_dataset validate --input data/selection-pilot-20.jsonl
```

该工具只准备样本和检查人工标签，不调用模型，也不把既有 `importance_score` 当作人工答案。已完成首轮标注后，可用 `python -m scripts.selection_eval --limit 15` 只读调用模型对照开发集；调整完规则后再用 `--split holdout --limit 5` 验证留出集。该回放不改数据库或人工金标准。若要将已确认标注用于旧文章，先备份数据库并运行迁移，再用 `python -m scripts.apply_selection_gold` 预览，确认范围后运行 `python -m scripts.apply_selection_gold --apply`；这一步仅写入人工覆盖字段，不修改标注 JSONL，也不会把未处理文章直接公开。
