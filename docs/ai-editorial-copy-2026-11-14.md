# AI 导读与模型文案

单篇导读从谁做了什么、进展如何写起，通常一到两句，最多三句。能用一句讲清就停笔。保留决定事实含义的限制，明确区分拟议、招标、成交、试点、部署和实际成效。独立的推荐理由沿用 AIHOT 的精选代表稿做法，无法提供原文支持的额外阅读价值时留空。选稿诊断留在后台。

| AIHOT 源码 | Pulse 实现 |
| --- | --- |
| `industry/prompts/{rules-answer-first-summary,rules-self-contained-title,rules-anti-hallucination,summarize-article,understand}.md` 和 `packages/backend/src/editorial/writing.ts` | `editorial_copy.py` 复用答案前置、独立阅读价值和按句压缩，增加中文及英文日期、百分比、数字和行动阶段校验。兼容采集入口与后台写作共用这套规则。 |
| `industry/prompts/{prefilter,selection-score,structure,safety}.md` | `editorial.py` 和 `live_model.py` 保留宽召回、五轴独立判断、正文证据和当前动作，沿用 Pulse 的分类与评分接口。 |
| `industry/prompts/{group-definitions,group-method,group-batch,group-pair,story-digest,translate-body}.md` | `grouping.py` 向判断和复核传递当前事实框架，`story_digest.py` 用当前公开证据写事件概览，翻译保留段落及占位符。日报使用确定性组刊，向量接口用于召回。 |
| `packages/backend/src/publication/{publish,detail}.ts` | 首页、文章列表、详情和 Markdown 读取当前精选代表稿的独立理由，历史席位里的理由不进入公开响应。 |

## 存量维护

在 `backend` 下运行。默认命令以只读方式输出当前公开稿清单、状态和预计新调用数。试写只保存任务和回执，审核可按稿件 ID 及原文输入哈希订正成稿。应用阶段复用试写结果，按材料修订和提示词版本去重，写入前核对原文、发布状态及人工覆盖。日报对同一材料修订更正引用及头条导语并保存上一版。

```powershell
python -m bluepulse_backend.summary_backfill
python -m bluepulse_backend.summary_backfill --preview 12 --max-attempts 12
python -m bluepulse_backend.summary_backfill --apply --max-attempts <本次总调用上限> --workers 3
```

付费步骤沿用后台模型开关、预算、模型配置和结果未知恢复规则。应用命令可追加 `--reviewed`，文件格式为 `{"version":"提示词版本","items":[{"id":"稿件 ID","input_hash":"原文输入哈希","summary":"核对后的导读","reason":null}]}`。审核稿可以补齐失败项。对已收到但未过文案校验的结果，可用 `--apply --repair-failed` 在预算内用更短的提示补试一次。暂未到恢复时间的任务留在队列，命令输出待处理数。

## 本机回填记录

- 本机库 210 篇公开稿全部更新，人工覆盖 0，回填失败或待处理 0。新版导读平均 88.8 字，最长 160 字。最终采用的提示词版本为 `f3c8d3fd0a28a68e`。12 篇试写逐篇核对后应用，另有 25 篇经人工对原文补写，两篇较长的稿件再压缩。稿件标题、评分、归组、精选状态和译文沿用现有记录。
- 最终版本共记录 257 次真实模型请求尝试，其中 10 次结果未知，未重发。另有 48 次前几轮试写，用于改进提示词与数字校验。请求尝试数不能直接作为实际计费数。
- 6 期日报均核对了同修订的引用，共保存 31 条导读更正历史。原刊期、原条目顺序及旧版本可追溯。
- 用本机业务库读取详情、列表、精选、日报、热点、Agent、Markdown 及分享海报。后端测试 294 项通过，生产构建及 lint 通过，桌面、移动端和减少动态效果的阅读器浏览器检查共 39 项通过。
- 导读长度、选稿措辞和部分事实边界有程序校验。程序校验不能代替逐篇查证，写作质量以人工对照原文的试写和补写记录为准。
