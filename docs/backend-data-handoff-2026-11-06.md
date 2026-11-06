# 后端存量数据库交接（2026-11-06）

对接同学指出的数据边界正确：提交 `cdde313` 同步的是后端代码、迁移、测试和文档，**没有同步运行数据**。`backend/data/` 被 Git 忽略；新克隆仓库并迁移后只会有表结构和七类主题，不会自动出现 15 源、35 篇材料、模型回执、许可状态、26 个 Fact 或 6 个精选席位。不能把作者本机的 API 结果当作对接机器的现状。

## 已准备的本机快照

本机已使用 SQLite `backup` API 从 `backend/data/bluepulse.db` 制作一致性快照，位于被 Git 忽略的 `backend/data/handoff/bluepulse-snapshot-2026-11-06-cdde313.db`。这份文件**未随 Git 推送**，需由负责人通过双方认可的内部文件渠道单独交付。不要将数据库、`.env` 或密钥加入 Git。

| 核对项 | 快照值 |
| --- | ---: |
| 文件字节数 | 806,912 |
| SHA-256 | `7d300bc5e0e2c0fe162600c958f5f6e8d38f4a97780d0929da07991e0fe8f91a` |
| `PRAGMA integrity_check` | `ok` |
| 来源 / 材料 / 模型尝试回执 | 15 / 35 / 37 |
| 开启摘录 / 全文许可的来源 | 15 / 15 |
| 当前 `public` 且未撤回、非重复、相关的材料 | 26 |
| Fact / 成员 / 精选快照 / 席位 | 26 / 26 / 1 / 6 |
| 自动任务 | 0 |

快照包含采集正文、来源链接和模型回执；它是**本地联调数据**，不是正式业务库，也不证明 15 源长期稳定或精选质量已达标。快照不包含 `.env` 文件；接收方仍须自行配置服务运行环境。打开的许可是数据库字段值，接收方拿到快照后才会继承。

## 接收方复验

先校验收到文件的 SHA-256 与上表一致，并在不覆盖现有数据库的前提下放入自己的 `backend/data/`。在 `repo/backend` 的 PowerShell 中，用实际接收路径设置数据库 URL；例如收到的文件名为 `backend/data/handoff/received.db`：

```powershell
Get-FileHash -LiteralPath .\data\handoff\received.db -Algorithm SHA256
$env:BLUEPULSE_DATABASE_URL = "sqlite:///$((Resolve-Path -LiteralPath .\data\handoff\received.db).Path.Replace('\','/'))"
.\.venv\Scripts\python.exe -m bluepulse_backend.cli migrate
.\.venv\Scripts\python.exe -m uvicorn bluepulse_backend.api:app --host 127.0.0.1 --port 8000
```

另开终端请求 `GET http://127.0.0.1:8000/api/v1/articles?period=all&limit=100`、`GET /api/v1/home/featured`、`GET /api/v1/site/timeline`，预计分别可读到 **26 篇、6 席、6 个精选 Fact 卡片**。详情页的 `source_body` 应在该来源的全文开关仍打开时返回。若仅克隆 Git 而未接收快照，零文章是预期结果，不是接口故障。

## 不传快照时的重建路线

可按[后端 README](../backend/README.md)先迁移空库并同步主题，再按[真实分类与展示记录](real-public-flow-2026-11-05.md)显式限量采集和分类；按[自动出稿实施记录](auto-publication-2026-11-06.md)显式打开全文许可、归组及生成精选。重建会访问外站，模型分类会产生付费调用；必须使用各命令的限量开关和明确预算。不同日期的站点供稿与网络情况会改变结果，**不能要求重建必然得到相同的 35/26/6 数字**。

对前端的交接表述应为：“接口代码已同步；有内容的实测结果来自单独的本机 SQLite 快照。对接环境需要接收并校验快照，或自行限量采集、分类并打开许可；在此之前应显示真实空态。”
