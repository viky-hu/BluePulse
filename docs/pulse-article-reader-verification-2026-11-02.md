# 单条新闻阅读页复用验收

日期：2026-11-02。范围为新闻阅读页、必要共享导航／预览／标签请求适配、Next精确只读代理及后端交接。没有修改Python、调用采集／模型、实现真实Markdown或分享图后端。

## 原始源码 → 复用内容

直接核对`D:/AIHOT/apps/web/app/routes/{item,item-original}.tsx`、`features/item/`各阅读组件、ArticleLayout／RailSection／OutlineSheet／PhoneBar／Menu、原prose样式，以及SiteItemDetail／publication detail、items、rules、API site／og与sanitize源文件。复用标题／原标题、来源与时间、导读／理由、入选／评分、正文语言、部分译文／仅摘要、同新闻／报道组、原帖九项媒体／视频原帖入口／引用、后续和相关事件。

正文增强保留图片点击／键盘查看、表格内部滚动、代码复制及按需高亮；交互保留目录、阅读进度、移动工具收放、吸顶标题、收藏／已读、链接分享／复制、更多菜单、Markdown及按需海报弹层。原版权与新增依赖许可见THIRD_PARTY_NOTICES.md。

## Pulse 适配

- 原文使用`/articles/:UUID/original`，语种替换历史而非增加条目；目录hash替换历史，返回恢复来路、筛选及p0滚动。SSR首屏与元信息按请求去重，Next loading边界在紧凑容器中呈现刚点击卡片的内存预览。
- 流式文章网格按实际内容宽度56rem／76rem切换单／双／三栏；保留原正文可读行长与细线侧栏。全部吸顶、目录、进度、图片加载后的尺寸重算和阅读方向监听使用p0；底部工具位于白纸内。Pulse品牌、字体、绿色垫层、订书钉及已有导航保留。
- 旧公开纯文本安全转义；显式reader优先，body=null不回退旧字段。规范化只投影公开字段，不把原始reader、未知／私有嵌套属性或禁限旧正文序列化进HTML／Flight。只在明确提供的reader语言间回退。
- 数据缓存与页面位置独立，最多16项／60秒且不超过详情／taxonomy最早上游截止；no-store／no-cache不复用，强制重取与晚到结果隔离。HTML解析及阅读数据按需加载，不引入共享封面的同步解析依赖。
- 精确同源代理保留Markdown、PNG、条件请求／304、内容类型、下载头和可信缓存截止。Mock导出／海报不会访问真实接口或制造成功文件。

## 验证结果

最终生产构建、lint和TypeScript通过，`git diff --check`无空白错误。

| 检查 | 结果 |
| --- | --- |
| `node --test scripts/article-reader.test.mjs scripts/article-navigation.test.mjs scripts/all-feed.test.mjs scripts/http-cache.test.mjs scripts/page-cache.test.mjs` | 32项通过；包含15项阅读数据／代理、3项路由／tag／容器判断及既有筛选／缓存回归 |
| `node scripts/home-routes.test.mjs` | 菜单选择、深链、URL与封面入口意图检查通过 |
| `node scripts/article-reader-browser-test.mjs` | 37项通过，0失败、0页面脚本错误；生产Next加本地确定性HTTP服务 |
| `PULSE_PLAYWRIGHT_MODULE=… node scripts/navigation-loading-browser-test.mjs` | 13组共享加载／预取／导航回归通过 |
| 独立源码审查及修复复核 | 序列化投影、已授权语言回退、实际容器预览门槛三项已修复；未发现修复引入的新问题 |

浏览器覆盖1440×900桌面、390×844移动、reduced-motion；同一桌面缩放至1920检查双侧栏，820宽度检查紧凑卡片预览。检查目录／hash不增历史、p0进度与滚动、代码复制／高亮、图片键盘／Escape、移动工具下读隐藏／上读与到底显示、吸顶标题、目录焦点回归、原文替换及过滤列表返回恢复。

数据场景覆盖旧纯文本、明确无正文、部分翻译、目录少于三项、仅摘要、故障重试、真实404、SSR HTML／Flight禁限哨兵、Markdown实际下载、PNG成功／失败、X九媒体／视频来源与引用、no-store／上游到期重读、慢语种请求后离开及显式Mock隔离。测试截图和结构化结果位于忽略的`test-results/article-reader/`（8张截图、results.json、server.log）。桌面、移动和三栏截图已人工视觉复核。

## 实际边界与后端依赖

所有受控HTTP、测试新闻和PNG均用于确定性验收，不代表真实新闻、FastAPI联调、生成任务或来源授权完成。真实reader投影、精确tag检索、修订绑定译文及完整性、Fact／Story读取、正文／再分发／媒体许可、Markdown与海报／OG生成仍待队友按[dock.md DOCK-009](../dock.md#dock-009单条新闻原文与阅读工具)实施。

Next streaming中指定文章不存在会呈现gone界面与noindex；本轮直接请求观察到HTTP200，属于已开始流式响应后的框架行为。上游API的404及同源代理状态保持真实，不以该页面状态冒充业务存在。原生系统分享面板和修饰键新标签未作操作系统级验证；功能按原版条件分支保留。

本轮在main实施。开工已有封面／订书钉、热点、日报及其验收／脚本改动未纳入本轮提交；没有创建分支、worktree或PR。
