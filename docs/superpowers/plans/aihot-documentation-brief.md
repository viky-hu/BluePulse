# 任务：AIHOT 长期研究文档

只编辑 `docs/aihot-understanding.md`、`docs/aihot-backend-stage-map.md`、AGENTS.md 和 README.md。不得修改前后端代码、安装依赖、启动采集、调用模型或提交 git。

用户要求对 D:/AIHOT 深入理解，后续几乎完整移植其成熟机制。Pulse 保留现有后端，先完成前端框架，后续警务领域校准，整体策略以 AIHOT 为主。研究文档应详细到后续实施者能定位真实源码，不可只改写 README。

读取 Pulse AGENTS、README 至新增模块之前、docs/system-construction-outline.md、stage1-backend-plan.md、开发进度及后端现状；读取 AIHOT AGENTS、README、docs/architecture/customize/selection/grouping/sources/deploy 及关键实现，核实以下内容。

文档记录日期 2026-10-11、本地为无 Git 下载快照、版本/文件校验依据、线上差异（线上模型榜/监控不在本地空 modules 列表中）。记录页面/交互/HTTP接口依赖、采集去重修订、预筛双评分结构写作、Article-Fact-Story关系、精选候选到归组发布的门槛、事件热点独立来源、日报规则/周月模型、统一发布层/许可/撤回/代表席位/ledger、缓存截止及搜索繁忙、localStorage/session30min/page缓存、管理员登录session+CSRF/人工权威、队列/模型回执预算unknown结果/停机恢复、媒体代理分享、API/RSS/MCP/Markdown/SEO、配置site/industry/modules、部署和实际验证边界。

每项要包含精确源码路径（D:/AIHOT 原路径、符号名）、实际行为、Pulse 对照、可移植部分、适配部分、缺失后端。不声称逐行全审或运行验收。本轮仅静态核对，可读取本地源码。

后端 stage-map 是差距和依赖交接稿，完整管理后台未实现、不要伪造完成状态。明确公众匿名、管理员后续同站 /admin 受保护；Pulse 目前 Python/FastAPI/SQLite/API，AIHOT Node/Fastify/Postgres/pg-boss，保留架构策略并由组员后续移植。

AGENTS.md 保留 Next 自动生成块和所有现有规则，仅追加简明重要结论和按工作主题必读研究章节/源码指引。README 只修订账号/普通登录旧规划并加入本轮基础功能和文档入口；保留 `### 本系统新增新功能新模块` 及其后全部字节内容（用户正在增写）。发布状态暂写本轮实施中，不声称验证通过。

复制许可记录 AIHOT MIT Copyright (c) 2026 数字生命卡兹克，品牌保留 Pulse。返回修改清单、核实要点与待核实事项，不提交。
