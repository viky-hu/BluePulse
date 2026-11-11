# 文章全文展示策略排查（2026-11-10）

## 结论

本机大量阅读页出现“应来源方要求，这里只提供摘要与原文入口”，直接原因是当前数据库全部 15 个来源的 `full_text_allowed=false`。这是一项本地来源配置，不是本轮检测出来源方禁止转载，也不能据此认定采集不到正文。

提示文字和摘要模式机制均来自 AIHOT 原始实现，未发现 Pulse 凭空增加“一律不得展示全文”的独立限制。不过，提示把“尚未开启全文”也解释成“应来源方要求”，其表述超出了当前配置能证明的事实。

本轮只排查和记录，没有修改运行配置、来源开关、新闻数据或前后端代码，没有触发采集和付费模型。

## 本机只读验证

目标：`backend/data/bluepulse.db`，使用 SQLite URI `mode=ro` 查询。以下是本轮查询时快照，worker 继续运行后数量可能变化。

| 项目 | 实测 |
| --- | --- |
| 来源 | 15 个，全部启用 |
| 摘录展示 | 15/15 开启 |
| 站内全文展示 | 0/15 开启 |
| 材料 | 264 条 |
| `body_status=full_text` | 255 条；这是采集状态，不是逐篇完整性验收 |
| `public=true` 且未撤回 | 224 条；这是存储标记计数，不替代读取时资格核验 |

正在运行的 `http://127.0.0.1:8000/api/v1/articles?period=all&limit=1` 返回的文章 `7db7d823-ee6d-4518-8e37-3c6ba8c29db2`，详情响应为：`body_status=full_text`、`reader.readingMode=summary-only`、`reader.body=null`、`source_body=null`、`zh_body=null`。对应材料数据库中存在非空正文。这直接复现了“有采集正文，但公开详情不返回”的路径。

当前库有一条 `system:launcher / source.bootstrap / local-live-v1` 审计，时间为 2026-11-09 03:00:04 UTC；未查询到 `source.update` 审计。布尔配置本身不保存“来源明确拒绝”或“尚未核实许可”的区别。

## 源码链路及 AIHOT 对照

1. Pulse `source_collection.py:ensure_source` 新建来源时，`excerpt_allowed` 和 `full_text_allowed` 均默认关闭；`models.py:Source` 的模型默认也如此。
2. `source_permissions.py:initialize_local_live` 只打开摘录展示并补来源门槛，不打开全文。`scripts/start-pulse.ps1` 默认本机库走 `initialize --local-live`。
3. `api.py:_detail` 在全文开关关闭时将原文和译文正文投影为 null；`reading.py:reader_projection` 返回 `summary-only`。
4. 前端 `articles/_reader/data.ts` 尊重这个模式，`ArticlePage.tsx` 显示上述提示。因此只删除提示或修改 Markdown 文档不会让 API 返回正文。
5. AIHOT `apps/web/app/routes/item.tsx` 含完全相同的提示；`packages/backend/src/publication/rules.ts:bodyModeOf` 要求 `site_fulltext` 开启、正文状态为 `ok` 且有正文，才返回全文模式。
6. AIHOT `docs/sources.md` 的“全文”规则、`site/site.ts:SOURCE_DEFAULTS`、`database/migrations/0036_open_source_defaults.sql` 和下载快照的 `industry/sources.json` 都体现默认关闭站内全文的策略；站外再分发 `syndicate_fulltext` 另设开关。本地快照不包含 AIHOT 线上数据库，不能据此声称其线上多数来源实际关闭。

## 历史为何看起来矛盾

- 2026-11-05：`docs/real-public-flow-2026-11-05.md` 记录当时只打开摘录，全文仍关闭。
- 2026-11-06：提交 `cdde313` 增加显式 `--allow-full-text` 操作；`docs/auto-publication-2026-11-06.md` 和 `backend/README.md` 明确记录用户随后同意打开当时 15 源的站内全文，并在当时本地库验证成功。该报告也明确：产品策略授权并不等于外部来源授予转载许可。
- 同日主线同步记录 `docs/backend-mainline-review-2026-11-06.md` 指出，队友数据库及许可设置在 Git 忽略目录，没有随代码同步。本机后来按确认启用新开发库，相关记录在提交 `8e03daa` 中。
- 2026-11-09：提交 `cffa8c7` 引入一键启动的 `local-live-v1` 初始化，只打开摘录，不恢复全文；当前库审计与该路径一致。

证据支持“旧库曾打开全文，新库未继承，一键启动也只恢复摘要”的解释；没有证据证明用户后来要求永久只显示摘要。无法仅凭 Git 追溯所有原始对话的措辞，因此不对某次输入是否有误作无依据判断。

## 来源真实条款：抽查而非全源审计

2026-11-10 查阅官方页面，足以反驳“所有源都不让全文展示”的推断：

| 来源 | 官方说明及判断边界 |
| --- | --- |
| GOV.UK | [使用条款](https://www.gov.uk/help/terms-conditions)说明大部分内容适用 OGL，可依许可条件复制；需要满足署名等条件并排除不适用内容，不应把该域名所有材料无条件放行。 |
| NIST | [版权与免责声明](https://www.nist.gov/copyrights-disclaimers)说明除明确标注受版权保护的材料外，站点信息可分发或复制，并要求适当来源署名；单独标注、第三方材料应分别核对。 |
| Biometric Update | [使用条款](https://www.biometricupdate.com/about-us/terms-of-use)对复制设有限制，需符合其版权声明；不能因页面公开可抓取就认定可以整篇再发布。 |

尚未完成其余来源及每篇文章、插图、附件的许可核查，不能报告“多数来源明确禁止”或“15 源全部允许”。技术抓取成功、公开阅读、站内全文展示、翻译以及对外全文再分发是不同事项；AIHOT 软件的 MIT 授权也不等于来源新闻内容授权。

## 后续处理依据

应保留可配置的全文能力，并将已核实开放许可的来源与待核实、明确受限来源区分；许可记录宜包含条款 URL、核实时间、适用范围及署名要求。文案应区分“本站当前仅展示摘要”“未取得完整正文”和“来源明确限制全文”，不能将三种情况都归因为来源要求。

若继续沿用 11 月 6 日已确认的本机全文产品策略，应把它落实为当前目标库可重复、可审计的初始化或管理配置，避免只操作一份不随 Git 同步的旧库。现有 `--allow-full-text` 能修改指定库的全部 15 源，但它本身不会核实来源条款，本轮未执行。

## 2026-11-11 修复和验证

Pulse 沿用 AIHOT `editorial/translate.ts` 的精选外文稿后台翻译策略。符合当前发布条件、允许站内全文的精选外文稿才进入翻译。译文按正文修订保存并复用付费回执，6 万字符以外的内容从原文查看，部分译文在阅读页有明确提示。

一键启动把全文作为独立版本策略应用到当前 15 个内置来源，支持已有摘要初始化记录的数据库。管理员明确设置优先，站内全文、媒体和全文再分发分别受各自开关控制。运行库备份为 `backend/data/backups/bluepulse-20261111T000239744922Z.sqlite3`。

运行中的本机 API 逐条验证 226 篇公开稿，全部返回可读原文。当前库 15 个来源开启全文，媒体和站外全文再分发均为 0 个。重复初始化仍只有一条全文升级审计。当前库核查时没有合格精选外文稿或翻译任务，首次翻译、修订重译和管理员重新翻译由隔离测试验证。

阅读页分别提示本站仅展示摘要、尚未取得正文或译文尚未完成。桌面、手机和减少动态效果均通过浏览器检查。
