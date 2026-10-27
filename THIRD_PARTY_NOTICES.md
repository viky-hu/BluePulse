# Third-party notices

## AIHOT

Pulse 的浏览器状态、会话恢复和菜单实现移植参考了 AIHOT 开源框架的以下文件：

- `D:/AIHOT/apps/web/app/lib/local-state.ts`：匿名收藏、已读、存储降级、数据导入导出及跨标签页通知。
- `D:/AIHOT/apps/web/app/lib/restore.ts`、`session-cache.ts`：历史条目快照、30分钟会话恢复及滚动锚点。
- `D:/AIHOT/apps/web/app/components/shell/Sidebar.tsx`、`nav.ts`：菜单分组、条目布局、选中态与路由归属。
- `D:/AIHOT/apps/web/app/components/icons.tsx`：菜单使用的内联 SVG 图标。
- `D:/AIHOT/site/brand/Logo.tsx`：圆点与站名的字标排版；Pulse 使用自身名称与本地字体。

Pulse 对应实现为 `src/app/_lib/browser-state.ts`、`session-restore.ts`、`src/app/_components/home/navigation-config.ts`、`menu/` 及相关集成代码。具体移植范围与领域适配见 [源码研究](docs/aihot-understanding.md) 和 [后端阶段交接](docs/aihot-backend-stage-map.md)。后续复制 AIHOT 实质代码应继续保留以下完整许可与版权声明，并更新本文件的适用范围。

参考仓库：[KKKKhazix/AIHOT](https://github.com/KKKKhazix/AIHOT)。本轮研究使用无 Git 的本地下载快照，无法指定上游提交。AIHOT 名称和 Logo 不包含在其 MIT 软件许可中；Pulse 使用自身品牌。第三方新闻内容及字体等素材各自遵守其原有许可。

以下完整文字来自 `D:/AIHOT/LICENSE`：

```text
MIT License

Copyright (c) 2026 数字生命卡兹克

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
