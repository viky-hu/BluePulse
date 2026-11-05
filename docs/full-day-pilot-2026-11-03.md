# 15 源单日全流程试跑（2026-11-03）

## 范围与口径

以 2026-11-01 已归档的每入口 2 篇为固定样本，共 **15 个入口、30 条入口样本、30 个不同 URL**。这些样本来自当天多次限量试采的归档，**不是一次同时抓取 15 源的网络运行**，也不代表各源当天或跨日期的真实供稿量。逐篇标注、原文链接和内部审阅正文见本地 Git 忽略目录 `backend/data/full-day-pilot/2026-11-01/` 的 `items.csv`、`result.json`、`review.html`。采集方法、入口故障、原页核对及更大范围的主题抽样，分别见[15 源台账](source-validation-ledger-2026-11-01.md)、[首轮采集报告](source-validation-baseline-2026-11-01.md)和[60 条主题质量抽查](source-quality-2026-11-02.md)。

本次把归档候选重放到全新隔离库，经 `Candidate → collect → URL 去重 → Material → Analyzer → Topic → /api/v1`，每条再用同一候选重放一次验证去重。主题与证据标签是此前逐篇人工复核的**固定输入**，`MockAnalyzer` 只检查下游流程，没有把 30 篇送给真实模型。`ready_for_review` 是内部待审状态，不等于人工终审通过或获准公开。原来源许可门禁保持关闭，没有写正式 `bluepulse.db`，没有发布文章。

## 运行结果

| 环节 | 结果 | 含义 |
| --- | ---: | --- |
| 首次导入 | 30 新增 / 30 尝试 | 15 个入口均有 2 条归档候选进入隔离库 |
| 同批重放 | 30 重复 / 30 尝试 | 此固定样本 URL 去重生效 |
| 下游处理 | 30 applied、0 failed、0 unknown | 全部人工固定标签成功写入分析回执 |
| 主题符合 | 15 直接、6 相邻、9 偏离 / 30 | 单日固定样本的人工主题判断，直接密度 15/30 |
| 正式主题关系 | 9 / 30 | 仅“直接且当前正文证据足够”的材料获得前端主题标签 |
| 内部去向 | 6 待审、15 暂缓、9 拒绝 / 30 | 暂缓含缺附件/原件、旧稿、未来日期和相邻主题 |
| 真实样本 API | 7 个前端主题、15 来源、0 公开文章、隐藏详情 404 | 许可门禁确实阻止真实样本展示 |
| 合成 API 正向契约 | `practice` 列表 1、`law` 列表 0、详情 200、来源全文不外露 | 独立 `example.test` 许可样本验证分类筛选与详情形状；**不是 30 篇真实稿展示** |

前端所用七类 `product/practice/paper/law/embodied/public-opinion/low-altitude` 已作为新库 `/taxonomy` 的启用主题。旧宽泛主题在同步时停用但保留历史行；正式业务库尚未执行这次同步。9 条带主题的真实材料在隔离库中分为 `paper` 3、`product` 2、`practice` 3、`law` 1。其余三个主题本样本无匹配文章。

## 逐源流转

每行分母均为本轮归档的 **2 篇**。`分类`是证据足够后写入主题关系的篇数；每行的原文链接仅作复核入口，完整 30 条 URL 见 `items.csv`。

| 入口与原文例子 | 直接 | 分类 | 待审 / 暂缓 / 拒绝 | 主要原因 |
| --- | ---: | ---: | ---: | --- |
| [GOV.UK 部署记录](https://www.gov.uk/government/publications/live-facial-recognition-deployment-records) | 2/2 | 0/2 | 0 / 2 / 0 | 两页主题相关，关键部署事实仍在附件/下级文件，当前正文证据不足 |
| [中国政府采购网](https://www.ccgp.gov.cn/cggg/zygg/gkzb/202611/t20261101_27598681.htm) | 0/2 | 0/2 | 0 / 0 / 2 | 靠前公告是非警务采购，关键词误召回 |
| [NIST Public Safety：5G Sidelink](https://www.nist.gov/news-events/news/2026/09/enhancing-public-safety-communication-reliability-through-5g-sidelink) | 2/2 | 2/2 | 1 / 1 / 0 | 一篇可审；另一篇原始发布日期晚于 11-01 样本日 |
| [NIST Forensic：指纹 Spotlight](https://www.nist.gov/news-events/news/2026/03/nist-helps-fingerprint-examiners-new-data-and-software-release) | 1/2 | 1/2 | 0 / 1 / 1 | 相关篇有证据但时效/价值不足，另篇偏题 |
| [NIST IT：联邦学习](https://www.nist.gov/news-events/news/2026/10/privacy-preserving-federated-learning-ppfl-testbed-and-curated-dataset) | 0/2 | 0/2 | 0 / 2 / 0 | 泛技术相邻，缺明确警务应用 |
| [NIST Standards：天线校准](https://www.nist.gov/news-events/news/2026/10/nist-ctl-announces-new-low-uncertainty-broadband-antenna-gain-calibrations) | 0/2 | 0/2 | 0 / 0 / 2 | 标准/机构新闻不符本次选稿主题 |
| [HTX：AI 运维](https://www.htx.gov.sg/whats-happening/all-news---events/all-news/2026/leveraging-ai-to-reimagine-day-2-ops) | 2/2 | 2/2 | 2 / 0 / 0 | Home Team 技术实践有具体事实，待原文终审 |
| [Police Science：杂志通知](https://science.police.uk/news-and-events/news/the-fourth-edition-of-policing-tomorrow-is-now-available/) | 0/2 | 0/2 | 0 / 2 / 0 | 两篇是目标内容入口/资助通知，当前页缺技术实质 |
| [NPCC：警务新闻](https://news.npcc.police.uk/releases/policings-first-ai-online-crime-reporting-test-goes-live) | 0/2 | 0/2 | 0 / 0 / 2 | 当日两篇偏离；后续较大抽样发现 AI 报案试点，不能据此淘汰入口 |
| [江苏公安：转载稿](https://gat.jiangsu.gov.cn/art/2026/10/30/art_6372_11852488.html) | 0/2 | 0/2 | 0 / 0 / 2 | 本轮党建/服务稿偏题；原页转载来源须保留 |
| [Police Digital Service：报告回应](https://pds.police.uk/police-digital-service-welcomes-hmicfrs-cyber-report/) | 1/2 | 0/2 | 0 / 2 / 0 | 相关页缺报告原件证据，另一篇峰会稿仅相邻 |
| [Biometric Update：人脸识别](https://www.biometricupdate.com/202610/uk-facial-recognition-rollout-widens-as-police-oversight-rules-take-shape) | 2/2 | 1/2 | 1 / 1 / 0 | 一篇可审，另一篇仍需一手归属核对 |
| [StateScoop：误认诉讼](https://statescoop.com/florida-man-aclu-sue-police-after-wrongful-arrest-using-facial-recognition-tech/) | 2/2 | 1/2 | 0 / 2 / 0 | 一篇旧稿，一篇证据不足；旧稿/稀疏供给不算抓取失败 |
| [Europol：EMPACT Hackathon](https://www.europol.europa.eu/media-press/newsroom/news/5th-empact-hackathon-leads-to-detection-of-51-potential-victims) | 2/2 | 1/2 | 1 / 1 / 0 | 行动稿可审；电子证据报告概述不能代替报告全文 |
| [SPF Police Life：统一来电显示](https://www.police.gov.sg/Media-Hub/Police-Life/2026/11/Know-Whos-Calling-SPF-Launches-Single-Caller-ID-to-Combat-Scams) | 1/2 | 1/2 | 1 / 1 / 0 | 技术实践可审，另一篇人物故事仅相邻 |
| **合计** | **15/30** | **9/30** | **6 / 15 / 9** | 均为固定样本判断 |

这 30 条没有跨入口重复 URL；同源重放的 30 条重复只证明隔离库的去重行为。NIST 跨栏目同 URL 重叠出现在另一次 60 条抽样里，仍需以跨入口规范化 URL 处理。

## 限量真实模型核验

在另一隔离库，对 4 条代表样本分别调用模型一次，上限 4 次，实际 **4 次 applied、0 公开**。逐项脱敏回执见 `backend/data/full-day-pilot/2026-11-01/model-probe-live/result.json`。HTX AI 运维、NIST 5G Sidelink 判相关且包含人工主类；中国政府采购网非警务公告判不相关。这 3 条与人工判断一致。GOV.UK 人脸识别部署记录被模型判“相关/practice”，但人工证据审查判**当前正文不足以支持部署事实**；这是“主题相关”与“证据足够”的不同口径，不能将 3/4 粗略解释为模型准确率。模型摘要尚需逐事实复核，4 条也不足以评估整体模型质量。

首次受限网络环境的 `/models` 预检未连通，**0 次模型调用**；随后在获准的联网环境用新隔离目录成功预检并执行 4 次。未输出 `.env` 密钥。模型分类结果没有写入 30 篇全流程隔离库，也没有覆盖人工标签。

## 复跑与下一步

在 `repo/backend` 下执行；每次使用一个**新的空输出目录**，以免覆盖证据：

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.full_day_pilot --output-dir data/full-day-pilot/replay-01
.\.venv\Scripts\python.exe -m bluepulse_backend.full_day_model_probe --execute --allow-paid-model --max-model-calls 4 --output-dir data/full-day-pilot/model-replay-01
```

第二条有真实付费调用，只有确需再核验模型时才运行。现阶段更值得继续推进的是：人工完成 6 篇待审稿的原页、日期、归属、事实锚点和许可核对；为 GOV.UK/PDS/Europol 的附件或报告补证据路径；把可审稿的编辑结果接到**内部审核界面**，再做一次有权限控制的公开流程。采集可靠性和主题密度的跨日期判断仍未由本轮证明；用户当前希望先看流程效果，可以暂不等待 14 天才能推进这些工作。
