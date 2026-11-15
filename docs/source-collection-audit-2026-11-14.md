# 15 信源采集复盘与恢复

审计窗口为北京时间 2026 年 11 月 8 日 00:00 至 11 月 14 日 21:45:33。运行记录与可复现的原站响应保存在本机 `backend/data/collection-audit-2026-11-14/`。`baseline.db` 是在线 SQLite 备份，已通过 `quick_check`。`evidence.json` 保存初始原站清单，后续对账和修订后的回补清单同目录保存。

## 复现与修复

| 来源 | 原站核对与改动 |
| --- | --- |
| 政府采购网 | 中央和地方各启用招标、成交中标、竞争性磋商、谈判、询价、更正、终止及其他公告等 9 类入口。读取原站发布时间，对带有原始标题及独立发布日期的转载保留日期精度。候选由相关采购方或明确警务科技任务召回，原文再判纳入与公开。对照原站快照，冻结清单 212 条采购漏采全部能通过新版列表逻辑。 |
| GOV.UK Home Office | 用按原站最近更新排序的 Home Office 清单替代单一检索词。详情核实文章首次发布时间，更新日期用于发现修订。预告尚未发布的统计稿在队列记录状态，随原站后续更新重新评估。 |
| Europol、StateScoop | 用官网新闻室分页和官方执法主题 REST 入口扩充 RSS 覆盖，记录分页能到达的时间界限。 |
| 四个 NIST 栏目 | 使用已核实的官方主题列表补足短 RSS，保留 RSS 线索。处理出版日、日期区间与活动日期的区别。 |
| HTX、NPCC、江苏公安、Police Digital Service、Biometric Update、SPF | 逐站核对已接入的新闻列表及来源日期，记录原始分页或官方接口终点。江苏公安新闻发布会官方接口共 15 条，最新为 2026 年 9 月 18 日，审计窗口内无发布。 |
| Police Science & Technology | 原站 sitemap 提供候选链接，网页在审计中返回浏览器验证页面。运行记录保留部分覆盖及正文缺口。 |

迁移参照 `D:/AIHOT/packages/backend/src/sources/collect.ts`、`sources/dates.ts`、`content/materials.ts` 和 `operations/recover.ts`。Pulse 在 SQLite 持久任务中复用材料身份、修订、正文补取及恢复行为。原始分页证据决定窗口是否覆盖。失败重扫可变列表首页，靠已提交材料去重，独立入口的检查点仅在完成后推进。截断归档保留缺口，近期窗口继续滚动。常驻 worker 在启动就绪检查和采集批次中记录规则版本及入口指纹。原站访问遵循 robots 及 `Retry-After`。AIHOT MIT 版权见 [第三方声明](../THIRD_PARTY_NOTICES.md)。

## 操作和验收记录

在 `D:/pulse/backend` 中运行以下命令，参数示例以本次审计目录为基准。实际回补使用经过逐条核对的清单。对账要求保留未判定、无法访问及归档截断的原因。

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.source_audit --database data/collection-audit-2026-11-14/baseline.db --evidence data/collection-audit-2026-11-14/evidence.json --report data/collection-audit-2026-11-14/comparison.json
.\.venv\Scripts\python.exe -m bluepulse_backend.source_audit_capture --from-date 2026-11-08 --output data/collection-audit-recapture
.\.venv\Scripts\python.exe -m bluepulse_backend.collection_recovery replay --baseline data/collection-audit-2026-11-14/baseline.db --output data/collection-audit-2026-11-14/isolated.sqlite3 --manifest data/collection-audit-2026-11-14/backfill-final.json --manifest-only
.\.venv\Scripts\python.exe -m bluepulse_backend.collection_recovery queue --manifest data/collection-audit-2026-11-14/backfill-final.json
```

`replay` 使用独立数据库和正式采集、正文补取队列，全源重跑时省去 `--manifest-only`。`queue` 默认只预览，经过隔离验证后加 `--apply` 才向已配置的业务库写入队列。正常编辑判断、可见性和转载许可由业务 worker 执行。切换前备份，使用仓库的 `scripts/start-pulse.ps1 -Mode stop` 与 `-Mode production`，使用 `-Mode health` 查看服务、列表覆盖及正文补齐情况。

最终对账覆盖 15 个信源、42 个核查入口、9,031 条原始记录。28 个入口的可用档案覆盖审计窗口。还有 13 个政府采购栏目达到原站分页上限，Police Science sitemap 有 64 个链接无发布日期，详情返回浏览器验证。逐条对账和核查范围见 `baseline-report-reviewed.json` 与 `audit-summary-reviewed.json`。

确认漏采 215 条，政府采购网 212 条、Europol 2 条、GOV.UK 1 条。采购详情中发现两篇原站正文含未配对的内联 HTML 标签，旧解析会提前退出正文容器。隔离库通过正式队列与原站证据补齐两个清单共 215 条。第一批 195 条于 11 月 15 日 09:16 加入业务队列，其余 20 条于 09:24 加入。`production-verification.json` 记录提交后的入库和发布情况。

公开稿偶发 404 的回归由 SQLite WAL 旧读快照复现。文件型 SQLite 的 API 连接现按请求释放。仅重启 API 后，两条此前受影响的公开稿各完成 24 次并发读取，全部返回 200。详情、Markdown、分享图、全部动态、热点、日报、归档和 Agent 出口检查见 `public-backfill-verification.json`。

采购正文保留表格单元格边界，原文带括号的币种与相同金额仍通过精确匹配。36 条曾被文案校验拦下的公告已按新版本重验。对账中发现转载列表可能覆盖已验证的日期精度，回归覆盖只给原始日期的稿件。另对 6 篇已公开材料修正采购分类，并记录原分类、当前修订及依据。结构化标签限制为有正文依据的短词。对于采购稿，实战、法制和专门领域的分类以本次采购进展及原文对象为准。

截至 11 月 15 日 10:43，215 条已确认漏采全部在业务库补齐正文，172 条公开、17 条经编辑规则判定不公开、26 条因文案事实校验未公开。11 月 14 日原始发布日期对应 32 条漏采，其中 29 条已公开。生产对账中可核验范围的待回补项为零，超出可用原站档案的时间窗单独记录。全量后端回归为 330 通过，另有一条已有的 Starlette TestClient 弃用提示。前端 lint、生产构建和三种浏览器模式检查通过。

11 月 15 日 12:51 与 13:51 的连续自然调度均记录 15 个信源完成，14 个来源的本轮覆盖有证据，Police Science 仍为部分覆盖。最后一次只读复核后，worker 持久化按主机的 `Retry-After`，跨页顺序校验后才采用日期边界，详情原始日期优先于列表精度，GOV.UK 统计预告到发布时间再补取正文。隔离回放报告列出延迟任务的下次执行时间。`production-verification.json` 和 `production-reconciliation.json` 留存实测时间、版本及逐项去向。

15:31 启动的收尾版规则 `912e64fe0cbe` 在 15:33 完成首轮自动采集。15 个信源均完成，13 个可证明覆盖，Police Science 和存在跨页乱序、达到 25 页上限的地方竞争性磋商栏目为部分覆盖。收尾版本的第二轮尚未观察。全量后端回归 333 通过，前端生产构建成功，页面和 API 就绪探针均为 HTTP 200。当前轮次见 `latest-worker-verification.json`，公开补采稿核对了 172 篇详情和 808 个正文标签。
