# GSAP 闭合 SVG 描边动画方法论

本文给出一套可重复使用的闭合 SVG 描边动画工作流：导入 SVG，确认每个轮廓确实闭合，保留原始几何参数，再用 GSAP `DrawSVGPlugin` 从零绘制、停留并淡出。

文中的主模板适用于 Next.js / React，后半部分提供等价的原生 HTML / CSS / JavaScript 模板。当前项目可对照以下文件理解最终效果：

- [原始 Logo：qlxf.svg](./qlxf.svg)
- [基础描边参考：SVG描边动画.html](./SVG描边动画.html)
- [当前 React 实现：src/app/page.tsx](./src/app/page.tsx)
- [当前首帧与布局样式：src/app/globals.css](./src/app/globals.css)

---

## 1. 核心结论

一套稳定的 SVG 描边动画只需要遵守六条规则：

1. 保留原始 `viewBox` 和所有路径坐标，不重新描摹或随意压缩 `d`。
2. 一个需要独立控制的闭合轮廓对应一个 SVG 几何元素。
3. `<path>` 的每个子路径都应使用 `Z` 或 `z` 明确闭合。
4. 首屏先用 CSS 隐藏描边，再由 GSAP 接管，避免 hydration 前闪现完整图形。
5. 使用 `DrawSVGPlugin` 根据真实路径长度控制 dash，不手写固定长度。
6. 用一条 GSAP timeline 编排绘制、停留、淡出和循环，不使用散落的 `delay`。

最常用的时间线结构是：

```text
0.0s                 drawDuration        holdDuration       fadeDuration
|-------------------------|-------------------|-------------------|
       绘制全部轮廓              完整状态停留             整体淡出
```

---

## 2. 支持范围

### 2.1 可以直接使用的图元

`DrawSVGPlugin` 可以测量并绘制下列带有可见 `stroke` 的 SVG 元素：

| 图元 | 是否天然闭合 | 建议 |
| --- | --- | --- |
| `<path>` | 取决于每个子路径是否以 `Z/z` 结束 | 最适合复杂 Logo；一个轮廓一个 path |
| `<circle>` | 是 | 可以直接使用，也可转成 path |
| `<ellipse>` | 是 | 可以直接使用，也可转成 path |
| `<rect>` | 是 | 可以直接使用；圆角矩形也适用 |
| `<polygon>` | 是 | 可以直接使用 |
| `<polyline>` | 否 | 先改为 polygon 或闭合 path |
| `<line>` | 否 | 适合开放线段，不属于本文的闭合轮廓场景 |

### 2.2 必须先规范化的内容

以下内容不能直接视为“闭合轮廓描边”：

- `<text>`：字体与排版不是稳定路径，应先在设计工具中转轮廓。
- `<use>`：它只是引用，先展开为实际几何元素。
- `<image>`：位图没有可供 DrawSVG 绘制的矢量边界。
- 依赖 `filter`、mask 或阴影产生的视觉边界：效果边缘不等于路径。
- 只有 `fill`、没有明确轮廓的复杂图形：先确定需要绘制的是哪一条边界。
- 一个 `<path>` 内包含多个 `M ... Z` 子路径：先拆成多个独立 path。

---

## 3. 什么叫“闭合”

### 3.1 `Z/z` 才是明确的路径闭合语义

下面两条路径肉眼可能完全一样，但语义不同：

```svg
<!-- 明确闭合：最后的 Z 会从当前点连回本子路径起点。 -->
<path d="M10 10 L90 10 L90 90 L10 90 Z" />

<!-- 只是最后一个坐标碰巧等于起点，没有 close-path 命令。 -->
<path d="M10 10 L90 10 L90 90 L10 90 L10 10" />
```

第二条在视觉上闭合，但端点、线帽、连接方式和后续路径处理仍可能按开放路径工作。通用模板要求 `<path>` 的每个子路径都使用 `Z/z`。

### 3.2 一个 path 可能包含多个子路径

```svg
<path d="M10 10 ... Z M40 40 ... Z" />
```

这里存在两个闭合子路径。DrawSVG 会把它们视为同一元素的总长度，绘制游标可能从第一个子路径跳到第二个子路径。若它们需要同时开始、分别控制或保持清晰的绘制起点，应拆成两个 `<path>`。

### 3.3 绘制方向由路径数据决定

- `M` 定义绘制起点。
- 后续命令顺序定义绘制方向。
- `Z` 从当前点回到当前子路径的 `M` 起点。
- 需要反向绘制时，应在矢量工具中反转路径方向，或将 DrawSVG 的可见区间从末端向前动画。

### 3.4 贝塞尔曲率必须保留

三次贝塞尔命令：

```text
C control1X control1Y control2X control2Y endX endY
```

两个控制点共同决定曲线离开当前点、接近终点时的切线和弯曲程度。修改或取整控制点会改变 Logo 曲率。生产实现应把完整 `d` 当作几何真值，而不是手工重建坐标表。

常见路径命令：

| 命令 | 含义 | 参数重点 |
| --- | --- | --- |
| `M/m` | 移动到子路径起点 | x, y |
| `L/l` | 直线 | 终点 x, y |
| `H/h` | 水平直线 | 终点 x |
| `V/v` | 垂直直线 | 终点 y |
| `C/c` | 三次贝塞尔 | 两个控制点和一个终点 |
| `S/s` | 平滑三次贝塞尔 | 一个控制点和一个终点 |
| `Q/q` | 二次贝塞尔 | 一个控制点和一个终点 |
| `A/a` | 椭圆弧 | 半径、旋转、弧标志、终点 |
| `Z/z` | 闭合当前子路径 | 无参数 |

大写命令使用绝对坐标，小写命令使用相对坐标。两种写法都可被 DrawSVG 正确测量，不需要为了动画强制改成同一种写法。

---

## 4. 为什么描边会像“被画出来”

SVG 描边动画的基础是两个属性：

- `stroke-dasharray`：定义实线段和空白段的长度。
- `stroke-dashoffset`：移动 dash 图案在路径上的起始位置。

原生实现通常先调用 `getTotalLength()`，把可见实线段隐藏到路径之外，再把偏移量动画回零。`DrawSVGPlugin` 封装了这套逻辑，并处理路径、圆、矩形、多边形、缩放和浏览器差异。

```js
gsap.set(paths, { drawSVG: "0 0" });
gsap.to(paths, {
  drawSVG: "0 100%",
  duration: 1.8,
  ease: "power1.inOut",
});
```

`drawSVG: "0 0"` 表示路径上没有可见区间；`drawSVG: "0 100%"` 表示完整路径可见。闭合轮廓仍然有一个由 `M` 决定的绘制起点。

---

## 5. SVG 资产登记表

导入新 SVG 后，先登记资产，再写动画。建议至少记录：

| 字段 | 说明 |
| --- | --- |
| 文件 | 源文件路径和版本 |
| `width` / `height` | 原始画布尺寸；可保留作记录 |
| `viewBox` | 响应式缩放的坐标系统，必须保留 |
| 图元数量 | path、circle、rect、ellipse、polygon 的数量 |
| 轮廓 ID | 每个独立轮廓的稳定名称 |
| 起点 | path 的首个 `M/m` 坐标 |
| 命令组成 | L、C、A、Z 等命令的数量 |
| 子路径数量 | `M/m` 的数量 |
| 闭合数量 | `Z/z` 的数量；闭合 path 应与子路径数一致 |
| transform | 元素或祖先 group 上是否有变换 |
| fill-rule | `nonzero` 或 `evenodd`；若以后恢复填充尤其重要 |
| 路径长度 | 在浏览器中通过 `getTotalLength()` 或插件测量 |
| 原始 `d` | 生产几何真值，不手工改写 |

### 5.1 当前 `qlxf.svg` 登记示例

| 项目 | 值 |
| --- | --- |
| 画布 | `3621 × 4252` |
| viewBox | `0 0 3621 4252` |
| fill | `none` |
| 独立轮廓 | 3 个 `<path>` |
| transform | 无 |
| 轮廓 1 | 起点 `M129.156 797`；2 个 `C`；1 个 `Z` |
| 轮廓 2 | 起点 `M936 2315`；1 个 `L`；4 个 `C`；1 个 `Z` |
| 轮廓 3 | 起点 `M1764 67`；6 个 `L`；20 个 `C`；1 个 `V`；1 个 `Z` |

精确路径长度应由浏览器测量，不要根据坐标手算。把 SVG 挂载到页面后，在控制台执行：

```js
const drawables = [
  ...document.querySelectorAll(
    "path, circle, ellipse, rect, polygon, polyline, line",
  ),
];

console.table(
  drawables.map((element, index) => ({
    index: index + 1,
    id: element.id || "(no id)",
    tag: element.tagName.toLowerCase(),
    length: Number(element.getTotalLength().toFixed(3)),
  })),
);
```

也可以使用插件的测量接口：

```js
const length = DrawSVGPlugin.getLength(document.querySelector("#contour-1"));
console.log(length);
```

---

## 6. 导入任意闭合 SVG 的规范化流程

### 第一步：保存不可变的原始文件

保留一份未经修改的 SVG。后续所有清理工作在副本上进行，避免无法追溯坐标、曲率或设计工具导出差异。

### 第二步：确认 `viewBox`

推荐结构：

```svg
<svg
  viewBox="minX minY width height"
  preserveAspectRatio="xMidYMid meet"
  xmlns="http://www.w3.org/2000/svg"
>
  <!-- 独立轮廓 -->
</svg>
```

`viewBox` 决定内部坐标系。响应式显示应调整 SVG 的 CSS 宽高，而不是批量修改路径坐标。

### 第三步：清除非必要导出噪声

可以删除设计工具元数据、无用 class 和空 group，但不要删除仍被以下内容引用的节点：

- `clipPath`
- mask
- gradient
- filter
- `<use href="...">`

若目标最终只有纯描边，优先把结构整理为直接可见的几何元素。

### 第四步：展开引用和文字

- 把 `<use>` 展开成真实 path 或基础图元。
- 把 `<text>` 转换为轮廓。
- 若文字转换后一个字产生多个闭合轮廓，应按需要拆开，而不是继续把整行文字当成一个 path。

### 第五步：处理 transform

有两种合法策略：

1. 保留 group/元素 transform，并让 SVG 在页面中等比缩放。
2. 在设计工具中把 transform 烘焙进坐标，导出无 transform 的最终路径。

第二种更容易审计。不要删除 transform 却不更新坐标，否则图形会移动、旋转或改变尺寸。

当使用 `vector-effect="non-scaling-stroke"` 时，应保持等比缩放。非等比缩放会让路径长度和屏幕描边之间的关系变复杂。

### 第六步：拆分复合 path

每个 `M/m` 会开始一个新子路径。若一个 `d` 含有多组 `M ... Z`，在设计工具中释放复合路径，或使用可靠的 SVG path 解析器拆分。不要用简单字符串切割处理科学计数法、相对命令或隐式命令。

推荐结果：

```svg
<path id="contour-1" d="M...Z" />
<path id="contour-2" d="M...Z" />
<path id="contour-3" d="M...Z" />
```

### 第七步：确认所有轮廓闭合

对 path，检查每个子路径都有对应的 `Z/z`。对 `circle`、`ellipse`、`rect` 和 `polygon`，闭合是图元语义的一部分。

下面的浏览器脚本适合做快速审计：

```js
const paths = [...document.querySelectorAll("path")];

console.table(
  paths.map((path, index) => {
    const d = path.getAttribute("d") || "";
    const subpathCount = (d.match(/[Mm]/g) || []).length;
    const closeCount = (d.match(/[Zz]/g) || []).length;

    return {
      index: index + 1,
      id: path.id || "(no id)",
      subpathCount,
      closeCount,
      explicitlyClosed: subpathCount > 0 && subpathCount === closeCount,
      length: Number(path.getTotalLength().toFixed(3)),
    };
  }),
);
```

这是快速审计，不是 SVG 语法解析器。复杂或来源不明的 SVG 应使用结构化 XML 与 path parser 验证。

### 第八步：统一描边属性

```svg
<path
  d="M...Z"
  fill="none"
  stroke="#D5AF86"
  stroke-width="3"
  stroke-linecap="round"
  stroke-linejoin="round"
  vector-effect="non-scaling-stroke"
/>
```

- `fill="none"`：只展示绘制线条。
- `round / round`：让起点、闭合接缝和转角更自然。
- `non-scaling-stroke`：Logo 响应式缩放时保持接近固定的屏幕线宽。

如果品牌图形要求锐利尖角，可改成 `stroke-linejoin="miter"`，并根据需要设置 `stroke-miterlimit`。

---

## 7. 统一动画参数

建议每个项目只维护一份配置：

| 参数 | 示例值 | 作用 |
| --- | --- | --- |
| `background` | `#353330` | 页面和舞台背景 |
| `stroke` | `#D5AF86` | Logo 描边色 |
| `strokeWidth` | `3` | 使用 non-scaling-stroke 时近似屏幕像素宽度 |
| `drawDuration` | `1.8` | 绘制时长，单位秒 |
| `holdDuration` | `0.6` | 完整状态停留时间 |
| `fadeDuration` | `0.6` | 整体淡出时间 |
| `drawEase` | `power1.inOut` | 绘制缓动 |
| `fadeEase` | `power1.out` | 淡出缓动 |
| `stagger` | `0` | 0 为同步；大于 0 为轮廓错峰 |
| `repeat` | `0` | 0 播放一次；-1 无限循环 |
| `repeatDelay` | `0.5` | 循环之间的空白时间 |
| `width` / `height` | `76vw` / `76vh` | SVG 响应式画布范围 |

若轮廓长度差异很大，同样的 `duration` 意味着每条路径在同一时间完成，但长路径移动速度更快。这通常适合 Logo 同步成形。若需要相同线速度，应根据各轮廓长度分别计算 duration。

---

## 8. Next.js / React 完整模板

安装依赖：

```bash
pnpm add gsap @gsap/react
```

### 8.1 `ClosedSvgDraw.tsx`

下面的示例可以直接运行。替换新 Logo 时，只需修改 `viewBox` 与 `CLOSED_PATHS`，并按视觉要求调整 `DRAW_CONFIG`。

```tsx
"use client";

import { useRef, type CSSProperties } from "react";
import { useGSAP } from "@gsap/react";
import { gsap } from "gsap";
import { DrawSVGPlugin } from "gsap/DrawSVGPlugin";

gsap.registerPlugin(DrawSVGPlugin, useGSAP);

type ClosedPath = {
  id: string;
  d: string;
};

const DRAW_CONFIG = {
  viewBox: "0 0 100 100",
  background: "#353330",
  stroke: "#D5AF86",
  strokeWidth: 3,
  drawDuration: 1.8,
  holdDuration: 0.6,
  fadeDuration: 0.6,
  drawEase: "power1.inOut",
  fadeEase: "power1.out",
  stagger: 0,
  repeat: 0,
  repeatDelay: 0.5,
  width: "76vw",
  height: "76vh",
} as const;

const CLOSED_PATHS: ClosedPath[] = [
  {
    id: "outer-contour",
    d: "M10 10 H90 V90 H10 Z",
  },
  {
    id: "inner-contour",
    d: "M50 25 C63.807 25 75 36.193 75 50 C75 63.807 63.807 75 50 75 C36.193 75 25 63.807 25 50 C25 36.193 36.193 25 50 25 Z",
  },
];

export default function ClosedSvgDraw() {
  const rootRef = useRef<HTMLElement>(null);
  const logoRef = useRef<SVGSVGElement>(null);

  useGSAP(
    () => {
      const logo = logoRef.current;
      const paths = gsap.utils.toArray<SVGPathElement>(
        ".closed-svg-draw__path",
      );

      if (!logo || paths.length === 0) {
        return;
      }

      const reduceMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)",
      ).matches;

      if (reduceMotion) {
        gsap.set(logo, { autoAlpha: 1 });
        gsap.set(paths, { drawSVG: "0 100%" });
        return;
      }

      const timeline = gsap.timeline({
        repeat: DRAW_CONFIG.repeat,
        repeatDelay: DRAW_CONFIG.repeatDelay,
      });

      timeline
        .set(logo, { autoAlpha: 1 }, 0)
        .fromTo(
          paths,
          { drawSVG: "0 0" },
          {
            drawSVG: "0 100%",
            duration: DRAW_CONFIG.drawDuration,
            ease: DRAW_CONFIG.drawEase,
            stagger: DRAW_CONFIG.stagger,
          },
          0,
        )
        .to({}, { duration: DRAW_CONFIG.holdDuration })
        .to(logo, {
          autoAlpha: 0,
          duration: DRAW_CONFIG.fadeDuration,
          ease: DRAW_CONFIG.fadeEase,
        });

      return () => timeline.kill();
    },
    { scope: rootRef },
  );

  const stageStyle = {
    backgroundColor: DRAW_CONFIG.background,
    "--closed-svg-width": DRAW_CONFIG.width,
    "--closed-svg-height": DRAW_CONFIG.height,
  } as CSSProperties;

  return (
    <main
      ref={rootRef}
      className="closed-svg-draw"
      style={stageStyle}
      aria-label="Logo animation"
    >
      <svg
        ref={logoRef}
        className="closed-svg-draw__svg"
        viewBox={DRAW_CONFIG.viewBox}
        preserveAspectRatio="xMidYMid meet"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        {CLOSED_PATHS.map((path) => (
          <path
            key={path.id}
            id={path.id}
            className="closed-svg-draw__path"
            d={path.d}
            fill="none"
            stroke={DRAW_CONFIG.stroke}
            strokeWidth={DRAW_CONFIG.strokeWidth}
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        ))}
      </svg>
    </main>
  );
}
```

如果 SVG 使用 `circle`、`ellipse`、`rect` 或 `polygon`，可以把它们直接写进同一 `<svg>`，给它们相同 class，并让选择器同时匹配。复杂项目更推荐先统一转成独立 path，以简化数据管理。

### 8.2 配套 CSS

```css
:root {
  --closed-svg-background: #353330;
}

html,
body {
  width: 100%;
  height: 100%;
  margin: 0;
  overflow: hidden;
  background: var(--closed-svg-background);
}

.closed-svg-draw {
  display: grid;
  width: 100vw;
  height: 100vh;
  place-items: center;
  overflow: hidden;
}

.closed-svg-draw__svg {
  display: block;
  width: var(--closed-svg-width);
  height: var(--closed-svg-height);
  overflow: visible;
}

.closed-svg-draw__path {
  /* 在 React hydration 和 GSAP 初始化之前保持零可见长度。 */
  stroke-dasharray: 0 999999;
  stroke-dashoffset: 0;
}

@media (prefers-reduced-motion: reduce) {
  .closed-svg-draw__path {
    /* 无 JavaScript 时也展示完整静态 Logo。 */
    stroke-dasharray: none;
  }
}
```

### 8.3 React 模板的关键点

- 文件必须是 Client Component，因为 GSAP 需要 DOM 与浏览器 API。
- 在创建任何 tween 之前注册 `DrawSVGPlugin` 和 `useGSAP`。
- `scope: rootRef` 让字符串选择器只匹配当前组件内部。
- `useGSAP()` 会在卸载时恢复 context；模板另外 kill timeline，使所有权更明确。
- React Strict Mode 开发环境会检查 effect 生命周期；正确 cleanup 后不会残留重复时间线。
- reduced-motion 分支不绘制、不淡出，直接保留完整静态 Logo。

---

## 9. 原生 HTML / CSS / JavaScript 完整模板

下面的单文件示例与 React 模板使用同一套参数语义，可以直接保存为 HTML 打开。

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Closed SVG Draw</title>
    <style>
      :root {
        --draw-background: #353330;
        --draw-stroke: #d5af86;
        --draw-stroke-width: 3px;
        --draw-width: 76vw;
        --draw-height: 76vh;
      }

      * {
        box-sizing: border-box;
      }

      html,
      body {
        width: 100%;
        height: 100%;
        margin: 0;
        overflow: hidden;
        background: var(--draw-background);
      }

      .closed-svg-draw {
        display: grid;
        width: 100vw;
        height: 100vh;
        place-items: center;
        background: var(--draw-background);
      }

      .closed-svg-draw__svg {
        display: block;
        width: var(--draw-width);
        height: var(--draw-height);
        overflow: visible;
      }

      .closed-svg-draw__path {
        fill: none;
        stroke: var(--draw-stroke);
        stroke-width: var(--draw-stroke-width);
        stroke-linecap: round;
        stroke-linejoin: round;
        vector-effect: non-scaling-stroke;
        stroke-dasharray: 0 999999;
        stroke-dashoffset: 0;
      }

      @media (prefers-reduced-motion: reduce) {
        .closed-svg-draw__path {
          stroke-dasharray: none;
        }
      }
    </style>
  </head>
  <body>
    <main class="closed-svg-draw" aria-label="Logo animation">
      <svg
        class="closed-svg-draw__svg"
        viewBox="0 0 100 100"
        preserveAspectRatio="xMidYMid meet"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <path
          id="outer-contour"
          class="closed-svg-draw__path"
          d="M10 10 H90 V90 H10 Z"
        ></path>
        <path
          id="inner-contour"
          class="closed-svg-draw__path"
          d="M50 25 C63.807 25 75 36.193 75 50 C75 63.807 63.807 75 50 75 C36.193 75 25 63.807 25 50 C25 36.193 36.193 25 50 25 Z"
        ></path>
      </svg>
    </main>

    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/DrawSVGPlugin.min.js"></script>
    <script>
      gsap.registerPlugin(DrawSVGPlugin);

      const DRAW_CONFIG = {
        background: "#353330",
        stroke: "#D5AF86",
        strokeWidth: 3,
        drawDuration: 1.8,
        holdDuration: 0.6,
        fadeDuration: 0.6,
        drawEase: "power1.inOut",
        fadeEase: "power1.out",
        stagger: 0,
        repeat: 0,
        repeatDelay: 0.5,
        width: "76vw",
        height: "76vh",
      };

      const root = document.documentElement;
      const logo = document.querySelector(".closed-svg-draw__svg");
      const paths = gsap.utils.toArray(".closed-svg-draw__path");

      root.style.setProperty("--draw-background", DRAW_CONFIG.background);
      root.style.setProperty("--draw-stroke", DRAW_CONFIG.stroke);
      root.style.setProperty(
        "--draw-stroke-width",
        `${DRAW_CONFIG.strokeWidth}px`,
      );
      root.style.setProperty("--draw-width", DRAW_CONFIG.width);
      root.style.setProperty("--draw-height", DRAW_CONFIG.height);

      const reduceMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)",
      ).matches;

      if (reduceMotion) {
        gsap.set(logo, { autoAlpha: 1 });
        gsap.set(paths, { drawSVG: "0 100%" });
      } else {
        gsap
          .timeline({
            repeat: DRAW_CONFIG.repeat,
            repeatDelay: DRAW_CONFIG.repeatDelay,
          })
          .set(logo, { autoAlpha: 1 }, 0)
          .fromTo(
            paths,
            { drawSVG: "0 0" },
            {
              drawSVG: "0 100%",
              duration: DRAW_CONFIG.drawDuration,
              ease: DRAW_CONFIG.drawEase,
              stagger: DRAW_CONFIG.stagger,
            },
            0,
          )
          .to({}, { duration: DRAW_CONFIG.holdDuration })
          .to(logo, {
            autoAlpha: 0,
            duration: DRAW_CONFIG.fadeDuration,
            ease: DRAW_CONFIG.fadeEase,
          });
      }
    </script>
  </body>
</html>
```

生产环境中应把 GSAP 固定为项目依赖或固定 CDN 版本，不要使用无版本的 `latest` URL。

---

## 10. 常用编排方式

### 三条轮廓完全同步

```js
timeline.fromTo(
  paths,
  { drawSVG: "0 0" },
  { drawSVG: "0 100%", duration: 1.8, stagger: 0 },
);
```

### 轮廓依次绘制

```js
timeline.fromTo(
  paths,
  { drawSVG: "0 0" },
  { drawSVG: "0 100%", duration: 1.2, stagger: 1.2 },
);
```

### 轮廓错峰并行

```js
timeline.fromTo(
  paths,
  { drawSVG: "0 0" },
  { drawSVG: "0 100%", duration: 1.8, stagger: 0.18 },
);
```

### 从路径末端反向绘制

```js
timeline.fromTo(
  paths,
  { drawSVG: "100% 100%" },
  { drawSVG: "0% 100%", duration: 1.8 },
);
```

### 完成后保留 Logo

删除淡出 tween：

```js
timeline
  .fromTo(paths, { drawSVG: "0 0" }, { drawSVG: "0 100%", duration: 1.8 })
  .to({}, { duration: 0.6 });
```

### 无限循环

```js
const timeline = gsap.timeline({ repeat: -1, repeatDelay: 0.5 });
```

循环时必须在时间线起点恢复 SVG 的 `autoAlpha: 1`，并使用 `fromTo()` 恢复每条路径的起始 dash 状态。前面的完整模板已经包含这两项。

---

## 11. 常见故障与处理

### 11.1 首屏闪现完整 Logo

原因：React hydration 或脚本执行前，浏览器先按普通 stroke 渲染了 SVG。

处理：在 CSS 中提前设置：

```css
.closed-svg-draw__path {
  stroke-dasharray: 0 999999;
  stroke-dashoffset: 0;
}
```

不要只在 `useEffect` 或 `useGSAP` 中隐藏路径，因为那已经晚于浏览器首轮绘制。

### 11.2 描边完全看不见

依次检查：

1. 元素是否有非透明的 `stroke`。
2. `stroke-width` 是否大于 0。
3. `fill="none"` 是否符合预期。
4. path 的 `d` 是否有效。
5. `DrawSVGPlugin` 是否已注册。
6. SVG 或祖先是否为 `display: none`。

### 11.3 动画像是从不同位置突然跳转

常见原因是一个 `<path>` 含多个子路径。将每个 `M ... Z` 拆成独立 path，再决定同步或 stagger。

### 11.4 闭合位置出现缺口或尖刺

- 确认路径有 `Z/z`。
- 使用相同的 `stroke-linecap` 与 `stroke-linejoin`。
- 圆润效果使用 `round / round`。
- 锐角使用 `miter` 时检查 `stroke-miterlimit`。
- 检查最后一段曲线到闭合起点的切线是否符合设计。

### 11.5 响应式缩放后线条太粗或太细

需要固定屏幕视觉宽度时添加：

```svg
vector-effect="non-scaling-stroke"
```

需要线宽随 Logo 一起缩放时移除它，并用 viewBox 单位设置 `stroke-width`。

### 11.6 `getTotalLength()` 返回 0 或测量异常

- 确保 SVG 已挂载到 DOM。
- 不要在 `display: none` 的容器里测量。
- 确认几何元素不是空 path。
- 检查 transform 与非等比缩放。
- 测量前不要把元素从 DOM 移除。

隐藏初始状态应使用 dash 或 `visibility`，而不是让 SVG `display: none`。

### 11.7 Logo 位置或比例不正确

- 保留原始 `viewBox`。
- 使用 `preserveAspectRatio="xMidYMid meet"`。
- 检查祖先 group 和元素自身的 transform。
- 不要同时用 CSS 非等比拉伸宽高。

模板给 SVG 一个响应式 viewport，`meet` 会在其中完整、等比地放置 Logo。

### 11.8 React 开发环境播放两次

React Strict Mode 会验证 effect 的挂载和清理。如果旧时间线没有被回收，就会看到重叠或二次播放。

处理：

- 使用 `useGSAP()`。
- 设置 `scope`。
- 不在组件 render 阶段创建 tween。
- 若自行使用 `useEffect`，必须通过 `gsap.context()` 创建动画，并在 cleanup 中调用 `context.revert()`。

### 11.9 淡出后循环不再显示

时间线重复时，SVG 仍保留 `autoAlpha: 0`。在时间线 0 秒处加入：

```js
timeline.set(logo, { autoAlpha: 1 }, 0);
```

并使用 `fromTo()` 让 dash 每轮都回到零长度。

### 11.10 fill-rule 导致内部区域判断不同

`fill-rule` 不直接改变 stroke 路径，但会影响以后添加填充时洞和重叠区域的显示。导入复合 Logo 时记录并保留原值，常见值是 `nonzero` 与 `evenodd`。

---

## 12. 验收清单

### 资产

- [ ] 原始 SVG 已保留。
- [ ] `viewBox` 未改变。
- [ ] 每个需要独立控制的闭合轮廓都有稳定 ID。
- [ ] 每个 path 的所有子路径都有 `Z/z`。
- [ ] 多子路径 path 已拆分。
- [ ] `<use>` 已展开，文字已转轮廓。
- [ ] transform 已保留或正确烘焙进坐标。
- [ ] 原始 `d`、控制点和弧参数未被无意取整。

### 样式

- [ ] 页面首帧背景色正确。
- [ ] hydration 前不会闪现完整 Logo。
- [ ] `fill="none"`、stroke 色和 stroke-width 正确。
- [ ] linecap、linejoin 和闭合接缝符合设计。
- [ ] 桌面与移动端均完整显示且不裁切。

### 动画

- [ ] 插件在第一个 tween 前完成注册。
- [ ] 初始值为 `drawSVG: "0 0"`。
- [ ] 完整值为 `drawSVG: "0 100%"`。
- [ ] 同步、错峰或顺序绘制符合参数设置。
- [ ] 绘制、停留和淡出时长正确。
- [ ] 单次动画结束后不会意外重播。
- [ ] 循环动画每轮会恢复 opacity 与 dash 起点。
- [ ] reduced-motion 下直接显示完整静态 Logo。

### 生命周期与质量

- [ ] React 动画位于 Client Component。
- [ ] 选择器限制在组件 scope 内。
- [ ] 卸载后 timeline 被回收。
- [ ] 控制台无 GSAP 插件、选择器或 SVG 测量警告。
- [ ] 生产构建成功。

---

## 13. 更换新 Logo 时只改什么

使用本文模板时，通常只需要完成以下步骤：

1. 把新 SVG 的原始 `viewBox` 写入 `DRAW_CONFIG.viewBox` 或 `<svg viewBox>`。
2. 把每个闭合轮廓整理成一个独立元素。
3. 将各 path 的完整 `d` 原样放入 `CLOSED_PATHS`。
4. 调整背景色、描边色和线宽。
5. 选择同步、错峰或依次绘制，并设置 `stagger`。
6. 调整绘制、停留、淡出的时间。
7. 按验收清单检查首帧、闭合、缩放、清理和 reduced-motion。

不要为每个新 Logo 重写 dash 计算、定时器或生命周期逻辑。变化应该集中在 SVG 几何数据和 `DRAW_CONFIG`，动画骨架保持不变。

---

## 14. 推荐默认值

如果没有特殊设计要求，可以从以下默认值开始：

```js
const DRAW_CONFIG = {
  background: "#353330",
  stroke: "#D5AF86",
  strokeWidth: 3,
  drawDuration: 1.8,
  holdDuration: 0.6,
  fadeDuration: 0.6,
  drawEase: "power1.inOut",
  fadeEase: "power1.out",
  stagger: 0,
  repeat: 0,
  repeatDelay: 0.5,
};
```

这组参数适合简洁的品牌开场：轮廓同时成形、短暂停留、整体淡出，之后保持纯色背景。
