# 15 源真实分类、去重与公开展示记录（2026-11-05）

本轮按用户最新决定推进：现有 15 个来源允许**摘录展示**，真实稿可进入公开列表和详情；暂缓五轴评分及主题质量评测。全文许可仍为 `false`，详情提供模型摘要、七类标签和可回溯原站链接，不公开采集保存的整篇原文。robots、WAF、主机限制及受控重试规则不变。这里的“分类”是对真实采集正文的真实模型调用，不是固定人工标签或合成稿。

## 数据与结果

先用 SQLite backup API 将 11-03 的 15 源、30 条真实限量试采库复制到新联调库，再升级迁移与同步七类目录。旧库升级暴露出 `c9e2f4a6d110` 在新增评分列前使用最新 ORM 的缺陷；已把跨来源身份回填移到所有当前字段齐备的 `e31c8a41d2f0` 迁移。原试采库未修改。修复后实际带数据升级到迁移头成功。

联调库：`backend/data/real-public-2026-11-05/real-public-v2.db`。按用户授权显式设置 15 源 `excerpt_allowed=true`，没有改动任何 `full_text_allowed`。该库随后做了一轮当前站点自动采集、四轮按来源公平分配的分类调用，以及第二轮同库采集。确认无待分类材料后，先备份原本为空的默认本地库到 `backend/data/real-public-2026-11-05/bluepulse-before-public.db`，再将验证库复制到默认 `backend/data/bluepulse.db`。这些数据文件均在 Git 忽略目录。

| 检查项 | 实际结果 | 解释 |
| --- | --- | --- |
| 第一次当前入口自动采集 | 15 源均结束；13 源有候选，采购网与 NIST IT 为 `no_candidates`；发现结果新增 5、修订 2、重复 18 | 两个零候选来自收紧后的列表过滤，不是访问失败；本轮无真实瞬时故障，故没有触发网络重试。 |
| 第二次同库采集 | 25 个候选：新增 0、修订 0、重复 25 | 证明相同当前入口结果重放不会新增材料或重复付费；这是两次同日样本。 |
| 当前默认本地库 | 15 来源、35 材料；35/35 正文状态为 `full_text`，正文长度 609–12,261 字符 | 其中 30 条来自 11-03 实采，5 条为本轮新增；GOV.UK 的旧薄落地页重采后形成正文修订。 |
| 模型分类 | 35/35 材料有当前相关性结论；本轮 33 次新调用，旧库已有 4 次已应用回执；现有 37 条 `applied` 回执，含两次正文修订前的历史回执 | 本轮调用上限分四次设置为 15、15、5、1；实际分别使用 15、13、4、1。没有运行新五轴评分。 |
| 公开展示 | 模型判相关 26/35；当前公开 26，隐藏 9；15 源各至少 1 篇可公开稿 | 仅是模型分类和当前摘录门禁的结果，不据此宣称选稿质量或首页精选。 |
| API 和前端联调 | 后端 `/articles?period=all` 26 篇，15 个来源各自的过滤列表与首篇详情均 HTTP 200；Next 同源代理返回 26 篇，15 篇代表稿的前端详情页均 HTTP 200；选取一页 HTML 含真实标题与摘要 | `/all` 列表由浏览器端加载；本轮浏览器自动工具因无法确认窗口 URL 而停止，**未完成可视渲染检查**。`http://127.0.0.1:3000/all` 可由用户手动查看。 |
| 离线回归 | 后端 **95 passed**，1 条既有 Starlette/httpx 兼容提示 | 包含带真实行的旧库升级、摘录许可、只分类不评分、真实详情页、受控重试和既有去重测试。 |

以下是每源当前库的材料数、相关/公开数及一篇实际可通过详情 API 阅读的原文。完整材料、模型回执和四轮脱敏分类计数保存在上述本地库及 `classification-round-*.json`；两次采集诊断在 `worker/cycle-*.json`。表中链接是原站，不表示已人工审定质量。

| 来源 | 材料 | 相关/公开 | 一篇原文 |
| --- | ---: | ---: | --- |
| GOV.UK | 2 | 2/2 | [人脸识别移民执法资料](https://www.gov.uk/government/collections/live-facial-recognition-in-immigration-enforcement) |
| 中国政府采购网 | 2 | 1/1 | [中央采购公告](https://www.ccgp.gov.cn/cggg/zygg/gkzb/202611/t20261103_27614146.htm) |
| NIST Public Safety | 2 | 2/2 | [5G 公共安全通信](https://www.nist.gov/news-events/news/2026/09/enhancing-public-safety-communication-reliability-through-5g-sidelink) |
| NIST Forensic Science | 2 | 2/2 | [指纹研究](https://www.nist.gov/news-events/news/2026/09/spotlight-closer-look-fingerprint-landscape) |
| NIST Information Technology | 2 | 1/1 | [O-RAN 安全报告](https://www.nist.gov/news-events/news/2026/10/nist-publishes-reports-open-radio-access-network-o-ran-security) |
| NIST Standards | 3 | 1/1 | [法医遗传参考材料](https://www.nist.gov/news-events/news/2026/02/nist-releases-new-forensic-genetic-reference-material-help-crime) |
| HTX News | 2 | 2/2 | [Home Team 共用架构](https://www.htx.gov.sg/whats-happening/all-news---events/all-news/2026/htxplains-how-common-architecture-will-help-enhance-the-home-team) |
| Police Science & Technology | 3 | 3/3 | [公园安全数据看板](https://science.police.uk/news-and-events/news/new-safer-parks-dashboard-launched-to-support-evidence-based-decision-making/) |
| NPCC News | 2 | 1/1 | [刀具犯罪中心](https://news.npcc.police.uk/releases/national-knife-crime-centre-marks-six-months-of-action) |
| 江苏公安 | 3 | 1/1 | [警务动态原页](https://gat.jiangsu.gov.cn/art/2026/10/30/art_6372_11852488.html) |
| Police Digital Service | 2 | 1/1 | [网络安全报告回应](https://pds.police.uk/police-digital-service-welcomes-hmicfrs-cyber-report/) |
| Biometric Update 执法栏目 | 4 | 4/4 | [数字身份基础设施报道](https://www.biometricupdate.com/202610/ice-expansion-deepens-dependence-on-proprietary-digital-identity-network-infrastructure) |
| StateScoop 执法技术栏目 | 2 | 2/2 | [AI 旧案报道](https://statescoop.com/can-ai-help-solve-cold-cases/) |
| Europol Newsroom | 2 | 2/2 | [网络犯罪行动原页](https://www.europol.europa.eu/media-press/newsroom/news/5th-empact-hackathon-leads-to-detection-of-51-potential-victims) |
| Singapore Police Force Police Life | 2 | 1/1 | [统一来电显示](https://www.police.gov.sg/Media-Hub/Police-Life/2026/11/Know-Whos-Calling-SPF-Launches-Single-Caller-ID-to-Combat-Scams) |

## 复跑与继续采集

以下命令在 `repo/backend` 执行。默认库已经迁移、同步分类并按本轮授权打开 15 源摘录许可；新建库需先迁移、`sync-taxonomy`，再显式执行 `source_permissions`。**不得把 `.env` 密钥写在命令或日志中。**

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.source_permissions --database-url sqlite:///D:/311实验室实用项目/警务科技情报/repo/backend/data/bluepulse.db --execute
.\.venv\Scripts\python.exe -m bluepulse_backend.source_worker --execute --database-url sqlite:///D:/311实验室实用项目/警务科技情报/repo/backend/data/bluepulse.db --max-items 2 --retry-attempts 2 --report-dir data/source-worker
.\.venv\Scripts\python.exe -m bluepulse_backend.classify_sources --execute --database-url sqlite:///D:/311实验室实用项目/警务科技情报/repo/backend/data/bluepulse.db --allow-paid-model --max-model-calls-total 15 --report data/source-worker/classification-next.json
```

`classify_sources` 每轮至多对每个来源发起 1 次新的分类调用，额度是总上限；重复执行时沿用已有回执，只继续待分类正文。需要在一个自动触发进程中完成采集加分类时，`source_worker` 可加 `--allow-paid-model --classification-only --max-model-calls-total 15`；该模式不跑五轴评分。自动网络重试仅用于超时、传输错误和指定 5xx，每次有独立 `SourceRun`；robots 禁止、403/429、WAF 和解析错误不会自动重试。进程内可用 `--cycles N --interval-seconds S` 重复，**尚未注册 Windows 定时任务，模型额度也未跨进程累计**。需要长期自动运行前，应确定触发频率和跨进程预算。

本地页面启动：后端在 `repo/backend` 运行 `.\.venv\Scripts\python.exe -m uvicorn bluepulse_backend.api:app --host 127.0.0.1 --port 8000`；前端在 `repo` 运行 `pnpm dev`，打开 `http://127.0.0.1:3000/all`。此页默认请求 `period=all`，所以旧稿可见；首页精选、同新闻组、热点和日报仍未产生真实业务数据。
