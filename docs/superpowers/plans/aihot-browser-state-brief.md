# 任务：统一浏览器状态及会话缓存

只创建 `src/app/_lib/browser-state.ts`、`src/app/_lib/use-browser-state.ts`、`src/app/_lib/session-restore.ts`、`scripts/browser-state.test.mjs`；不改其他文件，不提交。

基于 D:/AIHOT/apps/web/app/lib/local-state.ts 及 session-cache.ts/restore.ts，保留适用成熟机制；复制实质代码要文件注释记录 MIT来源，完整许可由主代理整合。Node 直接运行TS测试，核心文件不引入React。

约定导出：
`LocalStarredItem` {id,title,summary:string|null,sourceName,publishedAt:string|null,score:number|null,savedAt:string}。
`HistoryEntry` {article:ArticleCard,viewedAt:string}（import type现有home-data）。
`BrowserSnapshot` {ready:boolean,entered:boolean,starred:LocalStarredItem[],history:HistoryEntry[],notice:string|null}。
`BrowserStateStore` getSnapshot(), getServerSnapshot(), subscribe(listener), hydrate(), markEntered(), toggleStar(item:Omit<LocalStarredItem,'savedAt'>), removeStar(id), recordRead(article:ArticleCard), clearHistory()。
`getBrowserState(mock=false):BrowserStateStore` 命名空间单例。
`createBrowserState(mock=false, options?)` 供纯测试真实store输入受控Storage/EventTarget/now，不添加仅为测试使用的方法。
`browserKeys(mock=false)` 返回 {entry,starred,history}；真实entry `blue-pulse-entry-complete-v1`，starred `blue-pulse-starred-items-v1`，历史沿用 `blue-pulse-reading-history-v1`，mock所有key末尾`:mock`。
entry 保存字符串 `1`，head同步启动脚本将读取这个精确值。
`useBrowserState(mock=false)` 客户端hook返回 `{state,store}`，useSyncExternalStore稳定snapshot，hydrate不用hydration mismatch，server snapshot固定空值。

收藏真实UUID校验、新收藏置顶500上限、重复toggle取消、取消只对应ID、日期/文字字段校验、历史最多30条去重并保留现有数据；收藏快照保存摘要不保存全文。
读Storage属性本身可能throw；损坏数据不得用空列表静默覆盖。写失败/不可访问内存降级并notice说明本次访问有效；同页更新立即通知，storage跨页更新；写前重读（非原子，勿声称严格无丢失并发）。跨页更新不得混命名空间。退出订阅清理监听。

会话模块导出 `saveSessionSnapshot<T>(key:string,value:T,mock=false):void`、`readSessionSnapshot<T>(key:string,mock=false):T|null`，30min过期，版本/JSON/时间校验、容量上限20条、sessionStorage不访问时内存降级；页面/筛选完整key可含cursor；namespace分离。输入snapshot不会包含访问凭证。

先写行为测试确认新增模块缺失，再实现并运行。覆盖snapshot引用稳定、持久化/损坏/受限写内存、same-tab/cross-tab、mock隔离、历史兼容、500收藏截断、30min过期和不续期。不要为低影响简单包装单独写镜像测试。

返回接口/变更/测试结果和限制。
