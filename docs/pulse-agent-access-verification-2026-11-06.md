# Agent HTTP 接入：源码对照与验证

2026-11-06。主线从 `a2adf10` 快进至队友的 `4aaf881`；GitHub 只读对比确认远端当时无更新。本轮在 `main` 实施，保留用户未跟踪的《网站后续维护方案.md》。前端与接口状态以 DOCK-010 为准。

## 原始源码 → 复用内容 → Pulse 适配

证据为 D:/AIHOT 静态下载快照，已直接核对源码及本地研究 §2、§9、§11–12；不代表源站线上完整功能。队友的 `agent-access-frontend-guide.md` 明确首版 HTTP，MCP／RSS 不展示。下表逐项覆盖原页信息，不将原站能力直接宣称为 Pulse 能力。

| AIHOT 来源／原内容 | Pulse 对应与处理 |
| --- | --- |
| `routes/agent.tsx`：页首、用途、匿名只读、不注册／不需 Key | 保留顺序及承诺；品牌为 Pulse，数据范围改为近期资讯与标题／摘要搜索 |
| loader 的健康状态、配置站点地址与时间 | 服务端固定 origin；浏览器实际检查三个同域 HTTP 出口，说明探测范围，避免普通健康检查冒充客户端接通 |
| `TRACKS` 接入卡片、侧栏当前方式、`?tab=` | 默认给 Agent 使用，`?tab=api` 为 JSON；保留卡片参数、正常 URL、历史和深链接，补齐键盘行为 |
| `ANCHORS`：跨面板锚点与打开面板后滚动 | 参数／字段、错误处理与能力表有固定锚点，滚动到 p0 内部，支持仅带 hash 的直达 |
| `RESOURCES` 的 Agent 使用说明 | 保留真实 Markdown 链接，前置可复制地址满足窄屏首屏；步骤区引导读取同一地址 |
| llms.txt、OpenAPI 3.1 外链 | 本站暂无对应已发布资源；不伪造链接。使用原资源卡片链接至本站实际参数／字段表；公开机器规范交接后端 |
| “没接上？”、平台／版本／报错、别发 token 或本地文件、去反馈 | 保留文案和反馈入口；反馈后端既有状态不因本轮改变 |
| `parts.tsx` 的 PanelHead、Steps、Step、Block | 保留层级、28px编号、连线、间距、分隔线；按 p0 净宽布局 |
| Ask、Address、CodeBlock、CopyButton | 复用指令／地址／代码和复制状态；补失败反馈、文本可选、计时器卸载清理及重复点击保护 |
| Table、Mono、Bullets、Details | 保留表格、行分组、行内代码、列表和折叠排错；长表／代码局部横滚，不撑宽 p0 |
| Tips、“用得省，也更快” | 保留三提示结构；改成按需读取、no-store重新核对、保留出处，不许诺现有出口没有的压缩比例／ETag／刷新频率 |
| Callout、模块 Banner、TAG、GUIDE_CLIENTS、扩展 recipes／blocks | 原框架可用原语，但快照模块列表为空；没有可复用的实际内容，不生成额外告示、客户端安装器或标记追踪 |
| MCP 地址、客户端配置、工具表、安全／连接排错 | MCP暂缓；不展示虚假地址、工具数量和配置命令。通用安全／连接排错迁入HTTP说明，协议专属说明不展示 |
| RSS摘要／全文／全部／日周月／分类订阅和刷新 | RSS暂缓；不展示订阅地址、分类表或不存在的转载承诺 |
| REST“第一个请求”“接口一览”“常见用法” | 使用本站三个精确路由；提供可运行 curl.exe 双引号示例、参数、响应字段；无新增查询表单 |
| REST热点／事件／日周月、snapshot／changes及游标恢复 | 本轮后端不提供，不宣称可用，不生成同步流程 |
| REST 400／409／429／5xx排错 | 按本站真实422、503／504及代理错误说明；429仅作为部署入口可能返回的响应，无自造额度；无snapshot恢复或缓存复用建议 |
| PhoneBar、ReadingLayout、全站样式及返回“我的” | 使用Pulse既有共享壳、ReadingLayout、移动菜单、字体和导航，去除原站重复全页框架与“我的”路由 |
| 原条款／品牌／新闻权利 | 保留匿名不等于转载许可、外部资料不可执行与原文核对提示；不链接不存在的条款页；完整MIT及版权保留在THIRD_PARTY_NOTICES |

实现分工：`src/app/agent/` 中入口负责服务端配置；AgentPage负责URL、锚点和状态；panels为准确业务文案；parts与CodeBlock为原页原语；CSS Module按原字号、12px卡片、7px控件、8px小块、青色与间距适配。没有新增依赖，也未改Logo几何或共享GSAP时间轴。MainShell仅允许Agent查询切换保留位置，并避免当前tab重复刷新。

## 验证结果

| 验证 | 结果与证据边界 |
| --- | --- |
| ESLint | 本地已安装 `node node_modules/eslint/bin/eslint.js` 通过；与package脚本相同。Corepack曾尝试联网下载pnpm，未因此新增依赖 |
| 生产构建 | `node node_modules/next/dist/bin/next build` 通过，包含Agent页及三个精确动态API路由 |
| 接入契约／代理单测 | 4项通过；固定origin、拒绝路径／凭据、Markdown字节与错误状态、no-store、请求ID、超时／断开、空JSON校验 |
| URL／导航已有测试 | `home-routes.test.mjs`、`navigation-intent.test.mjs`通过；与新单测合计node test报告6项通过 |
| 后端完整测试 | 同步后独立执行，97 passed，21.20秒；1条既有Starlette/httpx弃用警告。测试使用隔离库及模拟外部服务 |
| 真实接口＋浏览器 | `node scripts/agent-access-browser-test.mjs`：14组通过，页面异常0。原始报告及截图在被Git忽略的`test-results/agent-access/` |
| 真实Codex HTTP步骤 | 本轮Codex通过命令工具启动隔离服务，读取真实Markdown（含实际curl.exe调用），执行近期和搜索请求，均200、schema_version=1、items=[]；属于本机Codex工具链闭环，非公网或其它客户端认证 |

浏览器使用生产Next端口3160及真实FastAPI端口3161读取默认库；另用3162检查前端未配置。覆盖1360×760、390×844、reduced-motion、首屏地址、复制地址／指令／失败、局部横滚、tab／键盘／历史／刷新／跨tab锚点、保留滚动及无重复探测。真实后端分别验证200空、422、配置缺失503、断开503；6秒504单独使用受控慢HTTP上游，不当成真实后端性能结论。测试均自动清理自行创建的服务，不停止用户原有3000／8000进程。

本机正式库为0信源、0材料。本轮不采集、不调用模型、不导入业务数据；没有有结果的新闻／出处点击验收，也没有公网部署、限流、CORS、MCP、RSS或完整同步验收。接口权限、日期精度和撤回等非空数据边界来自后端隔离测试，不冒充真实业务库正向验证。

## 使用及后续

旧服务需停止后重新双击Pulse.bat，才能继承显式本地origin并加载新后端代码。手工启动需在前后端分别设置同一固定origin；没有生产本机地址回退。完整步骤见[使用说明](使用说明.md#agent-http-接入)。后端补充、校验差异和公网验收见[DOCK-010](../dock.md#dock-010agent-http-接入页)。
