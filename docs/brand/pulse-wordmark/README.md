# Pulse 定制字标

2026-10-27：用户选定 **C · 波形**，评价为“简约大气”。三稿均为手工绘制的闭合 Bézier 字形轮廓，没有将某款字体直接转曲；没有复用 AIHOT 的品牌图形。设计参考来自 Pulse 的信息流动主题和既有青绿色界面。

## 定稿文件

- `pulse-wordmark.svg`：青绿色 `#176b75`，透明背景，首选矢量文件。
- `pulse-wordmark-black.svg`：纯黑 `#000000`，透明背景。
- `pulse-wordmark-white.svg`：纯白 `#ffffff`，透明背景，需置于深色背景查看。
- `pulse-wordmark.png`：透明背景青绿色 PNG，4224 × 1152，供不能接收 SVG 的场景使用。
- `selected.png`：C 定稿展示图。

字标保持 Pulse 大小写，采用轻微前倾、开放字腔和稳定基线。P、u、l、s、e 是独立闭合轮廓；C 的前倾由 SVG 内的矩阵完成。原始 `viewBox="0 12 528 144"` 应保留，显示时按比例缩放，不拉伸字形。

所有 SVG 仅含标题、分组和路径，无文字节点、字体依赖、脚本或外部图片。根元素的 `color` 决定 `currentColor` 填充；内联使用时可通过 CSS 设置 `color`，以 `<img>` 引入时使用对应配色文件。白色版本在白底上不可见是预期行为。

## 对比与保留稿

打开 `preview.html` 查看三稿原大字形、24px 高度 SVG 的菜单应用、纯黑和反白效果。`comparison.png` 为桌面对比，`mobile.png` 为移动端长图，`detail-a.png` 至 `detail-c.png` 为单稿细节。

- A · 连动：u–l 连笔和回环升部，保留作探索稿。
- B · 回响：独立字母、重复圆弧，保留作探索稿。
- C · 波形：轻微前倾与曲线张弛，已选定。

对应 `pulse-a-linked.svg`、`pulse-b-echo.svg`、`pulse-c-wave.svg`，每稿附 `-black`、`-white` 版本。主文件与 C 候选稿轮廓完全一致。

预览说明文字读取仓库本地 Google Sans，中文回退微软雅黑；这不影响字标自身。菜单仅用于尺寸与视觉示意，并非对网站菜单的替换。

## 再生成

源路径与预览生成器位于 `scripts/create-pulse-wordmark-artifacts.mjs`：

```powershell
node scripts/create-pulse-wordmark-artifacts.mjs
```

生成 PNG 与执行浏览器检查需要本地 Playwright；没有引入项目运行依赖：

```powershell
$env:PULSE_PLAYWRIGHT_MODULE = 'C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright\index.mjs'
node scripts/create-pulse-wordmark-artifacts.mjs --render
```

## 验证与交付边界

三稿均已检查轮廓闭合、路径处于 viewBox 内、24px 菜单尺寸、桌面 1560px 与移动端 390px 的无横向溢出，以及 reduced-motion 下的完整静态呈现。PNG 另经过人工视觉检查。

`pnpm lint`、`pnpm build` 均通过（退出 0）。12 份 SVG 均通过 XML 解析；定稿主 SVG 与 C 候选 SVG 哈希一致。

独立设计阶段仅交付字标资产。随后用户明确要求接入网站，并确认用现有 `qlxf.svg` 作为字标前面的图形：共享菜单现使用 `public/logo.svg` 与 `public/pulse-wordmark.svg`，分别显示为 32px 高的青绿色图形、24px 高的 C 稿字标，间距 10px；移除早期圆点和普通字体站名。

`public/logo.svg` 仅将原 qlxf 图形适配为青绿色实心皮肤，保留 `0 0 3621 4252` viewBox、三条闭合路径及每条原始 d 值，并添加 `vector-effect="non-scaling-stroke"`。原始 `qlxf.svg` 和入口描边动画未改动。生产字标与 C 稿主 SVG 完全一致。

接入后 `pnpm lint`、`pnpm build` 通过；既有菜单响应式专项 5 项通过，新增一次性核对资产几何、桌面 1360×760、移动 390×844 及 reduced-motion 模式全部通过。两个 SVG 均加载成功，没有横向溢出或浏览器异常；已人工查看桌面和移动截图。浏览器产物位于被 Git 忽略的 `test-results/pulse-wordmark-integration/`。

未改动入口、favicon 或动画；不涉及后端接口。字体和图形资源没有新增网络依赖。
