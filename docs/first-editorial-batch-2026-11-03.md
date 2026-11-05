# 首批人工选稿闭环：立即推进清单（2026-11-03）

依据 [15 源主题质量抽查](source-quality-2026-11-02.md)中 60 个入口样本，去重后已有 8 篇“主题直接相关、正文证据足够、可送人工复核”的候选。本清单是**内部审阅包**，未做模型分析、正式入库或发布。将“采集到正文”推进为“有原文可查、有事实边界、能作人工选稿决定”，无需等待跨日期稳定性结论。

## 先处理 4 篇官方原文

| 优先级 | 官方原文与日期 | 可核对的警务科技事实 | 人工审阅要点 |
| --- | --- | --- | --- |
| 1 | [新加坡警方统一外拨来电显示](https://www.police.gov.sg/Media-Hub/Police-Life/2026/11/Know-Whos-Calling-SPF-Launches-Single-Caller-ID-to-Combat-Scams)，11-01 | 警方宣布 11-02 起使用统一外拨来电显示，并配套官方短信确认，用于防范冒充警方诈骗。 | 保留“宣布/启用”的时间区别；核对号码及短信机制；不把防诈效果写成已验证。 |
| 2 | [HTX 的 AI 运维项目](https://www.htx.gov.sg/whats-happening/all-news---events/all-news/2026/leveraging-ai-to-reimagine-day-2-ops)，10-29 | HTX 介绍 VendorPulse 概念验证：读取供应商报告图表、文本与指标，辅助运维团队比较报告期并提示风险。 | 项目仍处 POC；节省工时数字是机构预期/赛事陈述，须归属原说法，不作独立效果结论。 |
| 3 | [HTX 的通用船舶与车辆架构](https://www.htx.gov.sg/whats-happening/all-news---events/all-news/2026/htxplains-how-common-architecture-will-help-enhance-the-home-team)，10-28 | HTX 介绍海事平台通用架构与车载电子/车辆平台标准化，目标是降低新系统集成和培训负担。 | 区分正在开发的方案与已部署能力；说明其覆盖 Home Team 多部门，避免写成仅警方项目。 |
| 4 | [NPCC 的 AI 在线报案试点](https://news.npcc.police.uk/releases/policings-first-ai-online-crime-reporting-test-goes-live)，09-25 | 英国剑桥郡警方的 Citizen Assist 试点用对话式 AI 收集非紧急犯罪报案并生成结构化报案记录。 | 明确试点范围是袭击、威胁、损坏和盗窃等报案路径；区分辅助报案与自动警务决策；因时间较早，适合案例/技术观察而非当天快讯。 |

以上事实依据为已采正文与相应官方原文。每篇下一步形成一张内部事实卡：原始标题、发布日精度、原文 URL、最多 3 个可定位到原文段落的事实、技术使用场景、仍未知事项、归属与摘录许可、人工决定（采用/暂缓/拒绝）。许可核对前保留原站链接和内部事实笔记，不改变来源 `excerpt_allowed=false`、`full_text_allowed=false` 门禁。

## 第二批 4 篇

- [Europol 的 EMPACT 黑客马拉松结果](https://www.europol.europa.eu/media-press/newsroom/news/5th-empact-hackathon-leads-to-detection-of-51-potential-victims)：官方结果，需分清技术方法与行动成果。
- [NIST 的 5G sidelink 公共安全通信研究](https://www.nist.gov/news-events/news/2026/09/enhancing-public-safety-communication-reliability-through-5g-sidelink)：技术实质较强，09-14 发表，更适合研究/案例材料。
- [NIST 的芬太尼混合物研究](https://www.nist.gov/news-events/news/2026/10/nist-study-shows-how-toxic-substances-mixed-fentanyl-vary-across-us-and)：公共安全与取证应用，已在两个 NIST 栏目出现，必须去重为一篇。
- [Biometric Update 的英国警方人脸识别报道](https://www.biometricupdate.com/202610/uk-facial-recognition-rollout-widens-as-police-oversight-rules-take-shape)：媒体报道，需对照警方/监管机构一手数据与原话后再判断。

## 本轮验收标准与后续工程顺序

1. 对首批 4 篇完成原文事实卡和人工采用决定；每个关键陈述能回到原文，日期与实施/试点状态无夸大。
2. 用独立观察库验证候选的 URL 去重、日期、来源和待审状态；不因 `full_text` 自动授予公开资格。
3. 选 2 篇正例及 2 篇误召回/证据不足例做一次可选的模型质量对照，**最多 4 次调用**，记录与人工标注的差异及费用/回执；调用前核实模型 ID。此步骤不应代替人工事实审阅。
4. 根据事实卡中的真实阻塞修补适配器：优先 GOV.UK 附件证据链；其次处理 CCGP 的泛“数据/平台”误召回和 NIST 栏目交叉去重。修改后用现有固定 URL 作回归检查。

这是一轮短期内容验收，不能据此声称来源跨日期稳定或全站质量密度。
