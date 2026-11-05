# 旧后端选稿标注恢复记录（2026-10-28）

旧后端删除前的本地备份为工作区根目录 `repo-backend-local-backup-2026-10-27.zip`。从其中的 `data/` 按原始字节恢复了四份 JSONL 到 `repo/backend/data/legacy-selection/`。该目录受 `.gitignore` 保护，样本标题、链接等内容不进入 Git，也不用于公开接口。

| 文件 | 条数 | 标注状态 | SHA-256 |
| --- | ---: | --- | --- |
| `selection-pilot-20.jsonl` | 20 | 全部 `review_status=confirmed`；开发集 15、留出集 5 | `f95de668cb9a1279d8b23c75f83fe84da88d2cdb8e7d61969fc40f9090cf653f` |
| `selection-pilot-40.jsonl` | 40 | 仅 1 条有部分相关性标签，均未确认；开发集 32、留出集 8 | `979990d3ea7d1ec4f53621720bb54bc48fd1a7bdeb063066bb75de80018ddb73` |
| `selection-candidates-20261001-v2.jsonl` | 95 | 未标注候选池；开发集 76、留出集 19 | `2588bbb5f0aaeb84d3ca70bc68a7530e6c4b5a0f7bbfec1270bc2044cd67b3a9` |
| `selection-candidates-20261001.jsonl` | 95 | 另一份原始候选导出，内容与 v2 不同；开发集 76、留出集 19 | `477d566e0713120f1962850605658d63e7d1e56e5c7689e3246c04920585b0e8` |

恢复后逐文件比对 SHA-256。20 条已确认样本的案例 ID 均唯一、理由均非空；12 条相关样本都有主题和内容类型，8 条无关样本均为 `reject`。其中相关性为 `direct` 10 条、`potential` 2 条、`irrelevant` 8 条；精选 `select` 3 条、`reject` 17 条。`primary_topic` 或 `content_kind` 在部分无关样本中为空，符合[原标注口径](./selection-annotation-guide.md)。

备份中的旧 `bluepulse-dev.db` 有 20 条 `editorial_*` 人工覆盖，案例 ID 与上述已确认 20 条完全一致，没有额外的人工覆盖。旧数据库仍保存在 ZIP 中，没有导入新后端数据库。旧 `scripts/selection_dataset.py`、`selection_review.py`、`selection_eval.py`、`apply_selection_gold.py` 和相关配置仍可从 Git 历史取得，但依赖旧数据模型，不应直接放回新运行链路。

后续使用时，以 `selection-pilot-20.jsonl` 作为**历史小样本金标准**；40 条和 95 条只作为待复核样本。旧 `article_id` 指向旧数据库，不能作为新后端的材料 ID；迁移需要先用原始 URL 或来源标识匹配，再人工核对。保留 5 条留出集不参与规则调整。20 条样本缺少足够的精选正例和新重点领域覆盖，不能单独证明新模型的召回率。标注字段、证据等级和精选规则仍以[标注指南](./selection-annotation-guide.md)为准。
