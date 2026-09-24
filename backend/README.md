# Blue Pulse 后端（Stage1 主干）

目前已搭起来源采集、文章存储、精选快照和匿名阅读 API 的主链路。真实模型暂不接入：英文内容会保留原题并标记 `pending_model`，不会伪造中文翻译或摘要。

## Windows 本地启动

在 PowerShell 进入 `backend` 目录后运行：

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
alembic upgrade head
python -m bluepulse_backend.worker sync-config
```

本地默认使用 `backend/data/bluepulse-dev.db` 的 SQLite，不需要先安装数据库服务。准备切换 PostgreSQL 时，在运行迁移、API 和 worker 的每个 PowerShell 窗口设置：

```powershell
$env:BLUEPULSE_DATABASE_URL = "postgresql+psycopg://用户名:密码@localhost:5432/bluepulse"
```

启动 API：

```powershell
python -m uvicorn bluepulse_backend.main:app --host 127.0.0.1 --port 8000
```

另开窗口立即采集一次：

```powershell
python -m bluepulse_backend.worker ingest-once
```

或者启动每日调度 worker（Asia/Shanghai 06:00）：

```powershell
python -m bluepulse_backend.worker schedule
```

API 文档位于 `http://127.0.0.1:8000/docs`。前端开发源可用 `BLUEPULSE_CORS_ORIGINS` 配置，默认允许 localhost:3000。

## 来源和内容处理

- GDELT DOC 2.0：按配置关键词检索新闻标题、原站链接、日期、语言和来源国家；不去抓取 API 返回的任意站点正文。
- Police1 Recently Published：读取公开 RSS 的标题、链接、日期和 feed 提供的摘要。
- OpenAlex：检索警务科技相关学术成果，保存题名、日期、作者机构国家及可取得的摘要。

来源配置位于 `config/sources.json`，主题位于 `config/taxonomy.json`。适配器只访问清单里的 HTTPS API/RSS 主机，不跟随重定向，并将响应大小限制在 8 MiB。文章按 canonical URL 幂等去重；相同内容不同 URL 的文章会保留并标记重复候选。缺正文、无地区或尚未模型处理都会显式记录状态。

## 公开 API

- `GET /api/v1/home/featured`
- `GET /api/v1/articles?period=30d&topic=research&region=foreign&q=police&sort=recent&limit=20`
- `GET /api/v1/articles/{article_id}`
- `GET /api/v1/taxonomy`
- `GET /api/v1/sources`
- `GET /api/v1/health/live` 和 `/api/v1/health/ready`

列表使用带排序键和筛选指纹的 cursor 分页；查询始终排除软删除文章。精选按近 24 小时优先、不足时从近 7 天补足，最多六条。

## 后续主线

尚待补齐：真实模型 adapter、实体目录及筛选、详情网页正文解析、运行记录查询/管理 API、管理员登录与软删除操作、自动化测试和 PostgreSQL 实机验证。当前采集入口是受控配置同步与 worker 命令，没有匿名触发任意 URL 的接口。
