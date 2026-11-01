# AI日报源码复用与前端验收

2026-11-01，main主线。前置扩宽已独立提交并push为bd18350；日报在该尺寸基础上实施。本记录仅证明前端及受控HTTP读取，不代表真实日报生成、事件归组、模型或后台服务完成。

## 原始源码 → 复用 → Pulse适配

| AIHOT真实来源 | 复用及适配 |
| --- | --- |
| routes/report-latest、report-detail、daily-archive | /daily、/daily/:key、/daily/archive薄Next路由，复用既有MainShell加载／导航／位置恢复 |
| ReportPaper | 原Masthead、FrontPage、QuietFront、Rows／Story、Source／Coverage／Related／Original、SectionPage、快讯、Neighbours和刊尾；原全部可空／可选字段和条件分支保留 |
| ReportLayout／ReportNav、OutlineSheet／PhoneBar | 280px往期、月份展开、缺省标题读取、近期三日期、合订本、原目录／当前项／锚点；净容器1240px断点及p0滚动根，Sheet复用焦点／Escape／遮罩／body portal |
| Halftone／IssueDots／Nameplate／format | 日期点阵、播入／指针、刊历／跳转／空日、全系列刊号和日期格式；scoped useGSAP生命周期，Canvas从本组件读取局部色值，保留原950／700ms绘制及减少动效静态路径 |
| app.css、Kicker、Tabs、Badge、SourceAvatar | 原配色、字号、线条、圆角、标签／一手／跟进／来源头像。共享PillTabs仅新增可选sm和fill，既有md/xs不变；日报不引入新设计系统 |
| contracts／site API／publication reports | 完整camelCase DTO、精确只读代理、截止／错误与当前公开引用依赖；没有移植React Router、Fastify、SQL或pg-boss |

保留Pulse品牌、既有本地Google Sans／微软雅黑、白纸与绿垫。日报／周报／月报开关保留，后两者暂禁用并有原生提示。源站通用日报和合订本SVG字形SHA256分别为4ECBE4631C146005F7B1212A309CB1E2D2A3B8931F9F5A74E2D2780FB63C656D、98CE5D90FDC589D26915BB04F7F5D9ED37518CDBC7E2B18089B7E847BC38D701，与复制后的文件一致；viewBox／path未改写。原版权／MIT及字体许可说明保留。

## 行为与接口

完整契约和生成机制参考见[dock.md DOCK-008](../dock.md#dock-008ai日报刊期阅读与合订本)。日内独立参与方importance与热榜衰减热度分开，出刊不在前端调用模型；前7自然日记忆、全跟进放行、每源2／正文12／快讯10、平静／上游失败和公开引用规则均列入参考清单，不限定队友内部实现。

五组/api/bluepulse/site/reports/daily读取精确映射到/api/v1/site/reports/daily：latest-page、根索引、日期详情、navigation/:key、months/:month。非法日期／月份／额外路径／周月接口不开放。不在详情缺刊时替换为最新刊。导航和详情均404时先判服务未接入，避免响应先后导致状态不一致。

单document页面和月份合计最多16项，60／120秒上限遵守上游最早截止；详情与导航合并通常取60秒。默认共享上限仍60秒，仅日报详情显式传120秒。30分钟仅恢复位置，刷新／重试强制取新；错误、no-store／no-cache及演示／真实数据不混用。原Etag不等于本站已实现条件请求／304复用。

## 实际运行检查

最后实现运行通过：

```text
pnpm lint
pnpm build
node --test scripts/daily-report.test.mjs scripts/http-cache.test.mjs scripts/page-cache.test.mjs scripts/home-routes.test.mjs scripts/all-feed.test.mjs scripts/featured-feed.test.mjs scripts/hot-ranking.test.mjs
node scripts/daily-report-browser-test.mjs
```

- 38项相关逻辑检查通过，其中10项日报新增检查；测试先验证缺少实现时失败，并为详情404先返回的竞态补充了修复前失败／修复后通过的检查。
- 22组生产浏览器检查通过，使用1440×900、1920×1080、390×844及1440减少动态效果；无浏览器pageerror。
- UI／字段：完整纸面、七版与快讯、原标签／计数／related、刊号401、280px归档及旧月标题按需读取、合订本到具体日期、原周月禁用；p0无横向溢出。
- 交互：吸顶与目录定位以p0为根，目录body portal、同页锚点replaceState不增加历史条目；原文章链接进入既有演示阅读页，后退恢复原纸面位置；共享md分类开关保持36px并正常更新URL。
- 条件／异常：无正式刊、未接入、故障、非法JSON／字段、真平静、仅有头条、撤回引用、封面srcSet／优先级／坏图移除、缺刊、重试、精确代理、预取／进入复用、当前菜单刷新、no-store／Age截止。纯逻辑另覆盖空版／重复／连续编号、title缺省与null、nullable媒体、服务404竞态和最早组合截止。
- 人工查看桌面、宽版、移动截图，修正手机字标被适配CSS缩小的问题：移除height:auto覆盖，恢复原44px场景并加入浏览器断言。原字号／配色／徽标和界面组成按源码复核。

截图、结果位于被忽略的test-results/daily-report/。测试只启动隔离Next生产服务及本地确定性HTTP fixture，不连接真实采集、模型或通知；演示新闻不作为真实业务完成证据。既有Node MODULE_TYPELESS_PACKAGE_JSON提示未通过更改包配置消除。

## 独立审查与交付边界

真实源码与代码质量独立只读审查／复审通过。初次指出的详情404竞态、PillTabs原尺寸／铺满和局部共享变量缺失已修复；目录portal的样式作用域、边框作用域和手机字标也复核。审查没有自行运行浏览器，不算另一份运行证据。

同主线其他会话的49d1a0f关于页提交已保留；后续纸角斜线等其他会话的工作不属于本轮日报提交。最终提交只包含日报、必要共享读取／标签适配和相关文档，不收录其他会话的未提交变更。

真实后端待办：Report／引用／修订及刊期任务，Fact／Story与确认精选、日内独立主体、权威与分类校准、读取时撤回／释放／封面许可、索引／详情／月份／导航及真实联调。前端完整、Mock可读、静态源码研究和受控服务通过均不等于上述后端完成。

## 后续桌面排版修订

用户明确要求电脑窄窗口也尽量保留左侧日报／周报／月报与往期栏，收回该栏左边的大段留白，可灵活收紧字号和排布；本轮不设计移动端。此要求覆盖上文首次交付的1240px／280px布局门槛，原始功能及业务契约不变。

只修改日报局部CSS及ReportPaper样式挂点：桌面从白纸内侧边缘排左栏，不再叠加共享阅读内边距；左栏176–240px、内部左右12px，正文左右16–32px。头条28–44px、导语15–17px按正文宽度变化；头版720px起并列看点、新闻仍760px起双列，分隔内边距收为24px。采用[MDN容器查询实践](https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Containment/Container_queries)，仅桌面外壳按既有769px边界区别，正文分栏由实际容器判断。不使用整体zoom或transform缩放，避免影响点阵Canvas测量。

生产浏览器实际测量（px，四舍五入；白纸外部边界未改）：

| 窗口 | 白纸内宽 | 左栏 | 正文净宽 | 正文右边距 | 头条字号 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1180×820 | 868 | 176 | 657 | 17 | 28.6 |
| 1440×900 | 1059 | 191 | 826 | 21 | 35.9 |
| 1920×1080 | 1412 | 240 | 1115 | 28 | 44 |

新左栏期望先在旧构建上验证失败，再实现并通过。`pnpm lint`、`pnpm build`和增强后的`node scripts/daily-report-browser-test.mjs`通过，共25组检查、无pageerror。除上表三个电脑窗口外，复验1440减少动效及已有390移动回归；后者仅确认原日期条／目录和44px字标未受影响。新增检查左栏与白纸左边缘对齐、无顶栏、正文右边距、p0吸顶、桌面目录定位及不新增历史条目；保留旧月标题按需读取、日期详情、合订本及既有异常／缓存／返回位置检查。平滑滚动以实际锚点到达或滚动到底为准，不依赖固定700ms。

已人工查看1180与1440及1920截图。共享白纸、导航动画、其他会话纸角斜线未纳入本次修改；所有日报原组件及字段分支保留。接口、算法与后端状态不变，本次不算真实后端联调。
