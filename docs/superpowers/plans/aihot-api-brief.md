# 任务：收藏可用性公开接口

仅修改 `backend/bluepulse_backend/api.py`、新增 `backend/tests/test_article_availability.py` 和 `src/app/api/bluepulse/[...path]/route.ts` 的白名单。不要编辑其他前端或文档，不提交 git。

遵守 Pulse AGENTS。API 保留现有后端。新增匿名 GET `/api/v1/articles/availability?ids=UUID,UUID`，最多 100 个输入 ID，返回 `{ "items": [{ "id": "规范 UUID", "available": true/false }] }`。输入格式无效/超量按照现有校验格式返回 400 或 422（与 FastAPI 验证一致）；空 ids 返回空 items；重复 ID 去重并保持首次输入顺序。为免 UUID 动态路由吞掉 availability，注册在 articles/{article_id} 之前。

可用性复用 `public_article_conditions()`（和正常详情一样），不存在、deleted、未处理、metadata_only、blocked/editorial uncertain 等都 false。不返回内部状态/管理字段，不需要用户session，不区分删除和未知。single批量select，不能逐篇取全文。no-store。

前端白名单仅增加 `/api/bluepulse/articles/availability`，保持现有转发及6秒超时、错误/请求编号行为，禁止把代理扩成任意后端转发。

先写真实 DB/API 测试，使用已有 unittest/TestClient/SQLite 夹具模式。验证匿名公开和隐藏、混合/重复/空/未知UUID、非法和101条输入、返回schema与no-store。先运行测试确认功能不存在，再实现并运行相关公开API测试。检查 Python 环境现有 .venv/uv 配置，只用离线测试，不启动采集/调用模型。

返回 red/green 命令和结果、变更文件、边界选择。不提交。
