# 主场景扩宽与既有内容页适配验收

2026-11-01，直接在main完成已批准计划的第一阶段。本阶段只调整共享场景和页面外层几何，不实施日报业务，不修改FastAPI、不触发采集或模型。

## 实际变更

- 共享壳集中定义菜单左2.8vw、宽clamp(220px,18vw,280px)，纸左max(23vw,菜单右沿+16px)、绿左纸左减2.5vw；绿色右留白保持1.470588235vw，纸右留白3.470588235vw。769–1000px旧菜单25%覆盖移除。
- 移动绿色左右取10px和安全区较大值，纸张再内缩8px。原垂直边界、绿层、白纸阴影、菜单组件和动效保留。
- MainScene提供绿色和白纸SVG refs，经MainShell/RootEntry传入InitialIntro。main-scene-geometry使用逆screen CTM把实际CSS矩形变成动画坐标；初始化/resize读取并缓存，逐帧只插值。删除intro-config里重复的终态数学公式，保留封面几何和所有时序/进度对象。
- 关于、共享阅读壳、搜索表单/结果和历史的页面级最大宽度1320px；基础旧feedSection保留920px，仅真实搜索结果应用新外壳。现有正文、表单、媒体和弹窗限制保留，未新增列或组件。
- 1440px视口净内容宽度约943.6px；1920约1291.8px；390移动约324px。结果未计入浏览器占位滚动条差异。

## 验证证据

以下命令在最后实现上执行通过：

```text
pnpm lint
pnpm build
node --test scripts/intro-config.test.mjs scripts/white-paper-config.test.mjs scripts/home-view-transition.test.mjs
node scripts/paper-width-browser-test.mjs
```

三组已有逻辑脚本通过。新增48组聚焦浏览器检查通过：1440/1920/390检查全部14个现有阅读/状态入口的纸张与内容frame一致、菜单安全边距、绿边和横向溢出；768/769/1000检查边界；另检查reduced-motion和过渡中resize的最后SVG帧到CSS稳定态交接（误差小于2px）、刷新后不重播封面。关于页另确认Canvas真实像素已绘制，避免用入场未完成的空白截图验收。没有浏览器pageerror。

测试通过独立生产Next服务和本地HTTP fixture运行，截图及结果位于被忽略的test-results/paper-width/。人工查看1440热点、390全部动态、1920关于页截图；已有组件、品牌、绿垫/白纸结构保留。测试服务没有连接真实采集或模型。

独立只读代码审查与限定修订复审均通过规格符合性/代码质量检查。审查建议搜索外壳单独限定，已落实；审查没有自行重跑浏览器，不将它当作第二份运行证据。

## 依据与边界

遵守AGENTS、README及原SVG/GSAP实现，使用本地Next16文档和GSAP React/core实践。已有页面继续以AIHOT真实移植组件为主；这里只改变承载尺寸。扩宽不证明热点、日报或事件后端已实现，也不扩大已有业务的验证结论。Node的既有MODULE_TYPELESS_PACKAGE_JSON提示未通过改包配置消除。

后续日报约定：以扣除共享内边距后的净容器1240px开启280px归档栏及正文左右各40px内边距，不按浏览器lg断点开启。
