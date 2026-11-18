# 江苏地市公安官网采集记录

实测日期为北京时间 2026 年 11 月 17 日。南京、苏州已接入本地 Pulse 常驻 Worker。无锡、常州、泰州、盐城、淮安已抓到可读正文，以下记录保留了各站的接入方法和实测范围。

| 信源 | 2026-11-17 实测 | 接入状态 |
| --- | --- | --- |
| 南京公安 | 栏目 3/3 可读。本地 Worker 首轮翻 2 页，30 篇均有完整正文和原站发布日期 | 本地 Worker 已启用 |
| 苏州公安 | 本地 Worker 首轮翻 2 页，30 篇均有完整正文和原站发布日期。隔离首轮 20 篇直接成功，10 篇传输失败并进入重试队列，抽查复取 3/3 成功 | 本地 Worker 已启用 |
| 无锡公安 | 栏目 3/3 可读，详情 3/3 抓到可读正文 | 已抽测 |
| 常州公安 | 首轮规则预检连接失败，后两轮栏目可读，详情 3/3 抓到可读正文 | 已抽测 |
| 泰州公安 | 两个栏目页及各自的列表接口均为 3/3，媒体聚焦详情抽测 1/1 抓到可读正文 | 已抽测 |
| 盐城公安 | 栏目 3/3 可读，详情 2/2 抓到可读正文 | 已抽测 |
| 淮安公安 | 栏目 3/3 可读，详情 2/2 抓到可读正文 | 已抽测 |

## 已接入本地 Worker

### 南京市公安局（`nanjing-police`）

1. 先检查 `/robots.txt`，随后读取警务动态首页。解析 `createPageHTML(总页数, 当前页下标, "index", "html")`，首页下标为 0，第二页是 `index_1.html`。
2. 从列表提取链接、标题和发布日期。详情只接受同主机的 `/jwdt/年月/t年月日_编号.html`。标题取 `.doctitle`，正文取 `.doccontent`，发布时间取 `.field_con1` 中的「发布时间」。
3. 详情含时分时按北京时间解释。详情缺时间时保留列表日期的精度。首批 30 篇是现有导入上限，运行记录标为部分覆盖。

[警务动态](https://gaj.nanjing.gov.cn/jwdt/) · [详情样本](https://gaj.nanjing.gov.cn/jwdt/202611/t20261102_6030441.html) · [南京采集器](../backend/bluepulse_backend/nanjing_source.py)

### 苏州市公安局（`suzhou-police`）

1. 爬取规则请求如果收到指向 `http://gonganju.suzhou.gov.cn` 的特定 `302`，按规则文件缺失处理。现场验证多个不存在的地址返回同样的跳转。采集器不跟随该跳转，后续只请求允许列表内的 HTTPS URL。明确禁止抓取、其他跳转、403、429、5xx 均按现有规则处理。
2. 以警务动态 `nav_list.shtml` 为首页。解析 `createPageHTML('page_div', 总页数, 当前页码, 'nav_list', 'shtml', 总条数)`，按实际页码访问 `nav_list_2.shtml`、`nav_list_3.shtml`。校验返回页码，避免重复读回首页后误判为翻页成功。
3. 列表提取标题、链接、日期。只接受同主机 `/gaj/jwdt/年月/32位十六进制编号.shtml`。详情从 `.article-title`、`.article-content` 和 `.date` 的「发布日期」分别取标题、正文和日期。网络类错误进入 Worker 现有重试队列。

[警务动态](https://gonganju.suzhou.gov.cn/gaj/jwdt/nav_list.shtml) · [第二页](https://gonganju.suzhou.gov.cn/gaj/jwdt/nav_list_2.shtml) · [110 接处警 AI 样本](https://gonganju.suzhou.gov.cn/gaj/jwdt/202609/58de9792ba7c4f05bef724c88a59942e.shtml) · [苏州采集器](../backend/bluepulse_backend/suzhou_source.py)

两站都是显式注册的新增信源。本地采集已开启，公开摘要和全文许可都未开启。

## 已抽测的采集方法

### 无锡市公安局

警务新闻的首屏 HTML 直接包含文章链接 `/doc/年/月/日/编号.shtml`，列表日期在 `.riqi`，格式是 `YYYY/MM/DD`。详情正文在 `#Zoom`，优先取 `.explain` 中带时分的「发布时间」，`meta[name="PubDate"]` 在样本上只给日期。页面用 `regClick_blue` 配置分页，后续页的请求方式待实测。 [警务新闻](https://ga.wuxi.gov.cn/jfzx/tpxw/index.shtml) · [详情样本](https://ga.wuxi.gov.cn/doc/2026/11/16/4858309.shtml)

### 常州市公安局

从 `li.list-li` 取链接和同条记录的日期。详情固定使用 `/content/suitable/show?id=…&catid=34221`，标题可用列表锚文本，正文在 `#czfxfontzoom`，时间取 `meta[name="PubDate"]`。页面提供 `cate_id=34221&page=2` 等分页链接，抽测只跑了首屏列表与详情。 [警务动态](https://gaj.changzhou.gov.cn/content/suitable/list?cate_id=34221) · [详情样本](https://gaj.changzhou.gov.cn/content/suitable/show?id=88743&catid=34221)

### 泰州市公安局

警务动态、媒体聚焦的栏目页是页面壳。读取加载 `AuthorizedRead/unitbuild.js` 的脚本标签，从中取 `url` 和本站声明的 `queryData`，把字段作为查询参数 GET 同主机 `/api-gateway/jpaas-publish-server/front/page/build/unit`。返回 JSON 的 `data.html` 含列表，本次两栏目每轮分别取到 13、15 条文章链接。详情使用 `.wzzw-title`、`.wzzw-article` 和 `.wzzw-text` 里的发布日期。抽测同一稿件的可见发布时间与 `PubDate` 相差数小时，接入时应保留可见发布时间及其出处。接口的后续分页尚未实测。 [警务动态](https://gaj.taizhou.gov.cn/jwzx/jwdt/index.html) · [媒体聚焦](https://gaj.taizhou.gov.cn/jwzx/mtjj/index.html) · [详情样本](https://gaj.taizhou.gov.cn/jwzx/mtjj/art/2026/art_e3de5bbe80124303bdbb2947638155af.html)

### 盐城市公安局

列表内嵌 `script[type="text/xml"]`。从 `datastore/recordset/record` 的 CDATA 取文章链接和 `.timedate`。详情在 `#zoom`，正文截取 `ContentStart` 到 `ContentEnd` 之间的内容，日期取页面的「发布时间」或 `PubDate`。官网标出了 `/module/web/jpage/dataproxy.jsp`，抽测仅验证了内嵌首屏记录。 [警务动态](https://ycga.yancheng.gov.cn/col/col12169/index.html) · [详情样本](https://ycga.yancheng.gov.cn/art/2026/11/9/art_12169_4466571.html)

### 淮安市公安局

从栏目首屏配对同条记录的标题链接与 `.time`。警务资讯可链接到站内不同子栏，详情匹配同主机的 `/col/…/art/o/…html`，例如样本来自警务动态子栏。正文在 `.nr-zw`，标题在 `.nr-bt`，精确时间取 `PubDate`，可见的 `.nr-time` 可补日期。首屏日期出现旧稿夹在新稿之间，不能仅凭首条旧记录判断已扫完目标时间窗。页面声明的 `nsetpage` 分页尚未实测。 [警务资讯](https://gaj.huaian.gov.cn/col/9035_856534/o/index.html) · [详情样本](https://gaj.huaian.gov.cn/col/9105_151615/art/o/17934624/1794879977969zxE3jr6f.html)

## 复验与本机原始记录

在项目根目录运行。单源预览会抓列表和最多两篇详情，验证实际分页与入库时查看常驻 Worker 的采集批次。

```powershell
.\backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_nanjing_source.py backend/tests/test_suzhou_source.py
Push-Location backend
.\.venv\Scripts\python.exe -m bluepulse_backend.source_collection --source nanjing-police --mode preview --max-items 2 --execute
.\.venv\Scripts\python.exe -m bluepulse_backend.source_collection --source suzhou-police --mode preview --max-items 2 --execute
Pop-Location
```

泰州、盐城、淮安在抽测时的 `robots.txt` 返回 404。其他站点的规则、网络结果及样本均可在本机 `backend/data` 下复核，原始日志未纳入 Git。

- 地市抽测目录 `jiangsu-source-quality-20261117-171341`，含 `network.json`、`details.json` 和 `taizhou-list-api.json`。
- 南京 Worker 记录 `nanjing-suzhou-source-check-20261117-205142-919405/result.json`。
- 苏州 Worker 记录 `suzhou-direct-check-20261117-211912-310835/result.json` 和 `local-worker.json`。
