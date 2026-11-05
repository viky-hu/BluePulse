# 五轴双评分实施与限量验证（2026-11-04）

本轮依据 `origin/main@898198b` 的《AIHOT 模型链路实施交接》和《标注指南 v2》实现当前 Python 后端的精选评分步骤。`D:/AIHOT` 原下载快照在本机已不存在，无法重新逐行核对原 `editorial/analyze.ts`、`industry/prompts/selection-score.md`；权重及双评分规则以该提交记录的源码复核结果为依据。实现保留机制并增加可核对的五轴输出，不能称为直接移植或 AIHOT 整体模型链路完成。

## 行为

1. 有至少 300 个非空白字符的正文才进入付费分类。相关且有中文摘要及至少一个七类主题的材料可以按原来源许可门禁进入文章库；是否精选另算。
2. 同材料 revision 使用同一评分提示词和输入，分别做评分 1、评分 2。两次请求身份使用不同的 `AnalysisAttempt.input_version` 后缀 `-r1`、`-r2`；发送前写 `started`，响应的五轴、类型、原始响应文本、usage 和 request ID 先提交，之后才写材料平均分与候选状态。若第 1 次已保存、第 2 次额度不足，下一轮只做第 2 次；`started/unknown` 不自动重发。
3. 五轴 `sig/nov/cred/reson/act` 各为 0–10 整数，内部类型为 `model_release/product_launch/tool_or_prompt/research_paper/industry_event/opinion_analysis/tutorial_explainer`。七行权重依标注指南 v2，分别为 `3/2/2/2/1`、`2/2/1/2/3`、`1/2/1/2/4`、`5/3/1/0/1`、`3/1/2/4/0`、`1/3/1/4/1`、`1/1/1/3/4`。服务端以权重乘五轴求单次 0–100 分，不信任模型自报总分。
4. 两分之和达到来源门槛的两倍才形成 `featured_candidate`，展示分为两分之和整除 2。任何单次成功、失败、unknown、同一 request ID 的两份响应都不形成候选。`Source.selection_threshold` 默认 `NULL`：两分完成后保存平均分和 `uncalibrated`，但不自动形成候选。当前尚无警务金标校准门槛，未把 AIHOT 的 60/65/76 直接用于生产。
5. 精选候选仍受当前归组完成、公开许可和去重门禁约束。旧单次模型候选在迁移时清零，历史回执保留；文章的相关分类公开资格不因精选评分未完而自动撤回。修订后重算两分，旧 revision 回执不覆盖新材料。

核心代码：[五轴计算与双回执](../backend/bluepulse_backend/selection_scoring.py)、[付费调用](../backend/bluepulse_backend/live_model.py)、[限量编排](../backend/bluepulse_backend/model_processing.py)、[升级迁移](../backend/migrations/versions/e31c8a41d2f0_dual_selection_scores.py)。`source_worker` 与 `source_collection --mode ingest-analyze` 共用该编排。模型评分输入仅有标题和实际正文，不带来源分级、门槛、旧分数或发表时间；原文里的命令按不可信数据处理。

## 验证

- 离线回归 **92 项通过**，含七类权重和、五轴类型边界、两份独立回执、临界值、额度中断后续做、unknown 不重发、未校准门槛、重复 request ID、材料修订后重算、真实 HTTP payload 不泄露密钥及分类加评分总调用上限。既有测试有一条 Starlette/httpx 兼容提示。
- 将 2026-11-04 的旧隔离 `source-worker` 库复制到 `backend/data/dual-score/2026-11-04-upgrade/` 后升级到 `e31c8a41d2f0`：2 篇材料和 1 条旧分析回执保留，模拟的旧单次精选候选及旧展示分清零；`alembic check` 无待升级差异。正式业务库未迁移或写入。
- 同一隔离库对已有的 [NIST First Responders 原页](https://www.nist.gov/news-events/news/2026/11/building-intelligence-first-responders-foundation-models-interoperable)显式允许**最多 2 次**真实评分调用。实际 2 次均 `applied`，request ID 不同，五轴均为 `7/7/5/8/5`，内部类型均为 `research_paper`，单次加权分均为 66，平均分 66；来源门槛为空，故 `selection_status=uncalibrated`、`featured_candidate=false`。原采正文 6,266 字符，本次评分输入为开头 4,200 字符，不能据此认为模型读过全文。此稿原有分类回执 1 次，来源许可仍关闭，公开数 0。逐源报告与 SQLite 位于上述 Git 忽略目录；未输出密钥。

本次只是单篇执行验证，不能证明五轴分数准确或双评分能提高选稿质量。当前模型 temperature=0，同篇两次确实得到相同分数；独立请求与回执已验证，评分差异性未由此证明。来源门槛、100–200 条领域金标、预筛与事实结构化、归组、跨进程预算和管理员处置仍属后续工作。
