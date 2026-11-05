# 15 源首轮稳定性与正文质量记录

基线在 **2026-11-01（北京时间）**以每入口最多 2 条详情执行；2026-11-02 又做了首次跨日观察。本文件只把 11-01 当作首轮基线，11-02 仅为第二个观察日，**尚不能证明跨日期稳定**。采集入口有 15 个、网站主机 12 个。运行原始 JSON、每源首篇的原响应、人工复核模板及隔离 SQLite 位于 Git 忽略的 `backend/data/source-validation/`；入口台账见 [15 源台账](source-validation-ledger-2026-11-01.md)。没有调用模型，没有写正式业务库或公开文章。

## 计数口径

“发现”是当前适配器报告的列表唯一链接数、RSS item 数、sitemap 新闻 URL 数或搜索返回数，依入口标明；不是全站文章数。“详情成功”指适配器返回候选，`full_text` 是有非空正文字段的技术状态，**不等于正文完整或事实足够**。日期覆盖为候选含 `published_at` 或 `published_date`。`正文长度`为字符数，斜线分隔两篇。首轮每个成功入口在独立隔离库重放同一快照，得到 `new=2`、第二次 `duplicate=2`、`revised=0`；这是去重机制验证，不是两次网络采集。各源单篇末尾均未正好撞到当前 12,000/100,000 字上限，但仍需继续监测中段漏取。

11-01 多次同日受控运行是为记录间歇故障及留存原页，各来源运行次数不等，不宜把成功次数比值当作长期可用率。下表以**最后一次成功运行**的发现和正文数字为主，同时保留同日失败次数。每源两个候选均有原始日期字段，候选 URL 无重复；NIST 四个 RSS 的跨栏目重复另述。

| 入口及抽查原文 | 11-01 robots／发现 | 运行成功/总数；详情成功/尝试；正文状态 | 字符数；耗时 | 同日失败阶段与代码 |
| --- | --- | --- | --- | --- |
| [GOV.UK](https://www.gov.uk/government/publications/live-facial-recognition-deployment-records) | 200；Search 4 | 3/3；2/2；全文 1、摘要 1 | 609/0；2.45 秒 | 无；4 个附件的落地页仅 120 字导语 |
| [采购网](https://www.ccgp.gov.cn/cggg/zygg/gkzb/202611/t20261101_27598681.htm) | robots 404；列表 20 | 2/3；2/2；全文 2 | 约 1,650/1,540；10.28 秒 | 1 次 `/robots.txt` `transport_error`，未进列表 |
| [NIST Public Safety](https://www.nist.gov/news-events/news/2026/11/building-intelligence-first-responders-foundation-models-interoperable) | 200；RSS 40 | 4/4；2/2；全文 2 | 6,266/4,869；3.13 秒 | 无；首篇标注 11-05 未来日期 |
| [NIST Forensic](https://www.nist.gov/news-events/news/2026/09/spotlight-closer-look-fingerprint-landscape) | 200；RSS 40 | 4/4；2/2；全文 2 | 823/767；3.26 秒 | 无；详情前跳过 1 活动页 |
| [NIST IT](https://www.nist.gov/news-events/news/2026/10/privacy-preserving-federated-learning-ppfl-testbed-and-curated-dataset) | 200；RSS 40 | 4/4；2/2；全文 2 | 2,854/1,572；3.48 秒 | 无；详情前跳过 2 活动页 |
| [NIST Standards](https://www.nist.gov/news-events/news/2026/10/nist-ctl-announces-new-low-uncertainty-broadband-antenna-gain-calibrations) | 200；RSS 40 | 4/4；2/2；全文 2 | 3,010/2,071；3.61 秒 | 无 |
| [HTX](https://www.htx.gov.sg/whats-happening/all-news---events/all-news/2026/leveraging-ai-to-reimagine-day-2-ops) | 200；JSON 首页面 12 | 3/3；2/2；全文 2 | 6,476/5,773；11.12 秒 | 无；页面只有日期，已修正精度 |
| [Police Science](https://science.police.uk/news-and-events/news/the-fourth-edition-of-policing-tomorrow-is-now-available/) | robots 301 自重定向；sitemap 新闻 63 | 2/2；2/2；全文 2 | 726/1,690；10.38 秒 | 按适配器的受控自重定向例外继续；无详情失败 |
| [NPCC](https://news.npcc.police.uk/releases/infected-blood-inquiry-police-review-update-oct-26) | 200；列表 12 | 3/4；2/2；全文 2 | 3,875/2,979；7.57 秒 | 1 次 `/robots.txt` `transport_error` |
| [江苏公安](https://gat.jiangsu.gov.cn/art/2026/10/30/art_6372_11852488.html) | 200；列表 45 | 2/2；2/2；全文 2 | 1,754/892；9.62 秒 | 无；首篇原页标注“信息来源：人民公安报” |
| [PDS](https://pds.police.uk/police-digital-service-welcomes-hmicfrs-cyber-report/) | 200；列表 49 | 2/3；2/2；全文 2 | 1,472/3,003；8.96 秒 | 1 次 `/robots.txt` `transport_error` |
| [Biometric Update](https://www.biometricupdate.com/202610/uk-facial-recognition-rollout-widens-as-police-oversight-rules-take-shape) | 200；栏目 10 | 2/2；2/2；全文 2 | 7,076/12,261；6.78 秒 | 本日无失败；10-29 曾在列表前超时 |
| [StateScoop](https://statescoop.com/florida-man-aclu-sue-police-after-wrongful-arrest-using-facial-recognition-tech/) | 200；RSS 4 | 2/3；2/2；全文 2 | 4,675/2,881；5.76 秒 | 1 次 `/robots.txt` `transport_error`；两稿均为旧稿 |
| [Europol](https://www.europol.europa.eu/media-press/newsroom/news/5th-empact-hackathon-leads-to-detection-of-51-potential-victims) | 200；RSS 10，技术词 4 | 2/3；2/2；全文 2 | 4,964/4,136；7.43 秒 | 首次 `/robots.txt` `transport_error` |
| [SPF Police Life](https://www.police.gov.sg/Media-Hub/Police-Life/2026/11/Know-Whos-Calling-SPF-Launches-Single-Caller-ID-to-Combat-Scams) | 200；列表 17，技术词 4 | 2/2；2/2；全文 2 | 3,377/5,789；5.39 秒 | 无；页面只有日期 |

11-01 **15/15 入口至少一次取得详情**；成功运行的发现入口 HTTP 状态均为 200。选定的 30 个详情中 29 个有正文、1 个仅有摘要；五个入口出现过一次请求阶段故障（采购网、NPCC、PDS、StateScoop、Europol），每次都未到详情。四个 NIST RSS 各 40 项；按新闻 URL 过滤后栏目内共有 112 条，合并为 105 个不同 URL，**7 个 URL 跨栏目出现**，本轮每栏目所选前两篇恰好无跨栏目重复。NIST 目前跳过 `/news-events/events/`，但未来日期也会出现在新闻 URL：Public Safety 的 11-05 条目在 11-01 被读到，管线将其 `published_at` 置空、时间线标为 unknown，不能算 11-01 新稿。

## 原页与正文质量抽查

每源留存一篇原响应，并与抽取正文做首尾和段落对照；通用原文视图的 15 篇末尾均直接匹配，14 篇开头直接匹配。江苏稿开头因解析结果在“今年 5 月”插入空格而字符串检查未命中，原页内容一致；其余 14 篇首篇的长段落逐段匹配，江苏为 10/13。这个检查会受 HTML 内联标签和空格影响，也不能证明未漏中段。人工抽查未见导航菜单或“相关推荐”混入；NIST Spotlight 的“Follow us on social media”是正文容器内推广尾句，建议后续清洗。Biometric Update 的旧“相关文章”混入已在后续解析器修正；SPF 的相关系列链接未混入此次正文。

人工初筛采用三个独立字段：`技术采集成功`=有可用候选及原页；`证据足以判断`=本页文字足以决定该材料的事实边界或明确拒稿，附件/报告是关键事实所在时计否；`符合选稿标准`=本轮可送人工选稿的警务科技材料，仍需原始归属、时间与许可核对。下表后两列是**30 篇单次样本的保守人工初筛**，非模型评估或整站入选率。

| 来源 | 技术正文/2 | 证据足以判断/2 | 符合选稿/2 | 抽查发现 |
| --- | ---: | ---: | ---: | --- |
| GOV.UK | 1（另 1 摘要） | 0 | 0 | collection 和部署记录页均指向更具体文件；HTML/CSV 附件未进入正式材料。 |
| 采购网 | 2 | 2 | 0 | 两条为大学生殖健康平台、工业数据设备，全文足以判为非警务；关键词排序有误召回。 |
| NIST Public Safety | 2 | 2 | 1 | 5G sidelink 细节可用；第一条研究内容足够但发布日期在未来，暂缓。 |
| NIST Forensic | 2 | 2 | 0 | 指纹 Spotlight 很短，另一条是过敏原研究；可明确拒本轮选稿。 |
| NIST IT | 2 | 2 | 0 | 联邦学习、O-RAN 安全有技术内容，但样本未给出警务使用证据。 |
| NIST Standards | 2 | 2 | 0 | 天线校准与泛标准活动不是当前警务科技动态。 |
| HTX | 2 | 2 | 2 | AI 运维与 Home Team 通用架构有具体场景，日期精度为日。 |
| Police Science | 2 | 1 | 0 | 杂志介绍只给导语和外链；基金征集可据正文判为征集通知。 |
| NPCC | 2 | 2 | 0 | 感染血液调查、移民犯罪行动均为一般警务。 |
| 江苏公安 | 2 | 2 | 0 | 党建和便民办证稿均可拒；转载归属应保留“人民公安报”。 |
| PDS | 2 | 1 | 0 | 网络安全报告回应未包含报告证据；另一篇峰会通稿缺技术实质。 |
| Biometric Update | 2 | 1 | 1 | 人脸识别部署报道可送人工核对原警方数据；ICE 基础设施一文需回合同/采购原件。 |
| StateScoop | 2 | 1 | 0 | 诉讼稿有原诉状链接但为 6 月旧稿；另一篇公司合作说法需一手材料。 |
| Europol | 2 | 1 | 1 | 黑客马拉松结果有官方原文；数字取证报告概述不能替代报告 PDF。 |
| SPF | 2 | 2 | 1 | 单一来电显示防诈措施有官方细节；另一篇侧重人物。 |
| **合计** | **29/30 有正文** | **23/30** | **6/30** | 证据充分与入选并非同一判断。 |

“符合选稿”的 6 条只是待人工复核候选，未发布。媒体条目须核实一手链接及转载措辞；江苏稿源属人民公安报，不能当作江苏公安原创。原页只给日期的 HTX、NPCC、Police Science、SPF、PDS 已使用 `published_date`；NIST RSS 对发布时间/活动日期的语义仍需持续核验。

## 11-02 首次跨日观察

在复用的隔离 `observation.db` 中，11-01 已留档的 30 条候选离线导入后首次为 30 新增、同快照重放为 30 重复，公开 0。11-02 的一次真实运行有 **8/15 入口完成、7/15 在网络阶段失败**。成功入口共尝试 16 个详情且 16 个返回候选：采购网 2 个新 URL，GOV.UK、NIST Public Safety/Forensic/IT、NPCC、江苏公安、PDS 共 14 个跨日重复；这次全轮修订 0，公开 0。失败阶段分别为：NIST Standards `/robots.txt` `transport_error`、HTX `/robots.txt` `timeout`、Police Science 自重定向处理后 `/sitemap.xml` `transport_error`、Biometric Update `/robots.txt` `transport_error`、StateScoop `/robots.txt` `timeout`、Europol `/robots.txt` `transport_error`、SPF `/robots.txt` `transport_error`。这些失败没有详情分母，不应算正文解析失败；多主机同晚出现连接异常，尚不能归因于单站结构或 WAF。随后针对 PDS 日期精度修复单独复采 2 篇，在同一观察库得到 **2 修订、同快照再跑 2 重复**，`published_at` 为空、`published_date` 为 10-27/10-26。

## 14 天建议与判定

从 11-01 起尽量每天同一时段运行一次全 15 源、每源最多 2 篇；单次失败可做一次单源重试，**日报保留首跑和重试两个分母**。每日至少审一篇原页与正文，依 `review-*.json` 模板分别记录 `body_clean`、`evidence_sufficient`、`editorial_fit` 与说明。当前只观察了两个日期，不能外推长期稳定性。

建议在约 14 个独立自然日后逐源评审：入口/robots 成功日数至少 12/14，成功入口的详情获取至少 90%，原始日期覆盖至少 95%，关键正文/附件足够率至少 90%，无未解释的固定上限截断或导航混入；`transport_error`/timeout 以天和阶段聚类分析。供稿稀疏单列“无新稿日”和最新原始日期，不计为入口失败。对 NIST 栏目交叉 URL 按全局 canonical URL 去重，未来日期/活动页单列；StateScoop 监控旧稿占比，GOV.UK 的附件关键事实缺口未补前不把其落地页算充分证据。阈值是**建议验收标准**，不是当前已达成结论。
