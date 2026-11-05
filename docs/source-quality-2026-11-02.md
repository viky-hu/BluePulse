# 15 个采集入口的主题质量抽查（2026-11-02）

本报告接续 [15 源台账](source-validation-ledger-2026-11-01.md)及[首轮稳定性与正文质量记录](source-validation-baseline-2026-11-01.md)。2026-11-01 至 11-02 的受控采集共留下 **60 个不同的“入口 × URL”样本**，逐篇人工阅读已提取文字并标注主题；其中 **16 篇**还保存或核对了原页面。15 个入口分布在 12 个主机上。数据、逐篇 URL 和标注位于本地 Git 忽略目录 `backend/data/source-validation/source-quality-2026-11-02.{csv,json}` 及同目录 `review-*.json`。没有调用模型、写正式业务库或公开文章。

## 判断口径

- **直接符合（direct）**：正文明确描述警务、执法、刑事取证或一线公共安全任务中的技术、产品、制度实践及其可核实结果。泛技术、泛网络安全、机构新闻，即使有潜在警务用途，也不自动计入。
- **相邻（adjacent）**：与警务科技有明确可解释的联系，但本页缺少具体警务应用或技术实质；报告目录、会议/基金通知和一般网络犯罪行动可落在这里。
- **偏离（off）**：现有正文足以确认与所需主题无关，例如一般采购、党建、非警务科研。正文足以*拒稿*仍可记“证据足够”，因此该字段与直接符合分开。
- **证据足够**：当前提取正文足以判断相关事实的边界；关键事实只在附件、外链报告或第三方原件时记否。**选稿符合**进一步要求时间、新闻价值、事实实质和归属；这只是人工待审候选，不代表可发布。
- 表内“直接密度”的分母仅为**已人工标注的不同入口 × URL 样本**。样本是现有列表/RSS 的靠前条目或关键词排序结果，数量不等且非随机；它不是全站密度、未来供稿率或真实入选率。无新稿与采集故障分别记录。11-02 的两轮较大抽样有 5 个入口连续在网络阶段失败，它们沿用 11-01 的 2 条样本，不能据此判为内容质量下降。

## 逐源样本结果

“充分”仅在直接符合的文章中计数；“近 60 日”是截至 11-02、原始发布日期不晚于当天的直接符合篇数。“选稿”指本轮初筛。每行链接指向可复核原文，完整 60 条 URL 见上述 JSON。

| 入口与原文例子 | 已评 | 直接 / 相邻 / 偏离 | 直接密度 | 直接且充分 | 近 60 日直接 | 选稿 | 本轮质量判断 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| [GOV.UK 部署记录](https://www.gov.uk/government/publications/live-facial-recognition-deployment-records) | 2 | 2 / 0 / 0 | 2/2 | 0 | 0 | 0 | 主题命中，但 collection/附件落地页没有承载关键证据；附件获取与解析仍缺。 |
| [中国政府采购网公告](https://www.ccgp.gov.cn/cggg/zygg/gkzb/202611/t20261102_27605755.htm) | 7 | 0 / 0 / 7 | 0/7 | 0 | 0 | 0 | 此中央公开招标入口靠前样本是高校、科研/工业采购；关键词有“数据/平台”误召回。只说明此入口样本低密度。 |
| [NIST Public Safety：5G sidelink](https://www.nist.gov/news-events/news/2026/09/enhancing-public-safety-communication-reliability-through-5g-sidelink) | 5 | 4 / 1 / 0 | 4/5 | 4 | 2 | 2 | 实质技术材料较多；一篇 [11-05 未来日期条目](https://www.nist.gov/news-events/news/2026/11/building-intelligence-first-responders-foundation-models-interoperable) 不进入当日新稿。 |
| [NIST Forensic：指纹数据软件](https://www.nist.gov/news-events/news/2026/03/nist-helps-fingerprint-examiners-new-data-and-software-release) | 5 | 3 / 1 / 1 | 3/5 | 3 | 1 | 1 | 有取证技术，但旧稿、短 Spotlight 和非警务实验混合；芬太尼研究与 Public Safety 栏目重叠。 |
| [NIST IT：联邦学习测试床](https://www.nist.gov/news-events/news/2026/10/privacy-preserving-federated-learning-ppfl-testbed-and-curated-dataset) | 5 | 0 / 3 / 2 | 0/5 | 0 | 0 | 0 | 技术内容存在，样本没有警务落地证据；不可把源目录标签当成正文主题。 |
| [NIST Standards：天线校准](https://www.nist.gov/news-events/news/2026/10/nist-ctl-announces-new-low-uncertainty-broadband-antenna-gain-calibrations) | 5 | 0 / 1 / 4 | 0/5 | 0 | 0 | 0 | 泛标准、器件和政策公告为主；现阶段低优先级人工选稿。 |
| [HTX：AI 运维](https://www.htx.gov.sg/whats-happening/all-news---events/all-news/2026/leveraging-ai-to-reimagine-day-2-ops) | 2 | 2 / 0 / 0 | 2/2 | 2 | 2 | 2 | 两篇有 Home Team 技术场景，但仅 2 篇，密度尚不能外推。 |
| [Police Science：杂志介绍](https://science.police.uk/news-and-events/news/the-fourth-edition-of-policing-tomorrow-is-now-available/) | 2 | 0 / 2 / 0 | 0/2 | 0 | 0 | 0 | 杂志/基金通知只提供入口或导语；需看目标内容，不能按正文完整新闻计。 |
| [NPCC：AI 在线报案试点](https://news.npcc.police.uk/releases/policings-first-ai-online-crime-reporting-test-goes-live) | 5 | 1 / 1 / 3 | 1/5 | 1 | 1 | 1 | 发现确有实质 AI 警务试点；常规警务新闻占多数。历史偶发请求故障另按稳定性统计。 |
| [江苏公安：转载稿](https://gat.jiangsu.gov.cn/art/2026/10/30/art_6372_11852488.html) | 2 | 0 / 0 / 2 | 0/2 | 0 | 0 | 0 | 本轮为党建/服务内容；原页“信息来源：人民公安报”须保留转载归属。样本太少。 |
| [PDS：网络安全报告回应](https://pds.police.uk/police-digital-service-welcomes-hmicfrs-cyber-report/) | 5 | 1 / 3 / 1 | 1/5 | 0 | 1 | 0 | 报告回应缺关键报告证据，峰会/奖项通稿多；与 NPCC 的奖项稿标题重复。 |
| [Biometric Update：英国人脸识别部署](https://www.biometricupdate.com/202610/uk-facial-recognition-rollout-widens-as-police-oversight-rules-take-shape) | 5 | 3 / 2 / 0 | 3/5 | 1 | 3 | 1 | 主题命中较多，但 2 篇直接相关稿仍要一手材料核对，媒体报道不可替代警方/合同原件。 |
| [StateScoop：警察报告 AI 工具](https://statescoop.com/gen-ai-police-report-transparency-oversight-eff/) | 4 | 3 / 1 / 0 | 3/4 | 2 | 0 | 0 | 主题集中但 4 篇均旧于 60 日；RSS 发现也只有 4 项。供稿稀疏/旧稿，不是正文采集失败。 |
| [Europol：黑客马拉松](https://www.europol.europa.eu/media-press/newsroom/news/5th-empact-hackathon-leads-to-detection-of-51-potential-victims) | 4 | 2 / 2 / 0 | 2/4 | 1 | 2 | 1 | 官方行动成果可用；电子证据报告的新闻概述不足以代替报告全文。 |
| [SPF Police Life：统一来电显示](https://www.police.gov.sg/Media-Hub/Police-Life/2026/11/Know-Whos-Calling-SPF-Launches-Single-Caller-ID-to-Combat-Scams) | 2 | 1 / 1 / 0 | 1/2 | 1 | 1 | 1 | 防诈技术实践有细节，另一篇人物故事仅相邻；样本很少。 |
| **合计** | **60** | **22 / 18 / 20** | **22/60（36.7%）** | **15/22** | **13** | **9/60** | 60 个入口样本对应 59 个跨入口不同 URL。 |

NIST 的[芬太尼研究](https://www.nist.gov/news-events/news/2026/10/nist-study-shows-how-toxic-substances-mixed-fentanyl-vary-across-us-and)同时出现在 Public Safety 与 Forensic Science，故 22 个“直接”中有一篇跨入口重复；按全局 URL 去重为 **21/59** 直接、**8/59** 选稿。NPCC 与 PDS 的奖项稿同标题但 URL 不同，仍应作为可能的转载/同稿重复人工核对。NIST 四个栏目同主机、同 RSS 体系，不构成四个独立供给渠道。

## 已证实、单次推断和待验证

已证实的是：上述 URL 的本地采集结果、60 条人工主题标签、16 条原页核对记录；GOV.UK 样本的关键证据位于附件/下级文件；StateScoop 的 4 条样本日期均超过 60 日；NIST 跨栏目确有同 URL 重复。11-01 的原页/正文对照见前述基线文档，部分长页面仍未证明中段逐段完整。

**单次样本推断**是各源的直接密度、选稿产出和优先级：优先继续观察 NIST Public Safety/Forensic、HTX、NPCC、Biometric Update、Europol、SPF 的直接且证据足够新稿；GOV.UK 先解决附件证据；CCGP 当前中央招标入口、NIST IT/Standards 的误召回和泛技术稿，宜先调整现有筛选及复核策略；StateScoop 监测新稿供给，不把旧稿比例视为抓取错误。这里没有据 2–7 篇样本淘汰任何入口。

**待验证**的是各入口跨日期可用率、最近 14 天的新 URL 数和主题密度、媒体一手归属、外链报告/附件完整性，以及是否因同站栏目和转载造成独立信息增量偏低。约连续观察 14 天，每日固定 `--max-items 2`；每周对低密度入口作一次显式 `--quality-sample --max-items 5` 抽查即可，避免把单日靠前样本反复计作新增。每源同时记录：成功运行日数/尝试日数、新增且非未来日期的不同 URL、其中直接相关数、直接且证据足够数、近期可选稿数、同站/跨站同稿数。建议至少有 **20 个不同 URL、覆盖 7 个不同采集日**才给出暂定主题密度；不足者报告区间内的真实计数与“样本不足”，尤其是 StateScoop。可用率须另以独立日和失败阶段评价；供稿为零时写“无新增稿”。

## 可复跑命令

在 `repo/backend` 下运行。`source_validation` 默认仍限制每入口最多 2 篇；5 篇抽样必须显式加 `--quality-sample`，保持现有 robots、主机与访问门禁。完成 `review-*.json` 的 `topic_fit`、`evidence_sufficient`、`editorial_fit` 人工标注后再汇总；`page_checked` 仅对照原页面时置真。

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.source_validation --max-items 2 --execute
.\.venv\Scripts\python.exe -m bluepulse_backend.source_validation --source npcc --max-items 5 --quality-sample --execute
.\.venv\Scripts\python.exe -m bluepulse_backend.source_quality_summary --as-of 2026-11-02 --run-from 2026-11-01 --run-to 2026-11-02 --new-only --output-csv data/source-validation/source-quality-2026-11-02.csv --output-json data/source-validation/source-quality-2026-11-02.json
```

更改日期区间即可取得逐日或滚动观察值；`--new-only` 用归档中的首次发现日排除此前采过的 URL，因此需保留历史基线。汇总程序按来源与规范化 URL 去重，保留跨栏目重叠提示。原始标注与证据文件仅本地保存，不调整现有来源许可和公开门禁。
