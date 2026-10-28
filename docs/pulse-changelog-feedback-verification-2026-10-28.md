# Pulse 更新日志与反馈页复用验收

日期：2026-10-28。分支：`main`。范围：更新日志、反馈前端、必要共享阅读／菜单适配、Next.js 精确站点接口与后端交接。保留其他会话的菜单、关于页、切页及缓存改动；本会话不提交或推送，由获用户授权的共享导航会话统一收口。没有修改 Python 后端或队友分支，没有接入飞书。

## 原始源码 → 复用内容 → Pulse 适配

| AIHOT 原始实现 | 复用内容 | Pulse 适配 |
| --- | --- | --- |
| `apps/web/app/routes/changelog.tsx`、`features/changelog/text.tsx` | 日期／星期／时间、正文段落列表与粗体、重要公告、类型数量和月份跳转 | Next.js 页面、CSS Modules、p0 内部滚动及锚点；主列表与 200px 右栏在内容宽 760px 起并列，更窄保留可操作控件 |
| `components/ui/Page.tsx` | ReadingLayout、AsideCard、阅读层级与吸顶 | 提取局部共享阅读模板，不复制整站背景、导航或外层框架 |
| `backend/site/meta.ts`、`site/changelog.json`、`docs/customize.md §7` | 人工维护版本化数据、日志／元信息、ETag | 仓库单一 JSON 同时供 SSR、菜单版本和 Next GET；没有 push 自动总结，不需要重复 FastAPI 日志服务 |
| `components/shell/Sidebar.tsx`、`lib/local-state.ts` | 未读红点、已读版本、来源页记忆 | 仅可见激活后标已读，live/mock 隔离、storage 跨标签同步、存储降级 |
| `routes/feedback.tsx` | 主表单与提示栏、内容／邮箱／截图、粘贴拖拽、草稿、提交状态及回执 | 警务文案、显式关联页面、先恢复后保存、离开补存、有效 201 才清草稿、同步防重与显式 Mock |
| `api/routes/feedback.ts`、`backend/operations/feedback.ts`、`admin/feedback.ts` | multipart、真实持久回执、限流、私有截图与处置思路 | 本轮只实现 Next 精确代理；FastAPI、存储与本机查看任务完整交给 `dock.md` DOCK-003，排除飞书 |

证据是 `D:/AIHOT` 无 Git 本地下载快照，仅静态源码核对；没有运行或核验 AIHOT 线上服务。MIT 全文及 `Copyright (c) 2026 数字生命卡兹克` 保留于 THIRD_PARTY_NOTICES.md。快照无可选 FeatureRelease 绘图文件，因此没有编造大版本插画功能。

## 最终实现与真实状态

- `/changelog` 使用 `site/changelog.json` 的 15 条真实开发记录，回溯 main 全部本地历史后按读者可感知变化合并。内部研究、临时提交和协作约定不单列；当前未提交的已交付工作归本批次。页面明确开发日期不是可证明的上线日期。
- 日志支持全部／更新／优化／公告／下线、数量、空态、随筛选变化的月份目标、刷新锚点及历史返回。浏览器已读标记与会话筛选／滚动位置、HTTP 缓存是独立生命周期。
- `GET /api/bluepulse/site/changelog`、`GET /api/bluepulse/site/meta` 分别缓存 300／60 秒，均有 ETag 和 304 空响应，共用同一真实 JSON，不经缺失的 Python 接口回退。
- `/feedback` 默认关闭真实接收，仍可填写及保存文字草稿，并可到关于页 `#pulse-contact` 联系负责人。前端上限 2000 字、邮箱 200 字、关联页面 500 字，一张 PNG/JPEG/WebP 原图最多 5MiB。
- `?mock=1` 的草稿独立，#10001 明确为本地演示、不发网络请求。成功演示不代表真实接收服务可用。
- Next 精确 POST 代理仅在 `BLUEPULSE_FEEDBACK_ENABLED=1` 时启用，保留 multipart 字节、限制总请求 12MiB、15 秒上游超时，不转发 Cookie／Authorization，不跟随重定向。真实成功要求 `201 {id: 正整数}`；未知结果保留草稿，不声称未发送。
- TLS 代理部署设置 `BLUEPULSE_SITE_ORIGIN`；来源校验已修正 Next 内部地址与公开域名不一致的问题。`BLUEPULSE_TRUST_PROXY=1` 仅在可信反代覆盖外来转发头后启用。
- 浏览器存储拒绝或损坏时有真实提示和内存降级；截图不写浏览器持久存储，替换、移除或卸载释放 Object URL。

## 验证结果

| 检查 | 当前结果 |
| --- | --- |
| 专项 Node 逻辑／代理测试 | 19 项通过；覆盖日志校验、筛选月份、已读状态、ETag、草稿、附件、回执、限流时间、代理关闭／边界／Origin |
| `pnpm lint` | 通过，无错误或警告 |
| `pnpm exec tsc --noEmit --incremental false` | 通过 |
| 生产构建 | 共享导航会话统一完成；本专项使用其最新生产产物，未并发重写 `.next` |
| 完整浏览器专项（此前一次） | **12/13 组通过**；成功回执在故意超时网络用例之后等待超时，未将其写为全量通过 |
| 成功回执独立运行 | 通过：一次上游请求、multipart 字段／图片完整、凭据不转发、有效回执清草稿、刷新不重建草稿 |
| 当前完整复跑 | 正在验证将故意挂起的网络场景放在正常契约之后的隔离运行；最终以本节后续更新及 verification.json 为准 |
| 视觉复核 | 已查看 1360×760 桌面、390×844 移动和 reduced-motion 两页截图；白纸无横向溢出，右栏吸顶、窄白纸筛选可用，反馈提示编号已修正为不换行 |
| 独立代码复核 | Origin 校验问题已复现、修正并复核通过，无剩余已确认业务阻断 |

浏览器检查使用 3140／3142 两个隔离的生产 Next 服务、3141 受控 HTTP 接收服务及隔离浏览器上下文。覆盖 GET 缓存、筛选／空态／月份、未读预取及跨标签、草稿 400ms 保存／刷新／SPA 返回／立即离开、拒绝存储、附件三种添加／移除／同文件重选／错误类型／大小、Object URL 清理、重复发送、live/mock 隔离，以及 200、无效 201、400/403/413/404/429/503、断网和超时。假服务回执不是业务真实入库。

此前曾发生两个测试环境问题：另一会话重建 `.next` 时短暂缺失产物，停止服务后重跑；测试选择器匹配到 Next 路由播报器，已限定为表单内 alert。最后一组在独立运行与全量运行的差异已如实保留，当前未据此修改业务源码。

复现：

```powershell
pnpm lint
pnpm exec tsc --noEmit --incremental false
node --experimental-strip-types --test scripts/changelog.test.mjs scripts/feedback.test.mjs scripts/feedback-proxy.test.mjs
# 先由当前工作会话统一 pnpm build；不要与其他 build/dev 并行。
node --experimental-strip-types scripts/changelog-feedback-browser-test.mjs
```

产物在 Git 忽略的 `test-results/changelog-feedback/`：verification.json、两页 desktop/mobile/reduced-motion PNG、复核报告。Node 的 MODULE_TYPELESS_PACKAGE_JSON 是仓库现有提示，没有为消除此提示改 package 模式或依赖。

## 反馈提交后如何查看

**当前普通模式尚不能真实发送，因此没有真实反馈可查。** 后端同事完成 `dock.md` DOCK-003 后，在后端机器执行以下待实现命令：

```powershell
Set-Location D:/pulse/backend
uv run python -m bluepulse_backend.cli feedback list --status new
uv run python -m bluepulse_backend.cli feedback show 123
```

`show` 应展示完整文字、邮箱、关联页面、处理状态、备注及私有截图本机路径。后端还需提供状态更新、删除、封禁与审计；网页 `/admin/feedback` 待管理员权限链建成后提供。以上命令与网页目前均未实现，不把前端、代理或测试服务称为完整反馈业务。
