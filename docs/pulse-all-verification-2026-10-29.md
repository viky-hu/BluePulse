# 全部动态页复用与验收

日期：2026-10-29。本记录对应用户纠正后的最终稿，取代初稿的视觉检查结论。范围是 `/all` 前端、必要共享导航／缓存适配和接口交接；没有修改或运行后端采集、模型、分类迁移。

## 原始源码 → 复用内容 → Pulse 适配

原始证据为本地非 Git 的 `D:/AIHOT` 下载快照；本轮直接核对源码，不将静态研究等同线上原站验收。

| 原始源码 | 复用内容与最终适配 |
| --- | --- |
| `routes/all.tsx` | 标题、分类／搜索行、搜索排序、结果、空态和分页层级。仅 `/all` 默认全部时间；查询变化正常 push，旧结果等待时 opacity 0.5，不套 Pulse 整页淡入淡出。 |
| `features/feed/Filters.tsx`、`components/ui/Tabs.tsx` | 分类单选与搜索保留条件；`PillTabs` 的选中块位于 active link 内，自然占满按钮。桌面 md 高36px／横 padding16px／14px字；手机44px。保留原300ms／cubic-bezier(.25,1,.5,1)原生滑块，由 scoped useGSAP 管理清理。 |
| `components/ui/IntentLink.tsx` | 鼠标、焦点和静止触摸100ms意图预取，取消滚动触摸计时。以 Next Link/router 和既有页面缓存替代 React Router 调用；分类保留位置，搜索与分页正常归顶。 |
| `features/feed/DayList.tsx`、`Timeline.tsx` | 分日、44px桌面日期栏、64px／22px时间轨；手机36px灰底满宽日期栏。月日加星期／周X；按用户要求所有尺寸均无年份和“今天”。没有额外18px日间距。 |
| `features/feed/FeedItem.tsx`、`parts.tsx` | 来源、桌面17px标题／15px三行摘要、分类、理由及收藏；手机来源／时刻同行、17px两行标题／14.5px两行摘要、隐藏分类、理由单行。保留320ms收藏反馈及已读弱化。 |
| `components/ui/Score.tsx`、`Page.tsx:EmptyState` | 原85／70分层评分胶囊；空态24px横 padding／56px纵 padding、15px标题与原描述／可选动作位置；手机无外卡片边框。 |

框架保留 Next.js16／React19／TypeScript／Tailwind4／GSAP、本地 Google Sans 与微软雅黑。p0 的位置、尺寸和原菜单切页动效参数未变；仅将既有 padding 提取为变量供本页吸顶和手机 bleed 使用。按内容宽度760px切工具栏列，600px切卡片呈现；不按整窗宽度挤小原控件。

已移除初稿增加的地区标签、独立演示说明行、搜索模式说明行、每页条数、骨架卡片和旧筛选 chips。Mock 仅在同一 h1 标注“（演示）”；相关度暂不可用仅通过禁用状态／title 表达。旧 period／topic／source／source_type／entity／sort 查询继续传递，不为旧查询额外扩展 UI。

## 数据与真实边界

使用同源 `/api/bluepulse/{articles,taxonomy}`，映射现有 FastAPI `/api/v1/`，每页40条真实游标。新七类必须由 taxonomy 精确注册；未注册、真实空数组、请求失败分别呈现。原文日期缺失时按后端有效时间归日，现有 time 节点显示“待核”，title 明确实际发现时刻，避免增加一行说明或把发现时刻冒充原文时间。

当前搜索真实检索正文并按 recent 排列；旧 importance 搜索链接归一为 recent 并丢弃旧排序游标，非搜索 importance 浏览继续兼容。没有伪造 total／pageCount／todayCount／freshness、精选标记、事件归组或 X 媒体。

服务端绝对截止、Age／Date、no-store、最多60秒页面复用与30分钟位置恢复沿用既有机制。前端依赖及后端实施任务见根目录 `dock.md` DOCK-004。

## 验证结果

| 检查 | 修订稿结果 |
| --- | --- |
| `pnpm lint` | 通过，0 error／warning |
| `pnpm build` | 生产构建、TypeScript及全部路由生成通过 |
| 六组相关逻辑脚本 | 26项通过；覆盖全部动态、URL、浏览器状态、缓存、HTTP截止与导航状态机 |
| `scripts/all-feed-browser-test.mjs` | 18组通过，浏览器异常0；1360×760桌面、390×844移动及桌面 reduced-motion |
| `scripts/navigation-loading-browser-test.mjs` | 13组通过，浏览器异常0；包含不缓存、过期后重新核验、位置恢复、快速改跳与晚到结果隔离 |
| 源码对照审查 | 初稿两项正确性问题和用户指出的复用偏差已修正；最终复核无阻断项 |

浏览器直接检查按钮高度／横 padding／字号、桌面搜索240px、选中块与 active link 四个几何量对齐，观察分类／搜索过程 stage 始终 idle。还覆盖斜杠聚焦、输入法、清空输入、互斥条件、缺分类与真空结果、收藏／已读、详情返回、40／8条游标往返、无历史回首页、失效游标恢复、吸顶、无横向溢出、503重试、格式错误、taxonomy故障、旧列表半透明等待和明确的 Mock 详情。

检查结果和截图位于忽略的 `test-results/all-feed/`、`test-results/navigation-loading/`，可运行上述脚本复现。运行环境沿用已有 Node 模块类型提示，不改变 package.json 为了消除提示。

## 未完成依赖

本轮浏览器使用生产 Next 服务加本地受控 HTTP 服务，未做真实 FastAPI 数据联调；测试文章不是业务新闻。七类注册与历史归类、分类提示词／人工覆盖、相关度、数字分页／真实统计、搜索容量保护、统一发布／撤回／许可缓存仍须后端组员实施并单独验收。完整 MIT 版权声明保留于 `THIRD_PARTY_NOTICES.md`。
