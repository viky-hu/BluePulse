# p0 左上角斜线保留与验证

日期：2026-11-01。分支：`main`。

## 原实现与调整

封面的 `WhitePaper` 已独立绘制左上角斜线，`InitialIntro.syncPanel` 也已让其随 p0 的边界移动；主页面 `MainScene` 原先只有绿色底板和白纸矩形，封面卸载后斜线随之消失。

将原有尺寸公式抽为 `getWhitePaperStapleGeometry`，供封面绘制、过场定位与主页面共同使用。主页面通过独立的 50 × 50 SVG 显示斜线，沿用封面的灰色、1.6px 线宽、圆端和 40° 倾角。SVG 固定在白纸左上角、位于正文之上，忽略指针事件，不随正文滚动或菜单切换而移动。

窗口及 visualViewport 尺寸变化时，使用与封面一致的视口和原 p0 宽度重新计算斜线；事件回调由 scoped useGSAP 管理，卸载时移除监听。原有时间轴、白纸和菜单布局未调整。

## 验证结果

- `pnpm lint`：通过。
- `pnpm build`：通过。
- `node --experimental-strip-types scripts/intro-config.test.mjs`：通过。
- `node --experimental-strip-types scripts/paper-staple-browser-test.mjs`：8 项检查通过，无浏览器运行错误。修复前，该脚本在“主页面必须保留一条斜线”的断言处失败。
- 1440 × 900 桌面、390 × 844 移动端，分别覆盖正常及减少动态效果：直达、实际正文滚动、刷新、菜单切换与首次入场交接。
- 正常动效中途分别调整到 1000 × 800、430 × 800：最终封面斜线与主页面斜线的端点误差小于 1px；采样帧中斜线持续可见。
- 浏览器截图与结构化结果位于被 Git 忽略的 `test-results/paper-staple/`，使用本地 mock 和隔离生产服务器，无外部采集或模型调用。

此次仅调整共享前端装饰，不涉及业务接口。原有未提交的日报等工作保留。
