import Link from "next/link";
import { notFound } from "next/navigation";
import type { ArticleDetail, TopicInfo } from "../_data";
import { formatArticleDate, formatArticleTimeline, formatRegion, readApi, safeSourceUrl } from "../_data";
import styles from "../reading.module.css";

function evidenceLabel(parseStatus: string): string {
  return {
    full_text: "已取得正文",
    abstract_only: "仅有学术摘要",
    summary_only: "仅有来源摘要",
    metadata_only: "仅有标题与元数据",
    partial_text: "仅有部分正文",
  }[parseStatus] ?? "内容获取状态待核";
}

function translationLabel(status: ArticleDetail["translation_status"]): string {
  return {
    not_required: "原文即中文",
    available: "已翻译",
    pending: "尚未翻译",
    failed: "翻译失败，可查看英文原文",
    source_unavailable: "无可翻译的完整原文",
    too_long: "原文较长，暂未翻译",
  }[status] ?? "状态待核";
}

export default async function ArticleDetailPage({ params }: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) notFound();
  const [response, topicResponse] = await Promise.all([
    readApi<ArticleDetail>(`/articles/${id}`),
    readApi<{ items: TopicInfo[] }>("/taxonomy"),
  ]);
  if (response.status === 404) notFound();
  const article = response.data;
  const topicNames = new Map((topicResponse.data?.items ?? []).map((item) => [item.slug, item.name_zh]));

  if (!article) {
    return (
      <main data-reading-page className={styles.shell}>
        <header className={styles.topbar}>
          <Link href="/" className={styles.brand}>BLUE PULSE<span> / 警务科技情报</span></Link>
        </header>
        <div className={styles.detailUnavailable} role="status">
          <span className={styles.eyebrow}>CONNECTION / 连接状态</span>
          <h1>暂时无法读取这篇文章。</h1>
          <p>请确认后端服务已启动，然后重试。</p>
          <Link href={`/articles/${id}`}>重新载入 ↗</Link>
          <Link href="/articles">返回情报列表 ←</Link>
        </div>
      </main>
    );
  }

  const sourceUrl = safeSourceUrl(article.url);
  const hasChineseBody = article.translation_status === "available" && Boolean(article.zh_body?.trim());
  const hasOriginalBody = article.body_status !== "metadata_only" && Boolean(article.source_body?.trim());
  const isEnglish = article.language.toLowerCase().startsWith("en");
  const bodyNote = hasChineseBody
    ? "中文全文由模型翻译，重要事实请与原文对照。"
    : !hasOriginalBody
      ? "来源未提供可解析的正文。以下仅展示已取得的标题和摘要，可前往原站阅读。"
      : article.body_status === "full_text" && isEnglish
        ? `${translationLabel(article.translation_status)}。以下显示已取得的英文原文。`
        : article.body_status !== "full_text"
          ? "来源只提供了部分内容，以下显示可获取的原文材料。"
          : "以下显示已取得的原文正文。";

  return (
    <main data-reading-page className={styles.shell}>
      <header className={styles.topbar}>
        <Link href="/" className={styles.brand}>BLUE PULSE<span> / 警务科技情报</span></Link>
        <Link href="/articles" className={styles.topbarLink}>情报列表 ↗</Link>
      </header>
      <nav className={styles.breadcrumb} aria-label="当前位置">
        <Link href="/articles">情报库</Link><span>/</span><span>文章详情</span>
      </nav>

      <article className={styles.detailLayout}>
        <div className={styles.detailMain}>
          <div className={styles.detailKicker}>ARTICLE / {formatRegion(article.region)} / {evidenceLabel(article.body_status)}</div>
          <h1 className={styles.detailTitle}>{article.title}</h1>
          {article.source_title !== article.title ? (
            <p className={styles.detailOriginalTitle}>{article.source_title}</p>
          ) : null}
          <div className={styles.detailMeta}>
            <span>{article.source.name}</span>
            <span aria-hidden="true">·</span>
            <time>{formatArticleTimeline(article)}</time>
            {article.author ? <><span aria-hidden="true">·</span><span>{article.author}</span></> : null}
          </div>
          <div className={styles.detailDivider} />

          <section className={styles.abstract} aria-labelledby="abstract-title">
            <div className={styles.sectionHeading}><span>01</span><h2 id="abstract-title">情报摘要</h2></div>
            <p>{article.summary?.trim() || "暂无可靠的中文摘要。请直接核对下方原文或原站资料。"}</p>
          </section>

          <section className={styles.bodySection} aria-labelledby="body-title">
            <div className={styles.sectionHeading}><span>02</span><h2 id="body-title">正文材料</h2></div>
            <div className={styles.contentNotice} role="note">
              <span className={styles.noticeDot} aria-hidden="true" />{bodyNote}
            </div>
            {hasChineseBody ? (
              <>
                <div className={styles.bodyText}>{article.zh_body}</div>
                <details className={styles.originalDisclosure}>
                  <summary>对照英文原文 <span aria-hidden="true">＋</span></summary>
                  <div className={styles.originalText}>{article.source_body}</div>
                </details>
              </>
            ) : hasOriginalBody ? (
              <div className={`${styles.bodyText} ${isEnglish ? styles.originalText : ""}`}>
                {article.source_body}
              </div>
            ) : null}
          </section>

          {article.media.length > 0 ? (
            <section className={styles.mediaSection} aria-labelledby="media-title">
              <div className={styles.sectionHeading}><span>03</span><h2 id="media-title">相关媒体</h2></div>
              <ul>
                {article.media.map((media, index) => {
                  const mediaUrl = safeSourceUrl(media.url);
                  return mediaUrl ? (
                    <li key={`${media.url}-${index}`}>
                      <a href={mediaUrl} target="_blank" rel="noopener noreferrer">
                        {media.caption || media.alt_text || `${media.kind} ${index + 1}`} ↗
                      </a>
                    </li>
                  ) : null;
                })}
              </ul>
            </section>
          ) : null}
        </div>

        <aside className={styles.detailAside} aria-label="来源信息">
          <div className={styles.asideCard}>
            <span className={styles.asideIndex}>SOURCE / 资料来源</span>
            <h2>{article.source.name}</h2>
            <dl>
              <div><dt>发布日期</dt><dd>{formatArticleDate(article.published_at)}</dd></div>
              <div><dt>原文语言</dt><dd>{isEnglish ? "英语" : "中文"}</dd></div>
              <div><dt>正文状态</dt><dd>{evidenceLabel(article.body_status)}</dd></div>
              <div><dt>中文全文</dt><dd>{translationLabel(article.translation_status)}</dd></div>
            </dl>
            {sourceUrl ? (
              <a className={styles.sourceButton} href={sourceUrl} target="_blank" rel="noopener noreferrer">
                前往原始来源 <span aria-hidden="true">↗</span>
              </a>
            ) : null}
          </div>
          <div className={styles.asideTopics}>
            <span className={styles.asideIndex}>TOPICS / 主题</span>
            <div>{article.topics.map((topic) => (
              <Link key={topic} href={`/articles?topic=${encodeURIComponent(topic)}`}>
                {topicNames.get(topic) ?? topic} ↗
              </Link>
            ))}</div>
          </div>
          {article.entities.length > 0 ? (
            <div className={styles.asideTopics}>
              <span className={styles.asideIndex}>ENTITIES / 厂商与模型</span>
              <div>{article.entities.map((entity) => (
                <Link key={entity.slug} href={`/articles?period=all&entity=${encodeURIComponent(entity.slug)}`}>
                  {entity.name} ↗
                </Link>
              ))}</div>
            </div>
          ) : null}
          <p className={styles.asideFootnote}>Blue Pulse 对公开材料进行整理。模型生成的标题、摘要与译文不代替原始资料。</p>
        </aside>
      </article>
      <div className={styles.detailBottom}><Link href="/articles">← 返回情报列表</Link></div>
      <footer className={styles.footer}>BLUE PULSE <span>以原始来源为准 · 不将模型整理内容视作独立事实</span></footer>
    </main>
  );
}
