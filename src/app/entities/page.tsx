import Link from "next/link";
import type { EntityInfo } from "../articles/_data";
import { formatRegion, readApi } from "../articles/_data";
import styles from "../articles/reading.module.css";

type SearchValues = Record<string, string | string[] | undefined>;

export default async function EntitiesPage({ searchParams }: { searchParams: Promise<SearchValues> }) {
  const raw = await searchParams;
  const type = typeof raw.type === "string" && ["vendor", "model", "organization"].includes(raw.type)
    ? raw.type : "";
  const cursor = typeof raw.cursor === "string" && /^[a-z0-9-]{1,100}$/.test(raw.cursor)
    ? raw.cursor : "";
  const params = new URLSearchParams({ limit: "30" });
  if (type) params.set("type", type);
  if (cursor) params.set("cursor", cursor);
  const response = await readApi<{ items: EntityInfo[]; next_cursor: string | null }>(`/entities?${params}`);
  const items = response.data?.items ?? [];

  return (
    <main data-reading-page className={styles.shell}>
      <header className={styles.topbar}>
        <Link href="/" className={styles.brand}>BLUE PULSE<span> / 警务科技情报</span></Link>
        <Link href="/articles" className={styles.topbarLink}>返回情报库 ↗</Link>
      </header>
      <section className={styles.hero} aria-labelledby="entities-title">
        <div className={styles.heroIndex}>02 / ENTITY INDEX</div>
        <p className={styles.eyebrow}>公开报道中有明确名称证据的实体</p>
        <h1 id="entities-title">厂商与模型<span className={styles.heroMark}>.</span></h1>
        <p className={styles.heroDescription}>按规范名称浏览文章关联。目录只显示当前有公开文章的条目，不将未证实的提及作为关联。</p>
        <div className={styles.heroRule} />
      </section>
      <nav className={styles.periodNav} aria-label="实体类型">
        {[["", "全部"], ["vendor", "厂商"], ["model", "模型"], ["organization", "机构"]].map(([value, label]) => (
          <Link key={value} href={`/entities${value ? `?type=${value}` : ""}`}
            aria-current={type === value ? "page" : undefined}
            className={type === value ? styles.periodActive : ""}>{label}</Link>
        ))}
      </nav>
      <section className={styles.entitySection} aria-label="实体目录">
        <div className={styles.resultsHeading}><span>INDEX / 实体索引</span><span>本页 {items.length} 条</span></div>
        {!response.data ? (
          <div className={styles.messagePanel} role="status"><strong>暂时无法连接情报服务</strong>
            <p>请确认后端已启动，再刷新页面。</p></div>
        ) : items.length === 0 ? (
          <div className={styles.messagePanel} role="status"><strong>暂无可展示的实体</strong>
            <p>目录只列出与已发布文章建立明确关联的厂商、模型或机构。</p>
            <Link href="/articles?period=all">查看文章库 ↗</Link></div>
        ) : (
          <>
            <div className={styles.entityGrid}>
              {items.map((item, index) => (
                <Link className={styles.entityCard} key={item.slug}
                  href={`/articles?period=all&entity=${encodeURIComponent(item.slug)}`}>
                  <span className={styles.asideIndex}>{String(index + 1).padStart(2, "0")} / {item.entity_type.toUpperCase()}</span>
                  <h2>{item.name}</h2>
                  <span>{formatRegion(item.region)} · {item.article_count} 篇文章 <b aria-hidden="true">↗</b></span>
                </Link>
              ))}
            </div>
            {response.data.next_cursor ? (
              <Link className={styles.nextPage} href={`/entities?${new URLSearchParams({ ...(type ? { type } : {}), cursor: response.data.next_cursor })}`}>
                查看下一页 <span aria-hidden="true">↗</span>
              </Link>
            ) : null}
          </>
        )}
      </section>
      <footer className={styles.footer}>BLUE PULSE <span>实体关联来自文章中的明确名称，不代表合作或背书</span></footer>
    </main>
  );
}
