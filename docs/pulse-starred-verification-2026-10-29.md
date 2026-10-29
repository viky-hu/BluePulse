# 收藏页复用与验收

日期：2026-10-29。范围为 `/starred` 前端、收藏菜单、本地备份与独立已读标记；直接在 main 开发，保护原有全部动态改动。未修改 FastAPI 或队友分支，未触发采集、付费模型或外部通知。

## 原始源码 → 复用内容 → Pulse 适配

证据为本机非 Git 的 `D:/AIHOT` 下载快照，直接阅读了实际源码，不以静态研究代替运行验证。

| 原始源码 | 复用内容及适配 |
| --- | --- |
| `apps/web/app/routes/starred.tsx` | 标题说明、导入／导出、只保存在本机提示、可关闭导入结果、空态、单列卡片、取消收藏及权限信息。使用 Next.js 路由／noindex 和 Pulse p0 内部滚动；不复制 PhoneBar 或外层框架。 |
| `apps/web/app/lib/local-state.ts` | 500收藏、5000已读、version 1 导入导出、已有优先、去重、归一化、savedAt降序和部分失败回执。沿用 Pulse UUID 和旧键；新增独立已读键并迁移既有历史，保留30篇历史的独立生命周期；不应用外观偏好。 |
| `components/ui/Presence.tsx`、`components/icons.tsx` | 160ms提示入退场和书签／关闭／下载图形；CSS局部样式、卸载清理、reduced-motion静态呈现。 |
| `components/shell/nav.ts` | 收藏位于“内容”组末尾，保留 Pulse 现有菜单尺寸、选中、意图预取和切页行为。 |
| `packages/backend/src/publication/availability.ts`、`packages/contracts/src/site.ts` | 不可用／仅摘要／当前来源名的语义。通过前端适配现有 available 布尔接口，显式兼容未来 status/source_name，分批100、no-store、取消旧请求、失败保留未知。没有移植 SQL 或扩大已撤回内容权限。 |

布局以收藏页实际内容宽度为依据：640px起工具左右排布并使用原版单列卡片；窄内容区域改为分隔行；480px以下隐藏次要收藏时间、发布时间换行。主标题24px、文章16px／650、摘要14px两行、辅助文字12.5–13px，日期固定北京时间 `YYYY-MM-DD HH:mm`。保留共享 p0 几何和 GSAP 转场、本地 Google Sans／微软雅黑。

## 检查结果

- `pnpm lint`：退出0。
- `pnpm build`：退出0，Next.js16.3.5生产构建和TypeScript通过，`/starred`正常生成。
- `node --experimental-strip-types --test scripts/starred-state.test.mjs scripts/starred-availability.test.mjs scripts/browser-state.test.mjs`：19项通过，0失败。
- `node --experimental-strip-types scripts/home-routes.test.mjs`：通过，收藏菜单与README选项保持一致，直接子页跳过封面。
- `node --experimental-strip-types scripts/starred-browser-test.mjs`：22组通过，0页面脚本错误；1360×760、390×844及桌面reduced-motion均覆盖。
- 独立审查分别检查了本地数据及完整功能，对照实际AIHOT源码和当前文件；未发现阻断项。

Node直接运行TypeScript时会输出仓库既有的 `MODULE_TYPELESS_PACKAGE_JSON` 提示，不影响上述退出状态；未为消除提示修改项目模块配置。

逻辑覆盖：旧记录兼容、一次迁移、独立清历史、500／5000上限、已有记录优先、导入排序、无效／超量计数、重复导入、备份投影、非法／过大文件、损坏存储保护、收藏持久化失败、已读部分失败、新鲜读取、通知同步、命名空间隔离和批次完整性校验。

浏览器覆盖：三种视口／动效条件下的空态、私有页面元信息、菜单高亮、导入／重复选择同文件、JSON下载、当前来源与北京时间、显式撤回／仅摘要、移除不误触文章、跨标签同步和阅读返回锚点；另外检查205条收藏的三个批次部分故障、当前菜单刷新重核验、真实详情收藏／刷新保留、清空历史后全部动态仍标已读、live/mock隔离、导入失败／部分成功／关闭通知、损坏存储和慢核验期间离开。

截图已人工复核：`test-results/starred/{desktop,mobile,reduced}-{empty,list}.png`，结果为 `test-results/starred/verification.json`。目录为本地忽略产物；样本仅存在于自动化隔离浏览器及受控HTTP服务，不写入默认收藏页。

## 补充回归的边界

补跑历史脚本 `home-transition-browser-test.mjs`，先同步了新增收藏菜单和新撤回提示的预期，并确认桌面封面完成、重访、菜单几何／滚动及全部菜单落地。该脚本随后在第162行等待旧版 `/all` 的“主题分类”下拉框超时：当前全部动态已经采用AIHOT分类标签，旧脚本还包含旧30天默认值和旧排序控件假设。因此该历史综合脚本**没有整套通过**，本轮不将其计入通过数量，也不为迎合旧测试修改新版全部动态。其后续用例未执行；收藏专项已独立覆盖本轮存储、导航和位置恢复。

## 真实状态与后端依赖

现有匿名 `GET /api/v1/articles/availability`、100条UUID限制和no-store已静态核实；本轮浏览器使用受控HTTP边界，未把它当作真实FastAPI联调。

生产接口当前只含available，尚无明确summary-only或当前来源名。前端不会根据缺少正文、翻译状态或快照内容自行判断许可；扩展字段未接入时显示保存时来源。完整统一发布、全文许可和撤回政策仍属后续后端工作。七节契约、示例与签收条件见根目录 `dock.md` 的DOCK-005。

收藏和已读没有账号／云同步，备份不含正文或历史快照；清空浏览器数据后不会自动恢复。AIHOT MIT全文和 `Copyright (c) 2026 数字生命卡兹克` 保留于第三方声明。
