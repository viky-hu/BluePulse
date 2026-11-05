# 15 源实时端到端限量测试（2026-11-03）

本轮从现有 15 个采集入口实时联网，每入口最多取 2 条，在全新隔离库完成入库、同批重放去重、少量真实模型分类及匿名 API 检查。原始结构化证据保存在 Git 忽略目录 `backend/data/live-end-to-end/2026-11-03-formal/` 的 `result.json`、`source-items.json`、`source-retry-europol-news-*.json` 和 `live-test.db`。这是一轮限量样本，不构成跨日期稳定性结论，也不代表 30 条均完成模型分类或选稿审核。

## 结果与判定

| 环节 | 已证实的本轮结果 | 边界 |
| --- | --- | --- |
| 来源与采集 | 15 个来源均在隔离库登记；首轮 14/15 入口成功，每个成功入口详情尝试 2、成功 2。Europol 首轮在 `/robots.txt` 阶段 `transport_error`，同规则单源复测成功 2/2。最终取得 30 条 | 不绕过 robots、WAF 或访问限制；复测成功不抹去首轮故障 |
| 正文与日期 | 30 条中 `full_text` 29、`abstract_only` 1；30 条有原始发布日期；本轮已解析详情均无已知长度上限截断 | GOV.UK 一条带附件的 publication 只有薄落地页正文，附件未并入证据；`full_text` 不等于证据充分或适合选稿 |
| 入库与去重 | 首次 30 条新增；相同候选在同库重放均记为重复，材料仍为 30；本批不同 URL 的高置信镜像为 0 | 只说明本批样本；跨 URL 去重规则的更多边界见[专项验证](dedup-freshness-2026-11-03.md) |
| 真实模型 | 显式上限 4 次，预检通过，4 次均有已应用回执。HTX、NIST Public Safety 判相关，采购网样本判不相关；GOV.UK 薄附件落地页判主题相关 | 其余 26 条未调用模型；模型的主题判断不能替代正文证据和来源许可。不得据 4 条推断全站主题密度 |
| 匿名 API | taxonomy 7、sources 15；真实材料公开列表 0、时间线卡片 0 | 来源默认公开许可未开启，真实样本没有自动公开；正式业务库未写入 |
| 前端显示 | 使用另一独立库中的**显式合成许可样本**，本地浏览器实际看到 `/articles?period=all&topic=practice` 列表、文章详情和 `/all?topic=practice` 时间线卡片；页面及代理请求 HTTP 200 | 证明有许可数据可从 API 到页面展示；不等于真实来源文章获准公开。首页精选、事件归组与热点仍无数据生产链路 |

### 逐源采集记录

表中“详情”是本轮详情请求尝试/解析成功；“正文”是 `full_text`/摘要级；日期为有原始发布日期的条数。链接是本轮实际取得的一条原页，不代表推荐选稿。各源完整请求状态、耗时、两条 URL、正文长度及重放结果见 `result.json` 和 `source-items.json`。除单列的 Europol 首轮故障，已解析详情均无详情失败；初次入库各新增 2、同批重放各重复 2。入口发现数因 RSS、列表、搜索的口径不同，以原始记录的 `diagnostics` 为准。

| 入口 | 详情 | 正文 | 日期 | 状态与本轮原页 |
| --- | ---: | ---: | ---: | --- |
| GOV.UK | 2/2 | 1/1 | 2/2 | [面部识别部署记录](https://www.gov.uk/government/publications/live-facial-recognition-deployment-records)；附件证据未取 |
| 中国政府采购网 | 2/2 | 2/0 | 2/2 | [采购公告](https://www.ccgp.gov.cn/cggg/zygg/gkzb/202611/t20261103_27614158.htm)；robots 404，依既有许可门禁限量读取 |
| NIST Public Safety | 2/2 | 2/0 | 2/2 | [5G sidelink 原页](https://www.nist.gov/news-events/news/2026/09/enhancing-public-safety-communication-reliability-through-5g-sidelink) |
| NIST Forensic Science | 2/2 | 2/0 | 2/2 | [指纹研究原页](https://www.nist.gov/news-events/news/2026/09/spotlight-closer-look-fingerprint-landscape) |
| NIST Information Technology | 2/2 | 2/0 | 2/2 | [联邦学习测试床原页](https://www.nist.gov/news-events/news/2026/10/privacy-preserving-federated-learning-ppfl-testbed-and-curated-dataset) |
| NIST Standards | 2/2 | 2/0 | 2/2 | [天线校准原页](https://www.nist.gov/news-events/news/2026/10/nist-ctl-announces-new-low-uncertainty-broadband-antenna-gain-calibrations) |
| HTX News | 2/2 | 2/0 | 2/2 | [Home Team 架构原页](https://www.htx.gov.sg/whats-happening/all-news---events/all-news/2026/htxplains-how-common-architecture-will-help-enhance-the-home-team) |
| Police Science | 2/2 | 2/0 | 2/2 | [研究基金原页](https://science.police.uk/news-and-events/news/police-star-fund-27-28-expression-of-interest-now-open/)；robots 自重定向后按既有规则读取 |
| NPCC | 2/2 | 2/0 | 2/2 | [刀具犯罪中心原页](https://news.npcc.police.uk/releases/national-knife-crime-centre-marks-six-months-of-action) |
| 江苏公安 | 2/2 | 2/0 | 2/2 | [警务动态原页](https://gat.jiangsu.gov.cn/art/2026/10/30/art_6372_11852488.html) |
| Police Digital Service | 2/2 | 2/0 | 2/2 | [网络安全报告原页](https://pds.police.uk/police-digital-service-welcomes-hmicfrs-cyber-report/) |
| Biometric Update | 2/2 | 2/0 | 2/2 | [面部识别原页](https://www.biometricupdate.com/202610/uk-facial-recognition-rollout-widens-as-police-oversight-rules-take-shape) |
| StateScoop | 2/2 | 2/0 | 2/2 | [面部识别旧稿原页](https://statescoop.com/florida-man-aclu-sue-police-after-wrongful-arrest-using-facial-recognition-tech/)；须按原始日期判新旧，不把本轮发现当新稿 |
| Singapore Police Force Police Life | 2/2 | 2/0 | 2/2 | [来电识别原页](https://www.police.gov.sg/Media-Hub/Police-Life/2026/11/Know-Whos-Calling-SPF-Launches-Single-Caller-ID-to-Combat-Scams) |
| Europol Newsroom | 首轮 0/0；复测 2/2 | 2/0 | 2/2 | 首轮 robots `transport_error`，复测 robots/入口/详情均 200；[原页](https://www.europol.europa.eu/media-press/newsroom/news/5th-empact-hackathon-leads-to-detection-of-51-potential-victims) |

## 本轮补足的技术链路

- 增加 `GET /api/v1/site/timeline`，向前端 `/all` 提供真实公开材料的近 30 日列表、筛选、分页和按上海日期分组；无精选、事件组或热点时明确返回空值。
- 增加有明确 `--execute`、每源最多 2 条、模型最多 4 次的 `live_end_to_end` 命令；它自动创建隔离数据库，登记全部 15 源，逐源保留请求诊断，并对首轮失败的单源支持同规则复测。来源公开许可保持关闭。
- 增加该批处理和时间线 API 的测试。前端 ESLint 仅检查前端范围，跳过 `backend/**` 的 Python 缓存。`pnpm run lint`、`pnpm run build` 和后端 66 项测试通过。

## 复跑与剩余判定

在 `repo/backend` 下，使用新的空输出目录；命令不写默认 `data/bluepulse.db`。不需模型付费时去掉 `--allow-paid-model` 并将 `--max-model-calls 0`。

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.live_end_to_end --execute --allow-paid-model --max-items 2 --max-model-calls 4 --output-dir data/live-end-to-end/next-run
```

若某源出现请求阶段故障，保留首轮证据，并在相同目录复测该源（示例）：

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.live_end_to_end --execute --retry-source europol-news --output-dir data/live-end-to-end/next-run
```

真实稿能否进入公开列表，仍需对目标来源确认转载/摘录许可、对具体正文与日期做证据复核，并明确公开决策。GOV.UK 附件正文、旧稿拦截的跨期表现、各源主题密度和 NPCC/江苏/Biometric Update/Europol 的间歇故障仍需后续样本复查；本轮 15 × 2 不能证明持续稳定。当前已证实的是实时采集至隐藏材料、限量分类、去重与匿名接口的处理链，以及用合成许可数据完成的真实浏览器展示链；**真实来源稿件从采集到公开展示尚未完成**。
