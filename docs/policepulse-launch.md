# PolicePulse 公网首发部署

首发入口使用 `/all`。精选、热点榜和 AI 日报继续使用现有数据与空态。实验室官网可用「PolicePulse」作为入口名称，链接到主站的 `/all`。

## 选稿与初始数据

2026-11-13 核对了当前标注包的 20 条确认，开发集 15 条，留出集 5 条，另 100 条停止标注。已有模型结果与 20 条材料的 ID、修订和内容哈希一致。14 条推荐中 5 条达到精选候选资格，6 条不推荐均未成为候选。9 条漏选都通过预筛，其中 6 条标为有现场评估的实战案例。两个离门槛最近的案例分别差 1 和 4.5 分，其余相差 12.5–29.5 分。先复核实战证据与评分标准的差异，暂沿用 60／65／76 门槛。完整理由和原 HTML 存在本机忽略目录 `backend/data/policepulse-launch-20261113/`。这些对照是单人小样本的存量结果，本轮没有重新调用模型。

数据库快照与清单必须从当前业务库重新生成，不能复用早期 2026-11-13 的部署候选快照或其旧计数。2026-11-15 本机交接快照的位置、SHA-256、完整性检查、业务计数及逐源权限见[日报重建与数据交接记录](daily-history-reconstruction-2026-11-15.md)。只把最新数据库快照和清单传到服务器的私有目录。首次公网发布前逐源确认摘要和站内全文，必要时从管理员页收紧。媒体与全文再分发独立授权。

## 准备目标机

使用 Ubuntu Server 24.04 LTS x86-64，安装 Python 3.12（含 `venv`）、Node.js 24 LTS、pnpm 10.6.1、Caddy、SQLite CLI、Git 和 `curl`。示例约定 Node 位于 `/usr/local/bin/node`。安装后运行 `node -v`、`pnpm -v`、`python3.12 --version` 和 `caddy version`。以现有 AIHOT 的 Web、API、worker 分进程模式为依据，沿用 Pulse 的 SQLite、Alembic 和现有任务恢复机制。

- 建立系统用户 `policepulse`，以该用户运行三项应用服务。由管理员维护 `/etc/policepulse` 和 Caddy 配置。为数据库创建本地目录 `/var/lib/policepulse`，属主为 `policepulse`、权限 `0700`。维护访问走 SSH，公网只开放 Caddy 所需的 HTTP/HTTPS。
- 把已验证的 Git 提交解包到 `/opt/policepulse/releases/<提交号>`。以 `policepulse` 用户运行 `pnpm install --frozen-lockfile`。在该版本的 `backend` 运行 `python3.12 -m venv .venv` 和 `.venv/bin/pip install -e '.[test]'`。同一版本目录完成 `pnpm lint`、`pnpm build --webpack` 和后端 `.venv/bin/python -m pytest -q`。
- `sha256sum` 核对上传前后快照，`sqlite3 -readonly <快照> 'PRAGMA integrity_check;'` 应返回 `ok`。只在全新生产路径安装快照，路径固定为 `/var/lib/policepulse/bluepulse.sqlite3`，文件属主为 `policepulse`、权限 `0600`。核对 `alembic_version`、材料和来源计数。首次启用前，以同一运行用户和下面的数据库环境执行 `backend/.venv/bin/python -m bluepulse_backend.cli initialize`，随后用 SQLite CLI 设置 `PRAGMA journal_mode=WAL;` 并确认返回 `wal`。初始化沿用快照已有的来源配置。

### 运行环境

把以下内容写入 `/etc/policepulse/site.env`，将示例主域名替换成实际域名。构建 Web 时也使用此文件的公开站点配置。

```dotenv
BLUEPULSE_SITE_ORIGIN=https://policepulse.example
BLUEPULSE_API_URL=http://127.0.0.1:8000
BLUEPULSE_DATABASE_URL=sqlite:////var/lib/policepulse/bluepulse.sqlite3
BLUEPULSE_TRUST_PROXY=1
BLUEPULSE_FEEDBACK_ENABLED=1
```

- `/etc/policepulse/api.env` 保存 `BLUEPULSE_ADMIN_PASSWORD`（至少 12 字符）和独立的 `BLUEPULSE_ADMIN_SESSION_SECRET`（至少 32 字符）。启用签名媒体时另设独立的 `BLUEPULSE_MEDIA_SECRET`。API 密钥文件由 root 管理并设为 `0600`。
- 将模型的 `base_url`、`key`、`llm_id` 写入该版本的 `backend/.env`，权限 `0600`，仅运行账号可读。该位置由现有 worker 的启动检查和隔离联调共同使用。
- `/etc/policepulse/worker.env` 首次写入以下配置。验证隔离批次后，将两个开关改为 `1` 再启动生产 worker。以下上限为首发默认值，生产调用包含失败及重试。观察用量后再调整。

```dotenv
BLUEPULSE_COLLECT_ENABLED=0
BLUEPULSE_MODEL_CALLS_ENABLED=0
BLUEPULSE_MODEL_BUDGET_MINUTE=12
BLUEPULSE_MODEL_BUDGET_HOUR=60
BLUEPULSE_MODEL_BUDGET_DAY=240
```

### 启动和域名

把 `/opt/policepulse/current` 指向已构建的提交目录，将 [systemd 和 Caddy 模板](../deploy/policepulse/) 中的 service 和 timer 以 `0644` 安装到 `/etc/systemd/system/`。执行 `systemctl daemon-reload` 后，先 `systemctl enable --now policepulse-api policepulse-web policepulse-backup.timer`。检查回环的 `http://127.0.0.1:8000/api/v1/health/ready` 和 `http://127.0.0.1:3000/api/bluepulse/taxonomy`。备份 timer 每天北京时间 03:00 运行。确认备份目录及异机备份可读，并按实际保留周期清理旧副本。

将主域名的 DNS 指向租用服务器。复制 `Caddyfile` 到 `/etc/caddy/Caddyfile` 并替换两个示例域名。实验室 DNS 未就绪时先省略别名块。用 `caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile` 验证，再重载 Caddy。实验室子域名启用后，检查 HTTPS 308 保留文章路径和查询参数。Caddy 覆盖 `X-Real-IP`，当前应用依靠该值识别客户端并限流。模板适用于 Caddy 直接接收公网流量的部署。

## 开放前验收

1. 在目标机用 `policepulse` 用户、后端虚拟环境和与服务一致的站点环境，运行 `python -m bluepulse_backend.runtime_health --json --probe-model`。确认模型在 `/models` 可见，结合报告定位源、任务和历史失败。此时生产 worker 尚未开启，检查可能返回 1。
2. 从后端目录运行 `python -m bluepulse_backend.worker --live-test /var/lib/policepulse/prelaunch`。该入口使用独立库，单批最多 30 次请求，检查 `report.json` 中真实来源及处理结果。之后启用生产采集和模型开关，执行 `systemctl enable --now policepulse-worker`。等待至少一篇新采入真实稿完成分析，经许可从 `/all` 进入详情并打开原始来源。记录逐源成功、无新增、重复和失败。
3. 从外部网络打开 `/all`，在桌面、手机和减少动态效果设置下验证列表、检索、详情直达和刷新。确认公开地址与分享链接使用主域名。检查 3000／8000 不能从外部访问，`/api/v1/internal/auto-publication/jobs` 不能经边缘访问。验证 HTTPS 管理员会话和缺失 CSRF 被拒绝。撤回测试先用快照副本完成，再按实际需要使用管理员纠错。
4. 运行一次 `systemctl start policepulse-backup.service`，将备份还原到独立路径并以只读方式核对完整性、版本与文章 ID。重启目标机后检查三项服务、timer、HTTPS 和真实阅读。检查均通过后发布主站入口。实验室入口接通后再补验其跳转。

上线后用 `journalctl -u policepulse-worker` 和 `runtime_health --json` 检查采集时间、回执、模型预算和积压。发生采集或模型故障时在 `worker.env` 关闭对应开关，再重启 worker，已通过许可的稿件继续提供阅读。更新前先备份，停止 worker 排空，再停止 Web 和 API。新版本构建完成且迁移通过后切换 `current` 并启动。回退时按版本与库结构匹配的快照恢复，先保存故障现场，保留切换后新增数据供核对。

## 2026-11-13 本地验收

- 应用提交 `3b68aae` 的独立副本通过 257 项后端回归、ESLint 和 webpack 生产构建。Windows 一键启动另完成 Turbopack 生产构建，Web、API、worker 均就绪。
- 在快照副本上通过桌面、手机、减少动态效果三组真实稿件的列表、检索、详情、刷新和原文链接检查。管理员登录、缺少 CSRF 被拒绝、成功撤回后列表及详情不可见均通过。快照校验为 `ok`。
- Caddyfile 通过 Caddy 配置校验。systemd 单元在 Ubuntu WSL 中用本地可执行文件路径检查，备份定时解析为北京时间 03:00。目标 Ubuntu 24.04 主机的实际启停、域名、证书和公网端到端检查待服务器就绪后执行。
- 完整启动后，15 个信源的本轮状态均正常，采入 2 篇新稿。SCNet 的 DeepSeek V4 默认思考耗尽部分步骤的输出额度。请求改为该供应商 OpenAI 接口的 `enable_thinking: false` 后，只重新排队本轮两篇失败稿件，两篇均完成研判、归组并公开。本机公开统计从 228 增到 230，后端回归增至 260 项通过。 [SCNet OpenAI 接口文档](https://www2.scnet.cn/ac/openapi/doc/2.0/moduleapi/api/chat.html)
