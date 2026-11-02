"use client";
// AIHOT item.tsx / item-original.tsx (MIT), retaining the reading composition and conditions.
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import { lazy, Suspense, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { RouteReady, useMainShell } from "../../_components/home/MainShell";
import { useBrowserState } from "../../_lib/use-browser-state";
import type { FeedArticle } from "../../_lib/feed-types";
import { SameEventBadge, SelectedBadge } from "../../_components/feed/Badge";
import { ScoreLabel } from "../../_components/feed/parts";
import { PillTabs } from "../../_components/feed/PillTabs";
import { IntentLink } from "../../_components/feed/IntentLink";
import { GroupButton, GroupSources } from "../../_components/feed/ReadingGroup";
import { IconBookmark, IconExternal } from "../../_components/feed/icons";
import { ARTICLE_TOPIC_LABELS } from "../../_components/home/article-topic-labels";
import { CONTENT_FILTERS } from "../../all/_data";
import { safeSourceUrl } from "../_data";
import { getCachedArticle, invalidateArticle, loadArticle, primeArticle } from "./cache";
import { articleRoute, emptyArticlePage } from "./data";
import { takeArticlePreview } from "./preview";
import type { ArticlePageData, ReaderArticle } from "./types";
import { ArticleLayout, RailSection, ReaderBack, ReaderHeader } from "./ReaderLayout";
import { ActionsSheet, MoreMenu, OutlineSheet, ReaderToolbar, ReadingProgress, Toast, actionIcons, useReaderStar, useReaderToast, type ActionRow } from "./ReaderTools";
import { ArticleBody } from "./ArticleBody";
import { MediaGallery, QuotedPost } from "./ReaderMedia";
import { StoryFollowups } from "./StoryFollowups";
import { fullDateTime, hostOf, relativeTime, isCompactReader } from "./format";
import { compactReaderContainer, scrollToSection } from "./scroll";
import styles from "./reader.module.css";

const PosterSheet = lazy(() => import("./PosterSheet"));

/** Keep browser history snapshots to the same card fields as feeds, never article bodies. */
function readingCard(item: ReaderArticle): FeedArticle {
  const article = item.article;
  return {
    id: article.id, title: article.title, source_title: article.source_title, summary: article.summary,
    published_at: article.published_at, first_seen_at: article.first_seen_at,
    language: article.language, url: article.url, importance_score: article.importance_score,
    parse_status: article.parse_status, body_status: article.body_status, translation_status: article.translation_status,
    region: article.region === "domestic" || article.region === "foreign" ? article.region : null,
    country_code: null, processing_status: "unknown", topics: article.topics,
    source: { ...article.source, region: null, country_code: null, language: article.language, topics: [] },
    selected: item.selected, sameEvent: item.sameEvent, featured_reason: item.reason, channel: item.channel, x: item.x,
  };
}

export function ArticlePage({ initial }: { initial?: ArticlePageData }) {
  const shell = useMainShell();
  const [loaded, setLoaded] = useState(() => ({ activation: shell.activation, data: getCachedArticle(shell.routeKey, shell.mock) ?? (!shell.restore && initial?.key === shell.routeKey ? initial : emptyArticlePage(shell.routeKey)) }));
  const [preview, setPreview] = useState<{ key: string; article: FeedArticle } | null>(null), [retry, setRetry] = useState(0);
  const previous = useRef({ key: shell.routeKey, revision: shell.refreshRevision, retry });
  const usedInitial = useRef<ArticlePageData | null>(null);
  useEffect(() => {
    if (shell.activation.key !== shell.routeKey) return;
    let active = true;
    const before = previous.current, key = shell.routeKey;
    const force = before.key === key && (before.revision !== shell.refreshRevision || before.retry !== retry);
    previous.current = { key, revision: shell.refreshRevision, retry };
    const freshInitial = !force && initial?.key === key && usedInitial.current !== initial && (!shell.restore || initial.expiresAt > Date.now()) ? initial : null;
    if (freshInitial) usedInitial.current = freshInitial;
    const cached = freshInitial ?? (!force ? getCachedArticle(key, shell.mock) : null);
    const route = articleRoute(shell.pathname);
    const fromCard = !cached && !shell.restore && route && compactReaderContainer() ? takeArticlePreview(route.id, shell.mock) : null;
    queueMicrotask(() => {
      if (!active) return;
      setPreview(fromCard ? { key, article: fromCard } : null);
      if (cached) { if (freshInitial) primeArticle(freshInitial, shell.mock); setLoaded({ activation: shell.activation, data: cached }); return; }
      setLoaded({ activation: shell.activation, data: emptyArticlePage(key) });
      void loadArticle(key, shell.mock, { force }).then(data => {
        if (active) { setLoaded({ activation: shell.activation, data }); setPreview(null); }
      });
    });
    return () => { active = false; };
  }, [initial, shell.activation, shell.routeKey, shell.pathname, shell.mock, shell.restore, shell.refreshRevision, retry]);
  const current: ArticlePageData = loaded.data.key === shell.routeKey && (loaded.activation === shell.activation || shell.activation.key !== shell.routeKey)
    ? loaded.data : getCachedArticle(shell.routeKey, shell.mock) ?? emptyArticlePage(shell.routeKey);
  const pendingPreview = preview?.key === shell.routeKey && current.status === "loading" ? preview.article : null;
  const again = () => { invalidateArticle(shell.routeKey, shell.mock); setRetry(value => value + 1); };
  return <><RouteReady ready={current.status !== "loading"} />
    {current.item && current.status === "ready" ? <ItemView key={`${current.item.article.id}:${current.item.bodyLanguage}`} item={current.item} taxonomy={current.taxonomy} />
      : pendingPreview ? <ItemPreview article={pendingPreview} />
      : <div className={styles.reader} data-article-status={current.status}><ReaderHeader title="" />{current.status === "loading" ? null : <div className={styles.unavailable}><h1>{current.status === "not-found" ? "这里没有内容" : "暂时无法加载"}</h1><p>{current.status === "not-found" ? "这篇内容不存在，或已不再公开。" : "服务暂时繁忙，请稍后再试。"}</p>{current.status === "error" && <button type="button" onClick={again}>重试</button>}<ReaderBack /></div>}</div>}
  </>;
}

export function ArticleLoading() {
  const shell = useMainShell(), [preview, setPreview] = useState<FeedArticle | null>(null);
  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active || !compactReaderContainer() || shell.restore) return;
      const route = articleRoute(shell.pathname);
      if (route) setPreview(takeArticlePreview(route.id, shell.mock));
    });
    return () => { active = false; };
  }, [shell.pathname, shell.mock, shell.restore]);
  return <><RouteReady ready={false} />{preview ? <ItemPreview article={preview} /> : <div className={styles.reader} data-article-status="loading" />}</>;
}

function ItemPreview({ article }: { article: FeedArticle }) {
  const shell = useMainShell(), star = useReaderStar(article), [toast, setToast] = useReaderToast();
  const isX = article.channel === "x" && !!article.x, at = article.published_at ?? article.first_seen_at;
  return <div className={styles.reader} data-article-status="preview"><ReaderHeader title={isX ? article.x!.authorName : article.title} selected={article.selected} /><article className={styles.preview} aria-busy="true"><div className={styles.inlineMeta}>{article.source.name} · {!article.published_at && "收录于 "}{fullDateTime(at)}</div>{!isX && <h1 className={styles.title} data-page-title>{article.title}</h1>}{article.summary && <section className={styles.summary}><h2>AI 导读</h2><p>{article.summary}</p></section>}{article.featured_reason && <section className={styles.mobileReason}><h2>推荐理由</h2><p>{article.featured_reason}</p></section>}<div className={styles.previewSkeleton} aria-hidden="true">{[92, 100, 96, 88, 98, 64].map((width, index) => <div key={index} style={{ width: `${width}%` }} />)}</div></article><ReaderToolbar saved={star.on} toggle={star.toggle} onShare={() => { void shareArticle(article.id, article.title, shell.href).then(result => { if (result === "copied") setToast("链接已复制"); }); }} originalLabel={isX ? "原推" : "原文"} wide={false} /><Toast text={toast} /></div>;
}

async function shareArticle(id: string, title: string, href: (value: string) => string): Promise<"shared" | "copied" | null> {
  const url = new URL(href(`/articles/${id}`), location.origin).href;
  try {
    if (navigator.share && matchMedia("(pointer: coarse)").matches) { await navigator.share({ title, url }); return "shared"; }
    await navigator.clipboard.writeText(`${title}\n${url}`); return "copied";
  } catch { return null; }
}

function ItemView({ item, taxonomy }: { item: ReaderArticle; taxonomy: ArticlePageData["taxonomy"] }) {
  const shell = useMainShell(), { store } = useBrowserState(shell.mock), article = item.article;
  const star = useReaderStar(article), [toast, setToast] = useReaderToast(), root = useRef<HTMLDivElement>(null);
  const [wide, setWide] = useState(false), [posterRequested, setPosterRequested] = useState(false), [posterOpen, setPosterOpen] = useState(false), [outlineOpen, setOutlineOpen] = useState(false), [actionsOpen, setActionsOpen] = useState(false);
  const snapshot = useMemo(() => readingCard(item), [item]);
  useEffect(() => { store.recordRead(snapshot); }, [snapshot, store]);
  useLayoutEffect(() => {
    if (!root.current) return;
    const update = () => { const rem = Number.parseFloat(getComputedStyle(document.documentElement).fontSize) || 16; setWide(!isCompactReader(root.current?.clientWidth ?? 0, rem)); };
    update(); const observer = new ResizeObserver(update); observer.observe(root.current);
    return () => observer.disconnect();
  }, []);
  const closePoster = useCallback(() => setPosterOpen(false), []);
  const openPoster = () => { setPosterRequested(true); setPosterOpen(true); };
  const share = () => { void shareArticle(article.id, article.title, shell.href).then(result => { if (result === "copied") setToast("链接已复制"); }); };
  const copyLink = async () => { try { await navigator.clipboard.writeText(new URL(shell.href(`/articles/${article.id}`), location.origin).href); setToast("链接已复制"); } catch { /* clipboard unavailable */ } };
  const copyMarkdown = async () => {
    try {
      if (shell.mock) throw Error("demo");
      const response = await fetch(`/api/bluepulse/articles/${article.id}/markdown`, { cache: "no-store" });
      if (!response.ok || !response.headers.get("content-type")?.startsWith("text/markdown")) throw Error(String(response.status));
      await navigator.clipboard.writeText(await response.text()); setToast("Markdown 已复制");
    } catch { setToast("复制失败，请在浏览器中打开后导出"); }
  };
  const isX = item.channel === "x" && !!item.x, summaryOnly = item.readingMode === "summary-only", showOutline = item.outline.length >= 3;
  const sourceUrl = safeSourceUrl(article.url), shownAt = article.published_at ?? article.first_seen_at;
  const score = summaryOnly ? null : article.importance_score;
  const bodyLabel = item.zhKind === "translation" && item.bodyLanguage === "zh" ? "正文 · AI 翻译" : item.bodyLanguage === "original" && item.hasTranslation ? "正文 · 原文" : "正文";
  const weChat = typeof navigator !== "undefined" && /MicroMessenger/i.test(navigator.userAgent);
  const rows: ActionRow[] = [
    { key: "poster", label: "生成分享海报", icon: actionIcons.poster, onSelect: openPoster },
    { key: "copy", label: "复制链接", icon: actionIcons.copy, onSelect: () => void copyLink() },
    ...(item.markdownAvailable ? [{ key: "markdown", label: weChat ? "复制 Markdown" : "导出 Markdown", icon: actionIcons.markdown, ...(weChat || shell.mock ? { onSelect: () => void copyMarkdown() } : { href: `/api/bluepulse/articles/${article.id}/markdown`, download: true }) }] : []),
  ];
  const verdict = (item.selected || Number.isFinite(score)) && <div className={styles.verdict}>{item.selected && (item.sameEvent ? <SameEventBadge /> : <SelectedBadge />)}{score !== null && <ScoreLabel score={score} />}</div>;
  const facts = <RailSection title="来源"><div className={styles.sourceName}>{isX ? item.x!.authorName : article.source.name}</div><div className={styles.sourceAuthor}>{isX ? `@${item.x!.handle} · X` : article.author ?? hostOf(article.url)}</div><div className={styles.timeLabel}>{article.published_at ? "发布时间" : "收录时间"}</div><time dateTime={shownAt ?? undefined} className={styles.sourceTime}>{fullDateTime(shownAt)}</time><div className={styles.relative} suppressHydrationWarning>{relativeTime(shownAt)}</div></RailSection>;
  const outline = showOutline && <RailSection title="本文目录"><nav aria-label="本文目录"><ol className={styles.outline}>{item.outline.map(entry => <li key={entry.id}><a href={`#${entry.id}`} data-nested={entry.level > 2} onClick={event => { if (event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) { event.preventDefault(); scrollToSection(entry.id); } }}>{entry.text}</a></li>)}</ol></nav></RailSection>;
  const topicName = (topic: string) => CONTENT_FILTERS.find(filter => filter.key === topic)?.label ?? taxonomy.find(entry => entry.slug === topic)?.name_zh ?? ARTICLE_TOPIC_LABELS[topic] ?? topic;
  const chips = (limit: number) => <div className={styles.chips}>{article.topics.map(topic => <IntentLink key={topic} href={shell.href(`/all?topic=${encodeURIComponent(topic)}`)}>{topicName(topic)}</IntentLink>)}{item.tags.slice(0, limit).map(tag => <IntentLink key={tag} href={shell.href(`/all?tag=${encodeURIComponent(tag)}`)}>#{tag}</IntentLink>)}</div>;
  const notes = <>{item.reason && !summaryOnly ? <RailSection title="推荐理由">{verdict}<p className={styles.noteText}>{item.reason}</p></RailSection> : verdict && <RailSection title={score !== null ? "AI 评分" : undefined}>{verdict}</RailSection>}{article.topics.length > 0 && <RailSection title="分类"><div className={styles.chips}>{article.topics.map(topic => <IntentLink key={topic} href={shell.href(`/all?topic=${encodeURIComponent(topic)}`)}>{topicName(topic)}</IntentLink>)}</div></RailSection>}{item.tags.length > 0 && <RailSection title="标签"><div className={styles.chips}>{item.tags.slice(0, 8).map(tag => <IntentLink key={tag} href={shell.href(`/all?tag=${encodeURIComponent(tag)}`)}>#{tag}</IntentLink>)}</div></RailSection>}</>;
  const actions = <div className={styles.desktopActions}>{sourceUrl && <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className={styles.originalLink}>{isX ? "在 X 查看原推" : "打开原文"}<IconExternal size={13} /></a>}<button type="button" className={styles.iconButton} aria-label={star.on ? "取消收藏" : "收藏"} aria-pressed={star.on} onClick={star.toggle}><IconBookmark size={18} filled={star.on} /></button><MoreMenu rows={rows} onShare={share} /></div>;
  const related = item.relatedStories.filter(story => story.publicId !== item.story?.publicId);
  return <div ref={root} className={styles.reader} data-article-status="ready" data-reading-page>
    {item.bodyHtml && <ReadingProgress />}
    <ReaderHeader title={isX ? item.x!.authorName : article.title} selected={item.selected} onMore={() => setActionsOpen(true)} />
    <ArticleLayout left={<><ReaderBack selected={item.selected} />{facts}{outline}</>} right={<>{actions}{notes}<div className={styles.middleOutline}>{outline}</div></>}>
      <div className={styles.middleBack}><ReaderBack selected={item.selected} /></div>
      <article className={styles.article}>
        <div className={styles.inlineMeta}><strong>{isX ? item.x!.authorName : article.source.name}</strong>{isX && <span>· @{item.x!.handle} · X</span>}{article.author && !isX && <span>· {article.author}</span>}<span>·</span>{!article.published_at && <span>收录于</span>}<time dateTime={shownAt ?? undefined}>{fullDateTime(shownAt)}</time><span suppressHydrationWarning>· {relativeTime(shownAt)}</span><span className={styles.inlineVerdict}>{verdict}</span></div>
        {!isX && <h1 className={styles.title} data-page-title>{article.title}</h1>}
        {!isX && article.source_title && article.source_title !== article.title && <p className={styles.originalTitle}>{article.source_title}</p>}
        {article.summary && (!isX || article.summary.replace(/\s+/g, " ").trim() !== article.title) && <section className={styles.summary} data-x={isX}><h2>{summaryOnly ? "摘要" : "AI 导读"}</h2><p>{article.summary}</p></section>}
        {item.reason && !summaryOnly && <section className={styles.mobileReason}><h2>推荐理由</h2><p>{item.reason}</p></section>}
        {item.sameEvent && <p className={styles.sameEvent}>同一新闻，精选展示<IntentLink href={shell.href(`/articles/${item.sameEvent.id}`)}>《{item.sameEvent.title}》</IntentLink></p>}
        {item.group && item.group.reportCount > 1 && <div className={styles.group}><div className={styles.desktopGroup}><GroupSources group={item.group} parentId={article.id} /></div><div className={styles.mobileGroup}><GroupButton group={item.group} parentId={article.id} /></div></div>}
        {summaryOnly && <p className={styles.contentNotice}>应来源方要求，这里只提供摘要与原文入口。完整内容请阅读原文。</p>}
        {item.bodyHtml && <section className={styles.bodySection}><div className={styles.bodyHeading}><span>{bodyLabel}</span>{item.hasTranslation && <PillTabs size="xs" label="正文语言" active={item.bodyLanguage} items={[{ key: "zh", label: "中文", prefetch: "intent", replace: true, to: shell.href(`/articles/${article.id}`) }, { key: "original", label: "原文", prefetch: "intent", replace: true, to: shell.href(`/articles/${article.id}/original`) }]} />}</div>{item.hasTranslation && item.bodyLanguage === "zh" && !item.complete && <p className={styles.partialNotice}>译文尚不完整，完整内容请切换到原文。</p>}<ArticleBody html={item.bodyHtml} /></section>}
        {isX && item.x!.media.length > 0 && <MediaGallery media={item.x!.media} postUrl={sourceUrl ?? ""} />}
        {isX && item.x!.quoted?.text && <QuotedPost quoted={item.x!.quoted} original={item.bodyLanguage === "original"} />}
        <p className={styles.sourceFoot}>来源：{sourceUrl ? <a href={sourceUrl} target="_blank" rel="noopener noreferrer">{isX ? item.x!.authorName : article.source.name}</a> : article.source.name}<span> · {hostOf(article.url)}</span></p>
        {(article.topics.length > 0 || item.tags.length > 0) && <div className={styles.mobileChips}>{chips(6)}</div>}
        {item.story && <StoryFollowups story={item.story} currentId={article.id} />}
        {related.length > 0 && <section className={styles.related}><h2>相关事件</h2><ul>{related.map(story => <li key={story.publicId}><IntentLink href={shell.href(`/story/${story.publicId}`)}>{story.title}</IntentLink></li>)}</ul></section>}
      </article>
    </ArticleLayout>
    <ReaderToolbar saved={star.on} toggle={star.toggle} onOutline={showOutline ? () => setOutlineOpen(true) : undefined} onShare={share} originalUrl={sourceUrl} originalLabel={isX ? "原推" : "原文"} wide={wide} />
    {showOutline && <OutlineSheet open={outlineOpen} onClose={() => setOutlineOpen(false)} outline={item.outline} />}
    <ActionsSheet open={actionsOpen} onClose={() => setActionsOpen(false)} rows={rows} />
    {posterRequested && <Suspense fallback={null}><PosterSheet id={article.id} title={article.title} open={posterOpen} onClose={closePoster} mock={shell.mock} /></Suspense>}
    <Toast text={toast} />
  </div>;
}
