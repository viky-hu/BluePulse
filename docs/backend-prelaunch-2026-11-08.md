# Pulse 后端闭环联调记录

日期为 2026-11-08（北京时间）。工程基线为本地 `main`，承接已有 AutoDL 兼容改动。运行说明见 [后端手册](../backend/README.md)，公开接口以 [DOCK](../dock.md) 为准。

## AIHOT 复用与 Pulse 适配

| AIHOT 实现 | Pulse 实现和验收口径 |
| --- | --- |
| `jobs/queue.ts`、`providers/receipts.ts`、`operations/recover.ts` | SQLAlchemy 持久任务、SQLite 短事务认领、来源和归组互斥、租约与恢复、分时段和单批预算。保留原始响应优先入库、按输入重放与未知结果处置。 |
| `editorial/analyze.ts`、`editorial/translate.ts` | 警务预筛、独立五轴双评分、结构化原文证据、两种写作分支和按修订保护标记的译文。 |
| `events/{group,recall,relate,digest}.ts`、`publication/{scope,publish,representative}.ts` | 三层事件关系、分批关系判断、合并复核、代表选择、事件摘要与当前证据绑定。默认走词法召回，另支持显式配置的嵌入服务。公开出口读取当前许可和撤回状态。 |
| `events/hot.ts`、`reports/{edition,compose,correct}.ts` | 独立参与方热度、缺测与小时快照、北京 08:00 规则出刊、冻结刊期与订正版本。 |
| `admin/auth.ts`、`operations/feedback.ts`、`media/{imgproxy,poster,og}.ts` | 同站密码会话与 CSRF、私有反馈附件、管理审计、按来源许可签发媒体、Markdown 和 Pulse 品牌分享图。 |

实质复用保留 [第三方 MIT 声明](../THIRD_PARTY_NOTICES.md)。SQLite 的事务、队列、身份字段及 Next.js 接口沿用 Pulse 现有边界。

## 真实信源和 AutoDL

- 使用 `backend/data/prelaunch-20261108/live-test.sqlite3`，同一隔离库预留 30 次总额度。实际发送 15 次生成请求，全部取得可应用响应。用量为 15,067 输入 token、2,044 输出 token，共 17,111 token。
- 实采得到 3 篇材料，来自 GOV.UK、江苏省公安厅和 HTX。中国政府采购网本轮无符合适配条件的候选。3 篇均完成预筛、双评分、事实结构化和写作，命中 2 次简明写作、1 次理解式写作。
- 三个来源的自动精选门槛均未校准，隔离库的摘录和全文开关保持关闭。样本中有两篇历史稿和一篇综合稿，未触发精选、真实付费翻译、同事件合并或非空热点。日报任务记录当天窗口缺少可出刊判断。有关正例通过独立的离线任务和接口验证。
- 脱敏回执与模型用量保存在隔离数据库。实际任务报告位于 `backend/data/prelaunch-20261108/report.json`。默认资讯库仍位于原迁移版本，0 个信源、0 篇材料。

## 上线前边界

后端 175 项回归、18 项前端逻辑检查、`pnpm lint` 和 `pnpm build` 通过。离线回归覆盖真实采集适配器、持久 worker、FastAPI、翻译、撤回、付费恢复、热点排名及缺测、日报正例与补刊、管理员权限、反馈与媒体限制。重复初始化与 Alembic schema 检查通过，隔离联调库升级后完整性检查为 `ok`。

生产构建通过 37 项阅读浏览器检查，以及桌面、手机、减少动态效果下的管理员和反馈浏览器检查。以真实联调库连接 FastAPI 和 Next.js，另验证热点与日报空态、登录、实采材料和回执列表、提交隔离测试反馈及退出。

正式运行前，按来源确认公开授权，并用警务金标和独立留出集校准精选阈值。持续采集可用率与公网 HTTPS 部署需在目标环境验收。
