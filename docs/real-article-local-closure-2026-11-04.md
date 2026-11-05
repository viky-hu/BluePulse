# 真实稿本地闭环试验（2026-11-04）

本轮只在本机隔离环境测试一篇 GOV.UK 真实稿，从来源采集到前端显示；不写正式 `backend/data/bluepulse.db`，不对外发布。代码入口为 `backend/bluepulse_backend/real_article_pilot.py`，原始逐项采集结果、模型回执及两个 SQLite 库在 Git 忽略目录 `backend/data/real-article-pilot/2026-11-04-govuk/`。

## 运行与结果

在 `repo/backend` 下，使用新的空目录；显式允许最多 **1 次**真实模型调用：

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.real_article_pilot --execute --allow-paid-model --output-dir data/real-article-pilot/next-run
```

| 检查 | 本轮结果 |
| --- | --- |
| 采集 | GOV.UK robots 和搜索入口通过；最多 2 条详情，取得 2 条；目标为[实时人脸识别部署记录](https://www.gov.uk/government/publications/live-facial-recognition-deployment-records) |
| 文字证据 | 英文 HTML 正文 2,073 字符、1 行表头加 18 行数据；英文 CSV 解析 18 行，逐项相同；[HTML 正文出处](https://www.gov.uk/government/publications/live-facial-recognition-deployment-records/live-facial-recognition-deployment-in-november-2025-accessible)保存于材料和修订 |
| 入库与去重 | 隐藏库首次新增 2；相同快照重放重复 2，材料仍为 2 |
| 模型 | 预检通过，调用 1 次、`applied` 1 次；目标判相关，主类 `practice`（实战），评分 62；没有分析另一条 collection 页 |
| 隐藏库 API | 来源摘录权限关闭；文章列表 0，目标详情 404，近 30 日时间线 0 |
| 本机展示副本 | 从隐藏库复制一个独立 SQLite，**仅在该副本**把 GOV.UK 来源摘录权限用于本机测试并重放已保存模型结果；`period=all&topic=practice` 列表 1、详情 200、时间线 0 |
| 浏览器 | 本机 Next + FastAPI：分类列表显示“实时人脸识别部署记录”，点击进入详情，看到标题、导读、GOV.UK 来源与原文入口；列表、详情和代理请求 200，浏览器错误日志 0。结束后关闭浏览器测试页和两个本机服务 |
| 正式环境 | 正式数据库仍为 0 来源、0 文章；没有持久开启任何真实来源的正式公开许可 |

时间线为空符合当前日期规则：落地页原始首次发布日期为 2026-01-09，本轮测试日为 2026-11-04；旧文只在 `period=all` 列表中出现，不会因今天采到而冒充近 30 日新稿。

## 内容质量与边界

模型导读准确指出附件是 Holyhead 地区部署结果表，并列出了表内可核对的日期、时长、摄像头、阈值和警报等字段。但它把原字段 `Watchlist number` 写成“监控名单人数”，原文未明确该数字的单位就是人数；对外文字应改成“名单数量/规模”等更保守表述。`practice` 是本次单篇模型判断，尚未作全部 15 源的主题密度评估。页面的最近更新时间与附件可见数据最后日期也不相同，不能从该试验推断有更新部署。

本机副本的正向展示证明 API 与页面技术链路可通，**不等于真实文章已获准在正式站点公开**。正式使用 GOV.UK 内容还需按具体页面核对 OGL 适用范围、第三方例外与署名；目前页面没有专门显示 OGL 归属声明。首页精选、事件归组、热点和日报也不属于这次单篇列表/详情试验。

本轮同时将 GOV.UK 与 NIST 的 robots 预检放入 `source_collection.build_adapter` 返回的适配器包装层，常规预览、入库和逐源验证共用同一门禁；资产主机 CSV 仍单独预检。针对性测试覆盖常规 GOV.UK 入库在 robots 禁止时不访问搜索；完整测试结果见本轮回归。
