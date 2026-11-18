# Police Life 与 Police Science & Technology 采集说明

实测日期为北京时间 2026 年 11 月 17 日。本次比较两个信源的发现入口、详情抓取和发布时间覆盖。隔离采集使用项目的常驻 Worker 任务逻辑，随后在本地 `3100` 实例核对了实际运行记录。

| 信源 | 当前发现方式 | 发布日期来源 | 已验证的覆盖 |
| --- | --- | --- | --- |
| 新加坡 Police Life（`spf-police-life`） | 归档 API 在站点规则允许时可用。本次改走公开栏目 | 公开栏目发现的稿件以详情页为准 | 公开栏目展示范围，标记为部分覆盖 |
| 英国 Police Science & Technology（`police-science`） | 带日期的官方新闻列表及其下一页链接 | 列表卡片的发布日期，详情日期可补充或纠正 | 本次目标时间窗覆盖完成 |

## 新加坡 Police Life

1. 读取站点的 `robots.txt`。采集器根据规则判断是否可以使用 `POST /api/GetLifeArticles`。实测规则禁止访问 `/api/`，因此由 Worker 读取允许抓取的公开栏目。 [站点抓取规则](https://www.police.gov.sg/robots.txt) · [Police Life 公开栏目](https://www.police.gov.sg/Media-Hub/Police-Life)
2. 从公开页提取同一主机的文章链接，优先处理「Explore Latest Articles」区域。同一链接合并，标题或链接符合警务科技关键词的候选进入正文队列。
3. 到文章详情读取标题、正文和发布日期，按原站给出的日期精度保存。实测两篇详情均抓到完整正文，发布日期分别为 11 月 1 日和 10 月 27 日。
4. 公开栏目是有限展示页。Worker 把该次扫描记为部分覆盖，正文抓取成功与归档覆盖分别记录。

实现见 [Police Life 采集器](../backend/bluepulse_backend/spf_source.py)。

## 英国 Police Science & Technology

1. Worker 优先读取官方新闻列表，从新闻卡片提取同一主机的文章链接、标题与发布日期。按官网给出的下一页链接翻页，直到已有日期证据足以覆盖时间窗，或官网分页耗尽。 [官方新闻列表](https://science.police.uk/news-and-events/news/)
2. 抓取详情正文时，优先使用详情明确给出的发布日期。详情未提供日期时保留列表已确认的日期。仅有日期的稿件保留日期精度。
3. 如果首屏遇到浏览器验证页或缺少预期的新闻卡片，且本轮尚未读到有效分页，Worker 可退回站点地图发现候选。站点地图只提供 URL，退回时按部分覆盖记录。 [官方站点地图](https://science.police.uk/sitemap.xml)
4. 隔离 Worker 实际翻了 4 页，记录 50 次候选发现并确认覆盖了目标时间窗，抽取的两篇详情均有正文及发布日期。本地常驻 Worker 随后也成功读取日期列表，并按该轮时间窗记录了完整覆盖。

实现见 [Police Science & Technology 采集器](../backend/bluepulse_backend/police_science_source.py)。

## 复验

在项目根目录执行以下命令，检查两个信源的采集回归用例。

```powershell
.\backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_spf_source.py backend/tests/test_police_science_source.py
```

运行常驻 Worker 后，在本地后台的「信源」分别查看这两个来源的采集记录。重点核对列表覆盖、候选数和正文任务结果。Police Science 的单源预览命令走站点地图抽样，验证正式日期分页时以常驻 Worker 的记录为准。[本地信源后台](http://127.0.0.1:3100/admin/sources)
