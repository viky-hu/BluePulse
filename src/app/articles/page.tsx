import Link from "next/link";
import type { ArticleCard, ArticleListResponse, EntityInfo, SourceInfo, TopicInfo } from "./_data";
import { formatArticleTimeline, formatRegion, readApi } from "./_data";
import styles from "./reading.module.css";

type SearchValues = Record<string, string | string[] | undefined>;
type Period = "24h" | "7d" | "30d" | "all";

const PERIODS: Array<{ value: Period; label: string }> = [
  { value: "24h", label: "24 小时" },
  { value: "7d", label: "7 天" },
  { value: "30d", label: "30 天" },
  { value: "all", label: "全部时间" },
];

const SOURCE_TYPE_LABELS: Record<string, string> = {
  academic: "研究机构 / 学术", aggregator: "公开聚合检索", government: "政府机构",
  media: "专业媒体", vendor: "厂商官方",
};

function scalar(value: string | string[] | undefined): string {
  return typeof value === "string" ? value : "";
}

function buildHref(values: Record<string, string>, changes: Record<string, string> = {}): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries({ ...values, ...changes })) {
    if (value) params.set(key, value);
  }
  const query = params.toString();
  return `/articles${query ? `?${query}` : ""}`;
}

function ArticleRow({ article, index, topicNames }: {
  article: ArticleCard;
  index: number;
  topicNames: Map<string, string>;
}) {
  return (
    <article className={`${styles.articleRow} ${index === 0 ? styles.leadRow : ""}`}>
      <Link className={styles.rowLink} href={`/articles/${article.id}`} aria-label={`阅读：${article.title}`}>
        <span className={styles.rowNumber}>{String(index + 1).padStart(2, "0")}</span>
        <div className={styles.rowContent}>
          <div className={styles.rowMeta}>
            <span>{formatRegion(article.region)}</span>
            <span className={styles.metaDot} aria-hidden="true" />
            <span>{article.source.name}</span>
            <span className={styles.metaDot} aria-hidden="true" />
            <time>{formatArticleTimeline(article)}</time>
          </div>
          <h2>{article.title}</h2>
          {article.source_title !== article.title ? (
            <p className={styles.originalTitle}>{article.source_title}</p>
          ) : null}
          <p className={styles.summary}>
            {article.summary?.trim() || "暂无中文摘要。打开详情查看已获取的原始资料。"}
          </p>
          <div className={styles.tagLine}>
            {(article.topics ?? []).slice(0, 3).map((topic) => (
              <span key={topic}>{topicNames.get(topic) ?? topic}</span>
            ))}
          </div>
        </div>
        <span className={styles.rowArrow} aria-hidden="true">↗</span>
      </Link>
    </article>
  );
}

export default async function ArticlesPage({
  searchParams,
}: {
  searchParams: Promise<SearchValues>;
}) {
  const raw = await searchParams;
  const requestedPeriod = scalar(raw.period);
  const period = PERIODS.some((item) => item.value === requestedPeriod)
    ? requestedPeriod as Period : "30d";
  const topic = scalar(raw.topic).slice(0, 80);
  const region = ["domestic", "foreign"].includes(scalar(raw.region)) ? scalar(raw.region) : "";
  const source = /^[0-9a-f-]{36}$/i.test(scalar(raw.source)) ? scalar(raw.source) : "";
  const sourceType = /^[a-z_-]{1,32}$/.test(scalar(raw.source_type)) ? scalar(raw.source_type) : "";
  const entity = /^[a-z0-9-]{1,100}$/.test(scalar(raw.entity)) ? scalar(raw.entity) : "";
  const q = scalar(raw.q).trim().slice(0, 200);
  const sort = scalar(raw.sort) === "importance" ? "importance" : "recent";
  const cursor = scalar(raw.cursor).slice(0, 2000);
  const values = { period, topic, region, source, source_type: sourceType, entity, q, sort };
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries({ ...values, ...(cursor ? { cursor } : {}) })) {
    if (value) query.set(key, value);
  }

  const [listing, topicResponse, sourceResponse, entityResponse] = await Promise.all([
    readApi<ArticleListResponse>(`/articles?${query.toString()}`),
    readApi<{ items: TopicInfo[] }>("/taxonomy"),
    readApi<{ items: SourceInfo[] }>("/sources"),
    readApi<{ items: EntityInfo[] }>("/entities?limit=100"),
  ]);
  const topics = topicResponse.data?.items ?? [];
  const sources = sourceResponse.data?.items ?? [];
  const entities = entityResponse.data?.items ?? [];
  const sourceTypes = Array.from(new Set(sources.map((item) => item.source_type)));
  const topicNames = new Map(topics.map((item) => [item.slug, item.name_zh]));
  const items = listing.data?.items ?? [];

  return (
    <main data-reading-page className={styles.shell}>
      <header className={styles.topbar}>
        <Link href="/" className={styles.brand}>BLUE PULSE<span> / 警务科技情报</span></Link>
        <Link href="/entities" className={styles.topbarLink}>厂商 / 模型目录 ↗</Link>
      </header>

      <section className={styles.hero} aria-labelledby="articles-title">
        <div className={styles.heroIndex}>01 / INTELLIGENCE</div>
        <p className={styles.eyebrow}>公开来源 · 中文整理 · 原文可溯</p>
        <h1 id="articles-title">近期情报<span className={styles.heroMark}>.</span></h1>
        <p className={styles.heroDescription}>从公开资料出发，追踪警务、公共安全技术与相关研究。</p>
        <div className={styles.heroRule} />
      </section>

      <nav className={styles.periodNav} aria-label="时间范围">
        {PERIODS.map((option) => (
          <Link
            key={option.value}
            href={buildHref(values, { period: option.value })}
            aria-current={period === option.value ? "page" : undefined}
            className={period === option.value ? styles.periodActive : ""}
          >
            {option.label}
          </Link>
        ))}
      </nav>

      <div className={styles.mainGrid}>
        <aside className={styles.filterPanel} aria-label="筛选文章">
          <div className={styles.panelHeading}><span>筛选 / FILTER</span><span>01—06</span></div>
          <form action="/articles" method="get" className={styles.filterForm}>
            <input type="hidden" name="period" value={period} />
            <div className={`${styles.filterField} ${styles.searchField}`}>
              <label htmlFor="query">关键词</label>
              <input id="query" name="q" type="search" placeholder="标题或正文" defaultValue={q} />
            </div>
            <div className={styles.filterField}>
              <label htmlFor="topic">主题</label>
              <select id="topic" name="topic" defaultValue={topic}>
                <option value="">全部主题</option>
                {topics.map((item) => <option key={item.slug} value={item.slug}>{item.name_zh}</option>)}
              </select>
            </div>
            <div className={styles.filterField}>
              <label htmlFor="region">地区</label>
              <select id="region" name="region" defaultValue={region}>
                <option value="">国内与国外</option>
                <option value="domestic">国内</option>
                <option value="foreign">国外</option>
              </select>
            </div>
            <div className={styles.filterField}>
              <label htmlFor="entity">厂商 / 模型</label>
              <select id="entity" name="entity" defaultValue={entity}>
                <option value="">全部实体</option>
                {entities.map((item) => <option key={item.slug} value={item.slug}>{item.name} · {item.article_count}</option>)}
              </select>
            </div>
            <div className={styles.filterField}>
              <label htmlFor="source-type">来源类型</label>
              <select id="source-type" name="source_type" defaultValue={sourceType}>
                <option value="">全部类型</option>
                {sourceTypes.map((item) => <option key={item} value={item}>{SOURCE_TYPE_LABELS[item] ?? item}</option>)}
              </select>
            </div>
            <div className={styles.filterField}>
              <label htmlFor="source">来源</label>
              <select id="source" name="source" defaultValue={source}>
                <option value="">全部来源</option>
                {sources.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </div>
            <div className={styles.filterField}>
              <label htmlFor="sort">排序</label>
              <select id="sort" name="sort" defaultValue={sort}>
                <option value="recent">发布时间</option>
                <option value="importance">重要性</option>
              </select>
            </div>
            <button type="submit">应用筛选 <span aria-hidden="true">↗</span></button>
            <Link href="/articles" className={styles.clearLink}>清除条件</Link>
          </form>
        </aside>

        <section className={styles.results} aria-label="文章列表">
          <div className={styles.resultsHeading}>
            <span>INTELLIGENCE / 情报条目</span>
            <span>{listing.data ? `本页 ${items.length} 条` : "连接状态"}</span>
          </div>
          {!listing.data ? (
            <div className={styles.messagePanel} role="status">
              <strong>暂时无法连接情报服务</strong>
              <p>请确认后端已启动，再刷新页面。已保存的文章不会因此丢失。</p>
              <Link href={buildHref(values)}>重新载入 ↗</Link>
            </div>
          ) : items.length === 0 ? (
            <div className={styles.messagePanel} role="status">
              <strong>这一范围内还没有可阅读的文章</strong>
              <p>可以放宽时间或筛选条件；待处理内容不会被冒充为已发布文章。</p>
              <Link href={buildHref(values, { period: "all", topic: "", region: "", source: "", source_type: "", entity: "", q: "" })}>
                查看全部时间 ↗
              </Link>
            </div>
          ) : (
            <>
              <div className={styles.articleList}>
                {items.map((item, index) => (
                  <ArticleRow key={item.id} article={item} index={index} topicNames={topicNames} />
                ))}
              </div>
              {listing.data.next_cursor ? (
                <Link className={styles.nextPage} href={buildHref(values, { cursor: listing.data.next_cursor })}>
                  查看下一页 <span aria-hidden="true">↗</span>
                </Link>
              ) : <p className={styles.listEnd}>— 当前范围内已显示完毕 —</p>}
            </>
          )}
        </section>
      </div>
      <footer className={styles.footer}>BLUE PULSE <span>以原始来源为准 · 不将模型整理内容视作独立事实</span></footer>
    </main>
  );
}
