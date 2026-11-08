# AutoDL 模型 API 连通与解析测试（2026-11-06）

## 结论

已修复当前 AutoDL 模型的调用参数并完成真实三调用验收：中文标题、摘要、分类和两次独立五轴评分均通过，三个响应的思考 token 均为 0。测试使用隔离库和虚构材料，未改变密钥或正式资讯库，不代表真实采集、资讯质量或持续生产运行已验收。下文首次测试失败的证据保留作为修复前对照。

## 首次测试范围与配置（修复前）

- 分支：`main`。未修改后端业务代码、用户密钥配置或业务数据库，未采集外站、发布新闻或启动自动任务。
- 使用 `backend/.env` 中的本机配置；不记录 API Key。
- 基础地址：`https://www.autodl.art/api/v1`。
- 模型 ID：`DeepSeek-V4.1-Flash-1017`。
- 使用明确标注为虚构的英文警务无人机搜救演练计划作为测试输入，仅用于验证模型接口和解析；不作为真实资讯或质量评测样本。
- 真实生成调用上限及实际次数均为 1，没有重试或执行五轴评分。

## 首次测试证据（修复前）

| 检查 | 实际结果 |
| --- | --- |
| 现有配置读取器 | 读取成功，HTTPS 地址、密钥和模型 ID 均已填写 |
| 现有 `model_listed()` 预检 | `/models` 返回 HTTP 200，包含配置模型 |
| 现有 `LiveAnalyzer.analyze()` | `/chat/completions` 返回 HTTP 200 |
| 生成耗时 | 约 5.8 秒 |
| 提供方 usage | 输入 579 token、输出 450 token、合计 1029 token；输出中的 reasoning token 为 450 |
| 结束原因 | `finish_reason=length` |
| 最终输出 | `message.content` 为空 |
| Pulse 解析 | `ProviderRejected: provider_invalid_schema` |

发送前已保存调用身份和请求参数，收到响应后保存脱敏回执，再交给现有分析器解析。详细回执在 Git 忽略目录：`backend/data/model-api-check/20261106T101548080646Z.json`。实际金额未查询，以 AutoDL 账单为准。

## 原因与原始依赖

源码核对：`backend/bluepulse_backend/live_model.py` 中分类默认 `max_output_tokens=450`；仅当接口主机为 `api.deepseek.com` 时，才添加关闭思考和 JSON 输出参数。AutoDL 请求没有进入此分支。本次响应表明，450 个输出 token 在思考阶段已耗尽，未生成最终 JSON，触发现有截断与解析校验。

下一步由后端适配 AutoDL 对应模型的思考开关、结构化输出及输出额度，先核对服务商实际支持的参数，再限量复测。不要直接全局套用某一厂商的参数，也不能仅凭一次响应推断长期稳定性。评分调用也有相同的主机判断，适配时需一并核对。

本轮只验证接口可达及现有分析器的兼容性边界，未验证真实采集、内容正确率、入库恢复、公开列表、精选、热点或日报。

## 已实施调整

- 沿用 Pulse 的 `LiveAnalyzer`、分类处理和双评分回执流程。源码依据为 AIHOT `providers/receipts.ts`、`editorial/analyze.ts` 的输入／配置身份、独立双评分、未知结果保护与响应优先保存机制；本次按 Python／SQLite 现状做限定适配，不移植 PostgreSQL、pg-boss 或完整生产回执架构。
- 分类和评分共用请求构建与诊断逻辑。仅对 AutoDL 两个官方主机上的 `DeepSeek-V4.1-Flash-1017` 发送 `thinking={"type":"disabled"}`、`response_format={"type":"json_object"}`、`stream=false`；分类上限 1024、评分 512 token，输入仍最多 4200 字符。其他模型不套用 AutoDL 专用配置。
- 所有模型命令默认读取 `backend/.env`，显式 `--env` 优先。未修改用户填写的配置，也不自动读取旧位置。
- 区分截断、空答案、JSON 无效、字段错误和 HTTP 错误。失败／未知回执记录安全的状态、request ID、结束原因、耗时与 usage；不记录密钥或完整思考文本。
- AutoDL 分析和评分身份包含实际请求配置，长度不超过数据库的 50 字符限制。保留历史回执；同修订的旧在途／未知尝试不会因切换配置自动重发。
- 新增默认关闭的 `model_smoke_check`，非空输出目录不能重用；付费请求不自动重试。发送状态先落盘，收到的脱敏响应先保存，再由实际分析器和业务校验解析。Windows 短暂文件锁只允许有限重试回执文件替换，不重试网络请求。

## 修复后真实验收

在 `D:/pulse/backend` 执行了默认未启用检查，并执行一次如下真实检查：

```powershell
.\.venv\Scripts\python.exe -m bluepulse_backend.model_smoke_check --execute --allow-paid-model --max-model-calls-total 3 --env "D:/pulse/backend/.env" --output-dir data/model-api-check/autodl-fixed-20261106
```

| 步骤 | HTTP／结束原因 | 用时 | 输入／输出 token | 思考 token | 结果 |
| --- | --- | --- | --- | --- | --- |
| 分类、中文标题及摘要 | 200／stop | 2226 ms | 572／153 | 0 | 中文标题、中文摘要与 `low-altitude`、`practice` 分类校验通过 |
| 五轴评分 1 | 200／stop | 1459 ms | 547／39 | 0 | 五轴整数校验通过，总分 24 |
| 五轴评分 2 | 200／stop | 1511 ms | 547／39 | 0 | 独立请求与回执，总分 24 |

实际生成次数为 3，没有重试；总输入 1666 token、输出 231 token、合计 1897 token。第三次请求报告缓存命中 512 token。三个 request ID 均非空且互不相同，答案非空、JSON 和业务字段均通过，三个响应的思考文本长度也均为 0。金额未查询，以 AutoDL 账单为准。

真实脱敏回执为 `backend/data/model-api-check/autodl-fixed-20261106/report.json`，隔离库为同目录 `smoke.db`，均被 Git 忽略。隔离库包含一条明确标注的虚构材料和三条已应用分析／评分回执，公开材料数为 0，来源摘录／全文许可保持关闭。评分门槛为 `null`，结果明确为 `uncalibrated`，不是精选入选。

真实检查前后比较 `backend/.env` 与 `backend/data/bluepulse.db` 的 SHA-256，均保持不变。未创建系统定时任务、采集外站或修改正式来源许可。

## 工程验证与限制

- 后端完整测试：`137 passed`；保留一条现有 Starlette/httpx 弃用警告。
- 回归覆盖：旧的思考耗尽输出、分类／评分共享参数、其他提供方不变、默认及显式配置路径、四类解析失败、HTTP 400／401／402／403／429、超时无重试、跨配置未知回执保护、发送前保存、失败即停、三次上限、思考关闭检查、非空目录防重复运行及短暂文件锁。
- `pnpm lint`、`pnpm build`、`git diff --check` 通过。此次无前端或动效改动，不将编译检查解释为浏览器视觉验收。
- 默认沙箱中的 FastAPI TestClient 检查停滞；停止了本轮对应的 pytest 进程，允许本机回环／socketpair 后完整测试通过。没有为通过测试改写业务语义。
- 独立只读审查发现一处诊断结束原因字段的脱敏遗漏；使用模拟回显密钥复现后修复，新增分类／评分及隔离库失败回执断言，复核确认关闭。审查及修复后未追加真实模型调用。
- 此次仅交付当前接口兼容和隔离模型处理验收；真实采集、金标准确率、生产原始响应持久化全链路、跨进程预算、长期调度稳定性、来源精选门槛校准、热点及日报仍属于各自后续工作。
