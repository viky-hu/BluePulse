# 首批可审稿件闭环试运行（2026-11-03）

从[首批候选清单](first-editorial-batch-2026-11-03.md)取 4 篇官方原文，使用已留存的采集基线和主题初筛记录，执行“候选选择 → 证据段落定位 → 隔离入库及重放去重 → 版本绑定审阅表 → 初审决定记录”。过程未发网络采集请求、未调用模型、未写正式业务库、未改变来源许可或公开文章。`advance` 只表示进入下一步内部编辑，**不是用户最终选稿批准或发布资格**。

## 本轮实测结果

| 原文 | 初审决定 | 已核对的依据与边界 |
| --- | --- | --- |
| [SPF：统一外拨来电显示](https://www.police.gov.sg/Media-Hub/Police-Life/2026/11/Know-Whos-Calling-SPF-Launches-Single-Caller-ID-to-Combat-Scams)，11-01 | advance | 官方原页与已采正文的三处关键段落一致：11-02 起启用、来电后官方短信、号码只用于外拨；不能声称防诈效果已实证。 |
| [HTX：VendorPulse AI 运维](https://www.htx.gov.sg/whats-happening/all-news---events/all-news/2026/leveraging-ai-to-reimagine-day-2-ops)，10-29 | advance | 官方原页确认读取报告图表/文字与概念验证阶段；工时效益是机构预期。 |
| [HTX：通用船舶与车辆架构](https://www.htx.gov.sg/whats-happening/all-news---events/all-news/2026/htxplains-how-common-architecture-will-help-enhance-the-home-team)，10-28 | hold | 采集正文包含项目与架构证据锚点，但本轮官方原页重访超时；还须核对原页和 Home Team 跨部门归属。访问超时不当作文章无效。 |
| [NPCC：Citizen Assist AI 报案试点](https://news.npcc.police.uk/releases/policings-first-ai-online-crime-reporting-test-goes-live)，09-25 | advance | 官方原页确认剑桥郡警方试点、结构化报案及初期限定的报案路径；适合作为案例，不写成全面部署或当日快讯。 |

本地独立数据库 `backend/data/editorial-pilot/first-batch/editorial-pilot.db` 有 **4 材料、4 修订**；首次导入 **4 new**，同批快照重放 **4 duplicate**。4 篇均为 `analysis_pending`、`public=false`；3 个来源的 `excerpt_allowed` 和 `full_text_allowed` 均为 false。审阅结果为 **advance 3、hold 1、reject 0、pending 0、公开 0**；按入口为 SPF 1/1 advance、HTX 1/2 advance、NPCC 1/1 advance。这里的分母只是定向选出的 4 篇，不能当作来源整体入选率。这是离线重放去重及内部初审流程的实测，不是第二轮网络采集，也不能证明正式发布链路。

## 可复查文件与约束

- 选择配置：[editorial-pilot-4.json](../backend/config/editorial-pilot-4.json)；流程代码：[editorial_pilot.py](../backend/bluepulse_backend/editorial_pilot.py)。每项事实给出原文中的定位短语，准备时必须在正文找到相应段落。
- 本地 Git 忽略目录 `backend/data/editorial-pilot/first-batch/` 保存 `packet.json`（含私用提取正文、原始 URL、来源日期、证据段落、材料 ID/修订/内容哈希）、`review-template.json`、`review-first-pass.json` 与带时间戳的 `review-result-*.json`。不要把包中的全文公开或提交到 Git。
- `record` 核对每条材料的规范化 URL、修订、内容哈希及来源许可；`advance` 要求复核者填写身份，并将原页与所有配置事实标为已核对。修订改变、遗漏或错误的事实检查会被拒绝；记录决定后不会调用模型或修改材料 `public`。
- 本轮为 Codex 的**初审建议**，其中 3 篇进入下一步内部编辑；人工最终采用、可摘录范围及是否公开仍待用户/编辑确认。现有前端可兼容旧文章详情，但这 4 篇尚不在正式库，前端普通模式不会显示。

从 `repo/backend` 重复运行时使用新的空 `--output-dir`，命令见[后端 README](../backend/README.md#首批内部选稿试运行)。可以编辑模板后运行 `record` 记录复核者的新决定；每次结果单独留档。全量自动化测试也覆盖离线导入与重放、非公开门禁、证据必填及修订过期拒绝。
