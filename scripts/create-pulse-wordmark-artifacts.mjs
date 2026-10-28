// Original lettering, drawn as closed cubic Bézier contours. No font outlines.
// Run: node scripts/create-pulse-wordmark-artifacts.mjs
// Render: set PULSE_PLAYWRIGHT_MODULE to a local Playwright index.mjs, then add --render.
import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const root = fileURLToPath(new URL("../", import.meta.url));
const output = path.join(root, "docs/brand/pulse-wordmark");
const palette = { teal: "#176b75", black: "#000000", white: "#ffffff" };
const selectedId = "c-wave";
const candidates = [
  {
    id: "a-linked", letter: "A", name: "连动", subtitle: "让连接成为记忆点", recommended: true,
    description: "圆润的宽体结构，u 的收笔牵引至 l 的回环；字母间保留停顿，连而不黏。",
    detail: "u–l 连笔 / 回环升部 / 水平基线",
    viewBox: "0 12 520 144",
    glyphs: [
      { name: "P", d: "M14 150V14H68C102 14 121 32 121 60C121 89 100 108 68 108H36V150ZM36 35V87H66C87 87 99 77 99 60C99 44 88 35 67 35Z" },
      { name: "u-l ligature", d: "M136 58H158V111C158 127 165 135 178 135C194 135 203 123 203 104V58H225V109C225 116 226 122 229 126C236 113 241 96 246 75C249 62 250 47 250 35C250 20 258 12 270 12C282 12 288 21 288 34C288 58 276 83 269 97V119C269 131 273 136 283 136L289 135V150C286 152 281 153 277 153C264 153 255 148 251 138C245 148 237 153 227 153C218 153 210 148 207 139C198 149 188 154 174 154C149 154 136 138 136 113ZM269 68C275 54 278 40 278 31C278 27 276 25 274 25C271 25 269 29 269 35Z" },
      { name: "s", d: "M380 65C370 57 359 53 345 53C322 53 305 66 305 83C305 100 318 107 341 112L350 114C362 117 366 120 366 125C366 132 359 136 347 136C333 136 321 130 312 123L301 140C312 150 329 155 346 155C372 155 389 143 389 124C389 107 377 100 355 95L344 92C333 89 327 86 327 81C327 74 334 70 345 70C355 70 364 74 372 79Z" },
      { name: "e", d: "M502 105H429C431 124 443 136 461 136C474 136 484 132 494 125L505 141C493 151 478 155 460 155C428 155 407 134 407 104C407 74 427 53 456 53C485 53 503 73 503 100C503 102 503 103 502 105ZM430 88H480C478 76 470 71 456 71C443 71 434 77 430 88Z" },
    ],
  },
  {
    id: "b-echo", letter: "B", name: "回响", subtitle: "用曲线建立秩序", recommended: false,
    description: "五个字母彼此独立。P 的圆角内腔、u 的底弧与 e 的开口，重复同一套圆弧语言。",
    detail: "独立字母 / 重复圆弧 / 开放字腔",
    viewBox: "0 12 520 144",
    glyphs: [
      { name: "P", d: "M14 150V14H69C101 14 120 32 120 61C120 90 101 108 69 108H36V150ZM36 35V87H68C87 87 98 78 98 61C98 44 87 35 68 35Z" },
      { name: "u", d: "M137 56H159V108C159 126 167 135 181 135C197 135 207 123 207 105V56H229V150H208V137C200 148 189 155 175 155C150 155 137 138 137 112Z" },
      { name: "l", d: "M251 14H273V119C273 130 277 135 286 135H292V152C288 154 284 155 279 155C260 155 251 144 251 123Z" },
      { name: "s", d: "M387 65L377 81C367 74 357 71 348 71C336 71 329 75 329 82C329 88 336 91 350 94L360 96C382 101 394 109 394 125C394 144 377 155 351 155C333 155 316 150 304 141L314 124C326 132 338 137 351 137C365 137 372 133 372 126C372 120 366 117 352 114L341 112C319 107 307 99 307 83C307 65 323 53 348 53C363 53 377 57 387 65Z" },
      { name: "e", d: "M506 108H432C434 126 445 136 462 136C475 136 485 131 494 124L505 140C494 150 478 155 461 155C430 155 409 135 409 104C409 74 429 53 458 53C488 53 507 74 507 103C507 105 507 106 506 108ZM432 90H484C481 77 472 71 459 71C446 71 436 78 432 90Z" },
    ],
  },
  {
    id: "c-wave", letter: "C", name: "波形", subtitle: "静止时也有向前的动势", recommended: false,
    description: "轻微前倾，曲线略有张弛。u 的回升、s 的转折和 e 的出口接续成一段流动的节奏。",
    detail: "轻微前倾 / 曲线张弛 / 稳定基线",
    viewBox: "0 12 528 144", transform: "matrix(1 0 -0.10 1 15 0)",
    glyphs: [
      { name: "P", d: "M14 150V14H67C103 14 123 31 123 58C123 86 103 105 69 105H37V150ZM37 35V84H67C89 84 101 75 101 59C101 43 88 35 67 35Z" },
      { name: "u", d: "M137 58H159V108C159 125 164 135 178 135C195 135 207 121 207 101V58H229V122C229 131 232 136 239 137L235 153C222 153 213 147 210 138C201 149 189 155 174 155C149 155 137 139 137 114Z" },
      { name: "l", d: "M254 14H276V115C276 129 281 135 291 135L299 133L303 149C297 153 291 155 284 155C264 155 254 142 254 120Z" },
      { name: "s", d: "M391 65L381 81C371 74 361 71 351 71C339 71 331 75 331 82C331 88 338 90 352 93L363 96C386 102 398 111 398 126C398 144 380 155 355 155C335 155 317 149 305 138L317 122C328 131 342 137 355 137C367 137 376 133 376 126C376 119 366 116 353 113L343 110C321 104 309 97 309 83C309 65 327 53 351 53C366 53 381 57 391 65Z" },
      { name: "e", d: "M509 104H435C437 124 450 136 467 136C480 136 489 132 499 124L510 140C498 150 483 155 466 155C433 155 412 134 412 104C412 74 433 53 461 53C490 53 510 73 510 98C510 101 510 102 509 104ZM436 87H487C484 76 475 71 462 71C450 71 440 77 436 87Z" },
    ],
  },
];

function svg(candidate, color = palette.teal, className = "", decorative = false) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${candidate.viewBox}" color="${color}" fill="currentColor" fill-rule="evenodd"${className ? ` class="${className}"` : ""}${decorative ? ' aria-hidden="true"' : ` role="img" aria-label="Pulse — ${candidate.letter} · ${candidate.name}"`}>
  ${decorative ? "" : `<title>Pulse — ${candidate.letter} · ${candidate.name}</title>`}
  <g${candidate.transform ? ` transform="${candidate.transform}"` : ""}>
${candidate.glyphs.map(glyph => `    <path data-glyph="${glyph.name}" d="${glyph.d}"/>`).join("\n")}
  </g>
</svg>`;
}

await mkdir(output, { recursive: true });
for (const candidate of candidates) {
  for (const [colorName, color] of Object.entries(palette)) {
    await writeFile(path.join(output, `pulse-${candidate.id}${colorName === "teal" ? "" : `-${colorName}`}.svg`), `${svg(candidate, color)}\n`);
  }
}
const selected = candidates.find(candidate => candidate.id === selectedId);
for (const [colorName, color] of Object.entries(palette)) {
  await writeFile(path.join(output, `pulse-wordmark${colorName === "teal" ? "" : `-${colorName}`}.svg`), `${svg(selected, color)}\n`);
}

function card(candidate) {
  return `<article class="candidate" id="${candidate.id}">
    <div class="candidate-heading"><h2><span>${candidate.letter}</span> ${candidate.name}</h2>${candidate.id === selectedId ? '<span class="recommend">已选定稿</span>' : ""}</div>
    <div class="hero">${svg(candidate, palette.teal, "large-mark")}</div>
    <div class="concept"><h3>${candidate.subtitle}</h3><p>${candidate.description}</p><div class="construction">${candidate.detail}</div></div>
    <div class="application"><div class="eyebrow">菜单应用 <span>SVG 高度 24px · 原尺寸</span></div>
      <div class="menu-stage"><div class="menu-demo"><div class="menu-brand">${svg(candidate, palette.teal, "menu-mark")}</div>
        <div class="menu-search"><span class="search-icon" aria-hidden="true"></span>搜索<span class="shortcut">/</span></div>
        <div class="menu-group">内容</div><div class="menu-selected"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 5h14v11H3zM6 2v6M14 2v6M3 9h14"/></svg>精选</div>
      </div><div class="scale-note"><span>24</span>px<br>与现有菜单相同的<br>50px 品牌区</div></div>
    </div>
    <div class="color-section"><div class="eyebrow">单色检验 <span>相同轮廓 · 三种配色</span></div><div class="colors">
      <div class="swatch light">${svg(candidate, palette.black, "swatch-mark", true)}<span>纯黑 / 浅底</span></div>
      <div class="swatch teal">${svg(candidate, palette.teal, "swatch-mark", true)}<span>#176B75</span></div>
      <div class="swatch dark">${svg(candidate, palette.white, "swatch-mark", true)}<span>反白 / 深底</span></div>
    </div></div>
    <a class="download" href="pulse-${candidate.id}.svg" download>下载 ${candidate.letter} · SVG <span aria-hidden="true">↗</span></a>
  </article>`;
}

// The local UI font is only used by the specimen labels. The wordmarks are paths.
const fontUrl = "../../../src/app/fonts/GoogleSans-Variable.woff2";
const html = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Pulse — 定制字标 / 三稿对比</title>
<style>
@font-face { font-family: "Google Sans Local"; src: url("${fontUrl}") format("woff2"); font-weight: 400 700; font-display: swap; }
:root { color-scheme: light; --ink:#172a2d; --muted:#637170; --accent:#176b75; --paper:#f2f3ef; --line:#dde3dc; }
* { box-sizing:border-box; } body { margin:0; background:var(--paper); color:var(--ink); font-family:"Google Sans Local","Microsoft YaHei",sans-serif; -webkit-font-smoothing:antialiased; }
main { max-width:1680px; margin:auto; padding:50px 54px 30px; }
.topline { display:flex; justify-content:space-between; align-items:center; color:var(--accent); font-size:11px; letter-spacing:.1em; }
.edition { color:var(--muted); letter-spacing:0; }
header { margin:32px 0 32px; display:flex; align-items:end; justify-content:space-between; gap:30px; }
h1 { margin:0; font-size:42px; font-weight:400; line-height:1.25; letter-spacing:0; }
h1 span { color:#81908b; font-size:32px; margin:0 13px; }
.intro { color:var(--muted); margin:0 0 4px; font-size:12px; line-height:1.9; }
.grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:20px; }
.candidate { background:#fff; border:1px solid #dbe2da; min-width:0; padding:24px 24px 0; }
.candidate-heading { display:flex; align-items:center; justify-content:space-between; height:29px; }
h2 { font-size:17px; margin:0; font-weight:400; } h2 span { display:inline-block; margin-right:10px; color:var(--accent); font-size:14px; }
.recommend { padding:5px 8px; color:var(--accent); background:#eaf1ed; font-size:10px; }
.hero { height:200px; display:flex; align-items:center; justify-content:center; padding:0 4px; }
.large-mark { width:100%; height:auto; display:block; overflow:visible; }
.concept { min-height:130px; padding-bottom:22px; border-bottom:1px solid var(--line); }
h3 { margin:0 0 12px; font-size:15px; font-weight:500; } p { font-size:12px; line-height:1.9; }
.concept p { margin:0; color:var(--muted); min-height:46px; }
.construction { margin-top:14px; color:#88958e; font-size:10px; }
.eyebrow { display:flex; align-items:baseline; justify-content:space-between; gap:8px; font-size:11px; }
.eyebrow span { font-size:9px; color:var(--muted); }
.application { padding:24px 0; border-bottom:1px solid var(--line); }
.menu-stage { background:#eff1ec; margin-top:15px; display:flex; align-items:center; justify-content:center; gap:24px; padding:20px 14px; }
.menu-demo { width:180px; padding:10px 12px 12px; background:#fdfdfd; box-shadow:0 5px 16px #1422200a; flex:none; border:1px solid #2530260e; }
.menu-brand { height:50px; display:flex; align-items:center; padding-left:4px; }
.menu-mark { height:24px; width:auto; display:block; }
.menu-search,.menu-selected { height:34px; padding:0 10px; display:flex; align-items:center; gap:9px; font-size:12px; color:#526264; }
.menu-search { background:#eef1ed; border-radius:7px; margin-top:8px; }
.shortcut { margin-left:auto; color:#95a09b; font-size:11px; }
.search-icon { width:11px; height:11px; border:1.4px solid currentColor; border-radius:50%; position:relative; margin:0 3px 0 1px; }
.search-icon:after { content:""; position:absolute; width:4px; height:1.4px; background:currentColor; transform:rotate(45deg); right:-3px; bottom:-1px; }
.menu-group { padding:14px 10px 6px; font-size:9px; color:#7e8c86; }
.menu-selected { border-radius:7px; color:var(--accent); background:#176b7519; }
.menu-selected svg { width:16px; height:16px; fill:none; stroke:currentColor; stroke-width:1.3; }
.scale-note { color:#819087; font-size:9px; line-height:1.9; flex:none; }
.scale-note>span { font-size:24px; color:#46635f; }
.color-section { padding:24px 0; }
.colors { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); margin-top:15px; }
.swatch { height:98px; padding:23px 10px 11px; display:flex; flex-direction:column; justify-content:space-between; align-items:center; }
.swatch-mark { width:100%; max-width:106px; height:auto; }
.swatch span { color:#728078; font-size:8px; }
.light { background:#f4f5f1; }.teal { background:#e6eee8; }.dark { background:#172e31; }.dark span { color:#a9bdb8; }
.download { color:var(--muted); padding:16px 0; border-top:1px solid var(--line); text-decoration:none; display:flex; justify-content:space-between; font-size:11px; }
.download:hover { color:var(--accent); }.download:focus-visible { outline:2px solid var(--accent); outline-offset:3px; }
footer { display:flex; justify-content:space-between; gap:20px; color:#77857d; padding-top:22px; font-size:10px; line-height:1.8; }
@media(max-width:1100px) { main{padding:30px 24px;} .grid{gap:12px;} .candidate{padding:18px 16px 0;} .hero{height:165px;} .scale-note{display:none;} .menu-stage{padding:18px 8px;} .eyebrow{flex-wrap:wrap;} }
@media(max-width:720px) { main{padding:26px 18px;} .topline{font-size:9px;gap:14px;letter-spacing:.04em;} header{display:block;margin:27px 0 24px;} h1{font-size:30px;} h1 span{font-size:23px;margin:0 6px;} .intro{margin-top:14px;font-size:11px;} .grid{grid-template-columns:1fr;gap:20px;} .candidate{padding:22px 22px 0;} .hero{height:185px;} .concept{min-height:0;} .scale-note{display:block;} .menu-stage{gap:22px;} footer{display:block;} footer span{display:block;margin-top:6px;} }
@media(prefers-reduced-motion:reduce) { *,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important;} }
@media print { main{padding:12px;} a.download{display:none;} .candidate{break-inside:avoid;} }
</style></head><body><main>
<div class="topline"><span>BLUE PULSE / ORIGINAL LETTERING</span><span class="edition">字标探索 · 2026.10.27</span></div>
<header><h1>Pulse <span>/</span> 定制字标</h1><p class="intro">同一个名字，三种流动的方式。<br>原创字形轮廓 · 单色优先 · 独立设计提案</p></header>
<section class="grid" aria-label="三个字标候选方案">${candidates.map(card).join("\n")}</section>
<footer><span>手工 Bézier 轮廓，字标无需字体文件。菜单为尺寸应用示意。</span><span>已选 C · 波形 / 尚未接入网站</span></footer>
</main></body></html>`;
await writeFile(path.join(output, "preview.html"), html);
console.log("Generated three original wordmarks, nine candidate SVGs, three selected master SVGs, and preview.html.");

if (process.argv.includes("--render")) {
  const { chromium } = await import(process.env.PULSE_PLAYWRIGHT_MODULE ? pathToFileURL(process.env.PULSE_PLAYWRIGHT_MODULE).href : "playwright");
  const browser = await chromium.launch({ headless: true });
  const checks = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1560, height: 1120 }, deviceScaleFactor: 2 });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    const responseFailures = [];
    page.on("requestfailed", request => responseFailures.push(request.url()));
    await page.goto(pathToFileURL(path.join(output, "preview.html")).href);
    await page.evaluate(() => document.fonts.ready);
    assert.equal(await page.locator(".candidate").count(), 3);
    assert.equal(await page.locator(".menu-mark").evaluateAll(nodes => nodes.every(node => Math.abs(node.getBoundingClientRect().height - 24) < .1)), true);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    // SVG geometry must fit even when an exported file clips at its own viewport.
    for (const candidate of candidates) {
      const bounds = await page.locator(`#${candidate.id} .hero svg`).evaluate(node => {
        const box = node.querySelector("g").getBBox();
        const matrix = node.querySelector("g").transform.baseVal.consolidate()?.matrix;
        const corners = [[box.x, box.y], [box.x + box.width, box.y], [box.x, box.y + box.height], [box.x + box.width, box.y + box.height]].map(([x,y]) => {
          const point = new DOMPoint(x,y); return matrix ? point.matrixTransform(matrix) : point;
        });
        const view = node.viewBox.baseVal;
        return { fits: corners.every(p => p.x >= view.x && p.x <= view.x + view.width && p.y >= view.y && p.y <= view.y + view.height), width: box.width, height: box.height };
      });
      assert.equal(bounds.fits, true, `${candidate.id}: paths must remain inside viewBox`);
      const content = await readFile(path.join(output, `pulse-${candidate.id}.svg`), "utf8");
      assert.equal(/<(text|image|use|script|foreignObject)\b|(?:href|font-family)=/.test(content), false);
      assert.ok(candidate.glyphs.every(glyph => glyph.d.endsWith("Z")));
      checks.push(`${candidate.letter}: closed contours, self-contained SVG, geometry within viewBox, 24px menu specimen`);
    }
    await page.screenshot({ path: path.join(output, "comparison.png"), fullPage: true });
    for (const candidate of candidates) await page.locator(`#${candidate.id}`).screenshot({ path: path.join(output, `detail-${candidate.letter.toLowerCase()}.png`) });
    checks.push("1560px desktop: three columns, no horizontal overflow");
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    const boxes = await page.locator(".candidate").evaluateAll(nodes => nodes.map(node => ({ x: node.getBoundingClientRect().x, y: node.getBoundingClientRect().y })));
    assert.equal(boxes.every(box => box.x === boxes[0].x), true);
    assert.ok(boxes[1].y > boxes[0].y && boxes[2].y > boxes[1].y);
    await page.screenshot({ path: path.join(output, "mobile.png"), fullPage: true });
    checks.push("390px mobile: single-column layout, no horizontal overflow");
    await page.emulateMedia({ reducedMotion: "reduce" });
    assert.equal(await page.locator(".candidate").count(), 3);
    assert.equal(await page.locator("a[download]").count(), 3);
    assert.equal(await page.evaluate(() => document.getAnimations().length), 0);
    checks.push("reduced motion: all specimens and download links present, no animation");
    assert.deepEqual(errors, []);
    assert.deepEqual(responseFailures, []);
    await page.setViewportSize({ width: 2112, height: 576 });
    await page.setContent(`<html><head><style>html,body{margin:0;background:transparent}svg{display:block;width:2112px;height:576px}</style></head><body>${svg(selected)}</body></html>`);
    await page.screenshot({ path: path.join(output, "pulse-wordmark.png"), omitBackground: true });
    await page.setViewportSize({ width: 1400, height: 560 });
    await page.setContent(`<html lang="zh-CN"><head><style>@font-face{font-family:Local;src:url("${pathToFileURL(path.join(root, "src/app/fonts/GoogleSans-Variable.woff2")).href}")}*{box-sizing:border-box}body{margin:0;background:#f2f3ef;color:#176b75;font-family:Local,"Microsoft YaHei",sans-serif}.label{position:absolute;top:42px;left:52px;font-size:13px}.status{position:absolute;top:42px;right:52px;font-size:13px}main{height:560px;display:flex;align-items:center;justify-content:center}main svg{width:820px;height:auto}.caption{position:absolute;bottom:38px;left:52px;color:#75857d;font-size:12px}</style></head><body><div class="label">PULSE / CUSTOM WORDMARK</div><div class="status">C · 波形 / 已选定稿</div><main>${svg(selected)}</main><div class="caption">原创字形轮廓 · #176B75 · 独立 SVG</div></body></html>`);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: path.join(output, "selected.png") });
    checks.push("selected C: master SVGs and transparent PNG exported");
    console.log(checks.map(check => `PASS ${check}`).join("\n"));
  } finally { await browser.close(); }
}
