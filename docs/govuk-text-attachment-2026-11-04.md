# GOV.UK 文字附件提取复测（2026-11-04）

## 改动

`GovUkAdapter` 在原有 Search API → Content API 限量路径上，遇到有附件的 publication 时，最多额外读取一份**同站英文 HTML 可访问版本**。请求继续走 `BoundedHTTP` 的 HTTPS 主机、响应大小、超时和禁止重定向限制；`source_validation` 的 robots 请求门禁也覆盖附件 URL。只读 `details.body`，不解析页面导航；HTML 表格转为保留行列分隔的文本。候选稿保留落地页 URL 作为原文链接，另将实际正文所在的附件 URL 存入 `body_source_url`，材料修订及详情 API 也保留该出处。附件读取失败时，短落地页仍为摘要级，并在逐项诊断中留下错误码。未改变来源许可或自动公开规则。

只取首个英文 HTML 附件和首个英文 CSV；跳过威尔士语版本、PDF、图片、视频和其他文件。HTML 附件限制在 GOV.UK 同站 `/government/` 路径；CSV 限制在官方 `assets.publishing.service.gov.uk/media/`，对资产主机单独检查 robots，使用 HTTPS、20 秒超时、300 KB 上限和禁止跳转的 Python 标准库请求。若只有 CSV 可用，保留表头与数据行后作为正文，并记录 CSV 为 `body_source_url`；若 HTML 已可用，则逐项比较两份表格，不把重复内容拼入正文。`csv_matched_html` / `csv_mismatched_html` 进入来源运行诊断，逐项结果保留 CSV URL、行数、robots 状态与错误码。网络传输错误最多重试一次，robots 禁止或 HTTP 错误不会重试。

## 实测证据

在新隔离库运行（`repo/backend`）：

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.source_validation --source govuk --max-items 2 --execute --output-dir data/source-validation/govuk-attachments-2026-11-04-final-v2
```

证据在 Git 忽略目录 `backend/data/source-validation/govuk-attachments-2026-11-04-final-v2/` 的 `baseline-*.json`、`observation.db`。本轮 robots、搜索入口、两条详情及一条英文 HTML 附件均返回 200；两条详情均解析成功，附件尝试 1、成功 1。先前只有 120 字符落地页导语的[部署记录](https://www.gov.uk/government/publications/live-facial-recognition-deployment-records)，现从[英文 HTML 附件](https://www.gov.uk/government/publications/live-facial-recognition-deployment-records/live-facial-recognition-deployment-in-november-2025-accessible)取得 **2,073 字符**：1 行表头加 18 行部署数据，行列分隔保留，没有 GOV.UK 导航或推荐内容。另一条 collection 页仍为 609 字符正文。隔离库首次新增 2、原样重放重复 2；材料数 2、公开数 **0**。旧 30 条材料隔离库的只读副本升级到新迁移后仍为 30 条，新字段可读；正式业务库未迁移或写入。

## CSV 复测

同日对资产主机的直接诊断发现：`httpx` 在 TLS 握手时 `UNEXPECTED_EOF_WHILE_READING`，系统 curl 与 Python 标准库均可取得约 1.6 KB 英文 CSV。因此适配器新增独立的标准库文字资产请求路径，并在请求 CSV 前单独检查该主机 robots。首次适配器运行在 robots 预检阶段遇到一次 `transport_error`，记录于 `backend/data/source-validation/govuk-csv-2026-11-04/baseline-2026-11-04T160234+0800.json`。同一隔离观察库复测见 `baseline-2026-11-04T160401+0800.json`：robots 返回 404，依既有“规则文件不可用”口径继续限量读取；CSV 取得并解析 **18 行**，与已取得 HTML 的 18 行**逐项相同**。同库重放两条 URL 均为重复，材料未增加，公开数仍为 **0**。

这证明本轮英文 CSV 已可采，且与本轮 HTML 版本的数据行一致。落地页首次发布于 2026-01-09、更新于 2026-10-15；两份附件本轮可见的最后一行都是 2026-02-26。页面更新原因及是否还有其他未列出的近期部署，**不能仅凭附件行数推断**；具体选稿仍需检查日期与事实锚点。威尔士语 CSV、PDF 与多媒体不在本轮范围。

随后一次完整入口复跑在 GOV.UK `/robots.txt` 阶段 `timeout`，没有进入搜索或附件，记录于同一目录的 `baseline-2026-11-04T160709+0800.json`。此失败属于入口网络阶段，不能算 CSV 解析失败；本次成功也不能证明持续可用。

针对性测试覆盖英文 HTML/CSV 选取、威尔士语和异站文件跳过、CSV 两层表头、表格行列保留、CSV 回退正文、附件失败回退摘要、编码路径穿越拒绝、robots 禁止附件时不请求，以及一次传输错误重试；完整后端测试结果以本轮回归为准。
