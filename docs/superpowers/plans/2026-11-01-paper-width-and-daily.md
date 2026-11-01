# 共享主场景扩宽与 AI 日报复用执行计划

用户已于2026-11-01批准本计划。直接在main工作，不创建分支、worktree或PR；两个阶段顺序执行，分别验收、提交和push。不得修改FastAPI、调用模型或采集，也不把受控数据验证当作真实后端完成。

## Task 1：共享主场景扩宽

- 桌面菜单左距2.8vw，宽clamp(220px,18vw,280px)；纸左max(23vw,菜单右沿+16px)，绿左为纸左减2.5vw；绿右留白1.470588235vw，纸右留白3.470588235vw。
- 移动端绿色左右基础边距10px并避让安全区，白纸再内缩8px；保留抽屉和原垂直几何。移除769–1000px的旧菜单25%覆盖。
- CSS稳定场景是终点真值，通过局部refs把真实绿色/纸矩形传给InitialIntro；初始化/resize时读取、转换、缓存，逐帧只插值。保留归一化进度、SSR稳定态、reduced motion、一次性守卫，以及原封面、p1–p5退场、时序、缓动、上下边界与阴影。
- 关于、共享阅读壳、搜索和历史的页面级外壳上限定向放宽1320px；正文、表单、媒体、弹窗自己的行长不全局替换。精选/全部/热点/收藏按现有内容容器断点适配，不增加列或组件。
- 验证1440桌面、390移动、1920宽布局、reduced motion，另做768/769/1000几何边界。核对动画交接、过渡resize、菜单间距、已有页面溢出、浮层/Canvas/吸顶/历史恢复。运行相关聚焦检查、lint、production build。
- [x] 实现并自检；[x] 独立源码审查；[x] 验收文档；[ ] main提交并push。证据见docs/pulse-paper-width-verification-2026-11-01.md。

## Task 2：日报源码复用与集成

- 完整实现/daily、/daily/:key、/daily/archive；保留原日报/周报/月报切换，周报/月报暂禁用并以原生title提示。
- 真实来源为D:/AIHOT的routes/report-latest、report-detail、daily-archive，features/report全部组件、format，OutlineSheet和PhoneBar，以及契约/路由/后端reports相关代码。逐项保留原报头、Nameplate、Halftone、IssueDots、统计带、头条、今日看点、本期版面、Rows/Story、来源头像、一手/跟进、otherSources/related、原文、快讯、Neighbours与刊尾，及所有原条件分支。
- 日报净容器>=1240px显示280px归档栏和原正文左右各40px内边距；更窄使用原近期日期条/目录抽屉。正文自身保留原520/560/640/760/880/1040内容断点；手机极窄容器仅做必要尺寸/排列约束，不删组件。
- 栏目映射依次为product产品发布与更新、practice警务实战应用、paper论文研究进展、law法制政策动态、embodied具身智能装备、public-opinion舆情治理观察、low-altitude低空警务应用。服务端提供栏目与顺序，前端不计算热度、不补齐栏目。
- 保留leadStoryOf/pagesOf/outline的头条移出正文、跨栏去重、空栏过滤和连续编号，目录与正文共用计算。p0作为滚动/吸顶/锚点/目录当前项根；复用Sheet、IntentLink、加载条、导航、浏览器位置恢复。新路由接入共享route parser和意图预取。
- 精确GET同源/api/bluepulse/site/reports/daily到FastAPI/api/v1/site/reports/daily：根索引、latest-page、:key、navigation/:key、months/:month。不开放任意reports/*或新写接口。
- 保留ReportDetail、ReportCitation、ReportIndexEntry/Response、ReportLatestPage、ReportNavigationEntry/Response全部字段，包括可空/可选字段、封面srcSet/尺寸/caption、otherSources、related、followUp、firstParty、available。文章链接适配/articles/UUID。
- 普通模式区分未接入、未发布、合法空结果与故障；只有显式?mock=1演示，演示与live缓存/浏览器状态隔离，不增加演示标题或说明组件。缓存最多16项，索引/最新刊本地上限60s、详情120s，复合请求取最早上游截止，no-store/no-cache不复用；30min仅恢复位置。刷新/重试强制重取，旧请求不可覆盖新路由。
- 验证实际组件对照、仅头条/空栏/重复/快讯/跟进/撤回/图片失败/月加载/前后期/目录定位/缺刊/重试/缓存截止，以及桌面移动reduced motion；运行聚焦检查、lint和build。
- [ ] 实现并自检；[ ] 原源码与代码质量独立审查；[ ] 文档与验收；[ ] main提交并push，消息为“完成’AI日报‘页搭建”。

## 后端参考文档与真实状态

在dock.md追加DOCK-008及索引，遵循原七节格式。明确文档是供队友参考的机制说明、接口消费约定与检查清单，不限定内部表结构或算法实现。记录源码→复用→Pulse适配→验证；同步README、aihot-understanding和backend-stage-map。

必须重新核对edition.ts、compose.ts、correct.ts、publication/reports.ts、events/hot.ts、publication/scope/representative、taxonomy及schedules：日报规则编排不直接调用模型；每日08:00前24h窗口；确认/释放归刊；前7个自然日记忆（不是最后7期）；Fact/Story/独立参与方与代表；官方补选；importance公式、官方加5、跟进减6；每源2/正文12/快讯10；全是跟进时仍有正文；空栏不是每栏独立热度门槛；平静与上游没评判；幂等补刊与显式修订；撤回、封面许可与统计不同口径。六槽首页不冒充日报。警务分类与未分类归属、权威/转载矩阵须领域适配。

保留AIHOT MIT和Copyright (c) 2026 数字生命卡兹克。正常入口不伪造正式刊期，真实日报后端仍待队友实现和联调。
