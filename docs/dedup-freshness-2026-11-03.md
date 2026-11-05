# 文章去重与新旧稿判断（2026-11-03）

本轮只处理文章身份和发布时间，不改来源许可、人工审核或公开策略。代码位于 `backend/bluepulse_backend/material_identity.py`、`pipeline.py`、`api.py`，迁移为 `b2f7e61c904a_material_identity_and_freshness.py`。验证结果在 Git 忽略目录 `backend/data/dedup-freshness-pilot/`。

## 规则

- **同 URL**：沿用规范化 URL 唯一身份；去掉追踪参数、排列剩余查询参数。跨入口重复发现写入 `Discovery`，不增加材料或版本。
- **不同 URL 的同稿**：仅当标题规范化后完全一致、来源发布日期为同一天、双方正文各至少 400 个规范化字符，且 24 字符片段对较短正文的覆盖率至少 80% 时，自动关联为同稿。保留两站 URL、正文、来源和发现记录；镜像材料标记 `duplicate_of_id`、`duplicate_reason=same_title_day_body_overlap`、`state=duplicate_hidden`，不重复调用模型，也不进入公开列表。代表材料优先选摘录许可已允许的来源、官方来源，再按首次发现时间。正文短、日期缺失、仅同标题或同一事件不同报道不会自动合并。
- **修订**：原文内容变更仍保留 `MaterialRevision`。同稿关系按当前标题和正文重新计算；镜像变成独立报道时重新排入分析，已有适用回执可以复用。
- **新旧稿**：有可信精确时间的文章，以首次发现时间减原发布时间 **48 小时**为新/历史分界；超过发现时间 1 小时的未来时间不可信。只有日期的页面，发现当日或前一日记近期，更早记历史，未来日期不可信；`published_at` 继续为空，内部 `published_sort_at` 只用于排序。`24h` 列表要求精确时间，日期级文章不会冒充“近 24 小时”；`7d/30d` 与 `all` 按可信原始日期筛选和排序，不用首次抓到的时间把旧稿推到前面。

这里的“近期/历史”是**相对首次发现**的处理标签，和是否值得选稿、是否与主题相关是不同判断；历史稿仍可在 `period=all` 中阅读。跨不同标题的转载、同事件后续进展和综合稿需要更丰富的事件关系，当前规则不会据关键词相似度擅自合并。

## 归档样本验证

用 11-01 至 11-02 已人工标注的 **15 入口、60 条入口 × URL 样本**，从本地基线正文回放到新隔离库；不访问外站、不调用模型、不写正式业务库：

| 检查 | 结果 |
| --- | --- |
| 同 URL 去重 | 60 条入口样本 → 59 条不同 URL 材料；[NIST 芬太尼研究](https://www.nist.gov/news-events/news/2026/10/nist-study-shows-how-toxic-substances-mixed-fentanyl-vary-across-us-and)跨 Public Safety / Forensic 两入口只存一条 |
| 不同 URL 高置信同稿 | [NPCC 奖项稿](https://news.npcc.police.uk/releases/national-awards-shine-spotlight-on-the-innovation-transforming-policing)与[PDS 同稿](https://pds.police.uk/national-awards-shine-spotlight-on-the-innovation-transforming-policing/)关联 1 组；59 条 URL 对应 58 份独立正文 |
| 11-03 回放时点分类 | 53 历史、5 近期、1 日期不可信；12 条为仅日期精度。此项按回放时刻计算，不冒充 11-01/11-02 的实时新稿量 |
| StateScoop | 4 条均为历史稿，原始发布日期分别为 2026-04-21、2026-06-10、2025-07-10、2025-10-15；不把 11 月抓到误报为新稿 |
| 未来日期 | NIST 一条 11-05 页面在本次 11-03 回放中记日期不可信，不列入近期窗口 |
| 公开 | 0 |

已将旧版 `observation.db` **只读备份到另一隔离文件**并升级验证：59 条材料仍在，补算出 1 组跨 URL 同稿，16 条既有日期级材料获得排序时间。这个副本的样本口径与上述 60 条回放不完全相同，因此日期级条数不直接比较；原观察库及正式业务库均未被迁移命令写入。

## 复跑

在 `repo/backend` 下指定一个新的空目录：

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.dedup_freshness_pilot --output-dir data/dedup-freshness-pilot/replay-next
```

输出 `result.json` 和逐材料 `materials.csv`。改动有针对性测试：同 URL 跨入口只存一条；同标题不同正文不误合并；NPCC/PDS 型正文重合镜像不重复分析和展示；原文修订解除镜像关系；日期级旧稿、未来日期、`24h/7d/all` 和分页均按原始日期处理。样本结果只证明这些归档材料及测试边界，不能推断所有相似报道都能自动识别。
