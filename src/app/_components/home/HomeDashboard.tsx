"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { useGSAP } from "@gsap/react";
import { gsap } from "gsap";
import Image from "next/image";
import {
  fetchArticleDetail,
  fetchHomeArticles,
  fetchHomeFeatured,
  fetchSources,
  fetchTaxonomy,
  type ArticleCard,
  type ArticleDetail,
  type ArticlePeriod,
  type ArticleRegion,
  type ArticleSort,
  type Source,
  type Topic,
} from "../../_lib/home-data";
import {
  MOCK_ARTICLE_DETAILS,
  MOCK_HOME_DATA,
  MOCK_HOME_FEATURED,
  MOCK_SOURCES,
  MOCK_TAXONOMY,
} from "../../_lib/home-mock";
import { BranchedTopicMenu } from "./BranchedTopicMenu";
import { TOPIC_MENU_SLUGS } from "./topic-menu-config";
import styles from "./home.module.css";
import type { PanelRect } from "../intro/intro-config";

gsap.registerPlugin(useGSAP);

type PageView =
  | { kind: "home" }
  | { kind: "search" }
  | { kind: "topic"; topic: Topic }
  | { kind: "history" }
  | { kind: "account" };
type ActiveView = PageView | { kind: "article"; id: string; from: PageView };
type ListStatus = "loading" | "ready" | "empty" | "error";
type DetailStatus = "loading" | "ready" | "error";
type HistoryEntry = { article: ArticleCard; viewedAt: string };
type Filters = {
  period: ArticlePeriod;
  topic: string;
  region: ArticleRegion | "";
  source: string;
  sourceType: string;
  q: string;
  sort: ArticleSort;
};

const HISTORY_STORAGE_KEY = "blue-pulse-reading-history-v1";
const PAGE_SIZE = 20;
const MOCK_PAGE_SIZE = 8;
const INITIAL_FILTERS: Filters = {
  period: "7d",
  topic: "",
  region: "",
  source: "",
  sourceType: "",
  q: "",
  sort: "recent",
};

function formatDateTime(value?: string | null): string {
  if (!value) return "时间待补";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间待补";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function articleDate(article: Pick<ArticleCard, "published_at" | "first_seen_at">): string | null {
  return article.published_at ?? article.first_seen_at ?? null;
}

function timeAgo(value: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return "刚刚阅读";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`;
  return `${Math.floor(seconds / 86400)} 天前`;
}

function regionLabel(region?: ArticleRegion | null): string {
  return region === "foreign" ? "国外" : region === "domestic" ? "国内" : "地区待识别";
}

function sourceTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    aggregator: "资讯聚合",
    government: "政府机构",
    media: "媒体",
    academic: "学术研究",
    organization: "组织机构",
  };
  return labels[type] ?? type;
}

function topicLabel(slug: string, topics: Topic[]): string {
  return topics.find((topic) => topic.slug === slug)?.name_zh ?? "主题";
}

function filterMockArticles(filters: Filters): ArticleCard[] {
  const query = filters.q.trim().toLocaleLowerCase();
  return MOCK_HOME_DATA.articles
    .filter((article) => {
      const haystack = `${article.title} ${article.source_title} ${article.summary ?? ""}`.toLocaleLowerCase();
      return (
        (!filters.topic || article.topics?.includes(filters.topic)) &&
        (!filters.region || article.region === filters.region) &&
        (!filters.source || article.source.id === filters.source) &&
        (!filters.sourceType || article.source.source_type === filters.sourceType) &&
        (!query || haystack.includes(query))
      );
    })
    .sort((a, b) =>
      filters.sort === "importance"
        ? b.importance_score - a.importance_score
        : (articleDate(b) ?? "").localeCompare(articleDate(a) ?? ""),
    );
}

function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.7,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true as const,
  };
  if (name === "search") return <svg {...common}><circle cx="10.8" cy="10.8" r="6.8" /><path d="m16 16 4.5 4.5" /></svg>;
  if (name === "clock") return <svg {...common}><circle cx="12" cy="12" r="8.5" /><path d="M12 7v5l3.2 2" /></svg>;
  if (name === "user") return <svg {...common}><circle cx="12" cy="8" r="3.2" /><path d="M5.5 20c.8-3.2 3-4.8 6.5-4.8s5.7 1.6 6.5 4.8" /></svg>;
  if (name === "back") return <svg {...common}><path d="M19 12H5m0 0 6.2-6.2M5 12l6.2 6.2" /></svg>;
  if (name === "arrow") return <svg {...common}><path d="M5 12h14m0 0-6-6m6 6-6 6" /></svg>;
  if (name === "menu") return <svg {...common}><path d="M4 7h16M4 12h16M4 17h16" /></svg>;
  if (name === "close") return <svg {...common}><path d="m6 6 12 12M18 6 6 18" /></svg>;
  if (name === "external") return <svg {...common}><path d="M13 5h6v6M19 5l-9 9" /><path d="M18 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></svg>;
  if (name === "clear") return <svg {...common}><path d="M4 7h16M10 11v6m4-6v6M6.5 7l.8 13h9.4l.8-13M9 7V4h6v3" /></svg>;
  return <svg {...common}><circle cx="12" cy="12" r="8.5" /><path d="M12 11v5m0-8h.01" /></svg>;
}

function imagePreview(article: ArticleCard): string | null {
  const media = article.media_preview;
  if (media?.kind !== "image" || !media.url) return null;
  try {
    const url = new URL(media.thumbnail_url || media.url);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

export function HomeDashboard({ mock = false, p0Rect }: { mock?: boolean; p0Rect?: PanelRect }) {
  const [view, setView] = useState<ActiveView>({ kind: "home" });
  const [menuOpen, setMenuOpen] = useState(false);
  const [filters, setFilters] = useState<Filters>(INITIAL_FILTERS);
  const [draftQuery, setDraftQuery] = useState("");
  const [loadedTopics, setLoadedTopics] = useState<Topic[]>([]);
  const [loadedSources, setLoadedSources] = useState<Source[]>([]);
  const [loadedFeatured, setLoadedFeatured] = useState<ArticleCard[]>([]);
  const [loadedFeaturedStatus, setLoadedFeaturedStatus] = useState<ListStatus>("loading");
  const [featuredError, setFeaturedError] = useState("");
  const [loadedTopicStatus, setLoadedTopicStatus] = useState<ListStatus>("loading");
  const [loadedSourceStatus, setLoadedSourceStatus] = useState<ListStatus>("loading");
  const [listResult, setListResult] = useState<{
    key: string;
    status: ListStatus;
    articles: ArticleCard[];
    nextCursor: string | null;
    error: string;
  } | null>(null);
  const [pageCursors, setPageCursors] = useState<(string | null)[]>([null]);
  const [pageIndex, setPageIndex] = useState(0);
  const [detail, setDetail] = useState<ArticleDetail | null>(null);
  const [detailStatus, setDetailStatus] = useState<DetailStatus>("loading");
  const [detailError, setDetailError] = useState("");
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [historyReady, setHistoryReady] = useState(false);
  const [historyCleared, setHistoryCleared] = useState(false);
  const dashboardRef = useRef<HTMLDivElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  const scrimRef = useRef<HTMLButtonElement>(null);
  const mobileBarRef = useRef<HTMLDivElement>(null);
  const viewStageRef = useRef<HTMLDivElement>(null);
  const readingAreaRef = useRef<HTMLElement>(null);
  const savedScrollPositions = useRef(new Map<string, number>());
  const activeViewRef = useRef<ActiveView>(view);
  const articleCardsRef = useRef<ArticleCard[]>([]);
  const contextSafeRef = useRef<((callback: () => void) => () => void) | null>(null);
  const introTimelineRef = useRef<gsap.core.Timeline | null>(null);
  const viewTransitionTimelineRef = useRef<gsap.core.Timeline | null>(null);
  const menuTimelineRef = useRef<gsap.core.Timeline | null>(null);
  const transitionLockedRef = useRef(false);
  const pendingRevealRef = useRef(false);
  const reducedMotionRef = useRef(false);
  const historyStorageKey = mock ? `${HISTORY_STORAGE_KEY}:mock` : HISTORY_STORAGE_KEY;
  const dashboardStyle = p0Rect
    ? {
        "--p0-left": `${p0Rect.x}px`,
        "--p0-top": `${p0Rect.y}px`,
        "--p0-width": `${p0Rect.width}px`,
        "--p0-height": `${p0Rect.height}px`,
      } as CSSProperties
    : undefined;

  const topics = mock ? MOCK_TAXONOMY.items : loadedTopics;
  const topicMenuTopics = useMemo(() => topics.filter((topic) => TOPIC_MENU_SLUGS.has(topic.slug)), [topics]);
  const sources = mock ? MOCK_SOURCES.items : loadedSources;
  const featured = mock ? MOCK_HOME_FEATURED.items.map((item) => item.article) : loadedFeatured;
  const featuredStatus = mock ? "ready" : loadedFeaturedStatus;
  const topicStatus = mock ? "ready" : loadedTopicStatus;
  const sourceStatus = mock ? "ready" : loadedSourceStatus;

  const getViewKey = useCallback((target: ActiveView): string => {
    if (target.kind === "article") return `article:${target.id}`;
    if (target.kind === "topic") return `topic:${target.topic.slug}`;
    return target.kind;
  }, []);

  const runGsap = useCallback((callback: () => void) => {
    const safeCallback = contextSafeRef.current?.(callback);
    if (safeCallback) safeCallback();
    else callback();
  }, []);

  const transitionTo = useCallback((next: ActiveView) => {
    const current = activeViewRef.current;
    if (getViewKey(current) === getViewKey(next) || transitionLockedRef.current) return;

    if (current.kind !== "article" && readingAreaRef.current) {
      savedScrollPositions.current.set(getViewKey(current), readingAreaRef.current.scrollTop);
    }

    transitionLockedRef.current = true;
    pendingRevealRef.current = true;
    setMenuOpen(false);

    const commit = () => {
      activeViewRef.current = next;
      setView(next);
    };

    runGsap(() => {
      const stage = viewStageRef.current;
      viewTransitionTimelineRef.current?.kill();
      if (!stage || reducedMotionRef.current) {
        commit();
        return;
      }
      viewTransitionTimelineRef.current = gsap.timeline({
        onComplete: commit,
        defaults: { overwrite: "auto" },
      }).to(stage, {
        autoAlpha: 0.12,
        y: -8,
        duration: 0.22,
        ease: "power2.in",
      });
    });
  }, [getViewKey, runGsap]);

  const navigate = useCallback((next: PageView) => {
    transitionTo(next);
  }, [transitionTo]);

  useGSAP(
    (_context, contextSafe) => {
      contextSafeRef.current = contextSafe ?? null;
      const root = dashboardRef.current;
      const sidebar = sidebarRef.current;
      const scrim = scrimRef.current;
      const mobileBar = mobileBarRef.current;
      const stage = viewStageRef.current;
      if (!root || !sidebar || !scrim || !mobileBar || !stage) return;

      const select = gsap.utils.selector(root);
      const staggerItems = select<HTMLElement>("[data-home-stagger]");
      const isMobile = window.matchMedia("(max-width: 768px)").matches;
      const matchMedia = gsap.matchMedia();

      matchMedia.add("(prefers-reduced-motion: reduce)", () => {
        reducedMotionRef.current = true;
        gsap.set([stage, mobileBar, staggerItems], {
          autoAlpha: 1,
          clearProps: "transform",
        });
        gsap.set(sidebar, { autoAlpha: isMobile ? 0 : 1, clearProps: "transform" });
        gsap.set(scrim, { autoAlpha: 0 });
      });

      matchMedia.add("(prefers-reduced-motion: no-preference)", () => {
        reducedMotionRef.current = false;
        gsap.set(stage, { autoAlpha: 0, y: 10 });
        gsap.set(staggerItems, { autoAlpha: 0, y: 8 });
        gsap.set(mobileBar, { autoAlpha: isMobile ? 0 : 1, y: isMobile ? -8 : 0 });
        if (isMobile) {
          gsap.set(sidebar, { autoAlpha: 0, xPercent: -108 });
          gsap.set(scrim, { autoAlpha: 0 });
        } else {
          gsap.set(sidebar, { autoAlpha: 0, y: 10 });
        }

        introTimelineRef.current?.kill();
        introTimelineRef.current = gsap.timeline({ defaults: { ease: "power3.out" } })
          .to(isMobile ? mobileBar : sidebar, {
            autoAlpha: 1,
            xPercent: isMobile ? 0 : undefined,
            y: 0,
            duration: 0.5,
          })
          .to(stage, {
            autoAlpha: 1,
            y: 0,
            duration: 0.44,
          }, "<0.1")
          .to(staggerItems, {
            autoAlpha: 1,
            y: 0,
            duration: 0.36,
            stagger: 0.025,
          }, "<0.04");
      });

      return () => {
        matchMedia.revert();
        introTimelineRef.current?.kill();
        viewTransitionTimelineRef.current?.kill();
        menuTimelineRef.current?.kill();
        contextSafeRef.current = null;
      };
    },
    { scope: dashboardRef },
  );

  useEffect(() => {
    if (!pendingRevealRef.current) return;
    pendingRevealRef.current = false;
    const frame = requestAnimationFrame(() => {
      runGsap(() => {
        const stage = viewStageRef.current;
        if (!stage) {
          transitionLockedRef.current = false;
          return;
        }
        const staggerItems = stage.querySelectorAll<HTMLElement>("[data-home-stagger]");
        if (reducedMotionRef.current) {
          gsap.set([stage, staggerItems], { autoAlpha: 1, clearProps: "transform" });
          transitionLockedRef.current = false;
          return;
        }
        viewTransitionTimelineRef.current?.kill();
        viewTransitionTimelineRef.current = gsap.timeline({
          onComplete: () => { transitionLockedRef.current = false; },
          defaults: { ease: "power2.out" },
        })
          .fromTo(stage, { autoAlpha: 0.12, y: 8 }, { autoAlpha: 1, y: 0, duration: 0.4 })
          .fromTo(staggerItems, { autoAlpha: 0, y: 7 }, { autoAlpha: 1, y: 0, duration: 0.3, stagger: 0.022 }, "<0.04");
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [runGsap, view]);

  useEffect(() => {
    const sidebar = sidebarRef.current;
    const scrim = scrimRef.current;
    if (!sidebar || !scrim || !window.matchMedia("(max-width: 768px)").matches) return;
    runGsap(() => {
      menuTimelineRef.current?.kill();
      if (reducedMotionRef.current) {
        gsap.set(sidebar, { autoAlpha: menuOpen ? 1 : 0, xPercent: menuOpen ? 0 : -108 });
        gsap.set(scrim, { autoAlpha: menuOpen ? 1 : 0 });
        return;
      }
      menuTimelineRef.current = gsap.timeline({ defaults: { ease: "power3.out" } })
        .to(sidebar, { autoAlpha: menuOpen ? 1 : 0, xPercent: menuOpen ? 0 : -108, duration: 0.28 })
        .to(scrim, { autoAlpha: menuOpen ? 1 : 0, duration: 0.22 }, menuOpen ? "<0.04" : 0);
    });
  }, [menuOpen, runGsap]);

  useEffect(() => {
    let active = true;
    try {
      const stored = window.localStorage.getItem(historyStorageKey);
      if (stored) {
        const parsed = JSON.parse(stored) as unknown;
        if (Array.isArray(parsed)) {
          const restored = parsed.filter((entry): entry is HistoryEntry =>
            Boolean(entry && typeof entry === "object" && "article" in entry && "viewedAt" in entry),
          ).slice(0, 30);
          queueMicrotask(() => {
            if (active) setHistory(restored);
          });
        }
      }
    } catch {
      // A blocked or malformed history store is treated as an empty session.
    } finally {
      queueMicrotask(() => {
        if (active) setHistoryReady(true);
      });
    }
    return () => { active = false; };
  }, [historyStorageKey]);

  useEffect(() => {
    if (!historyReady) return;
    try {
      window.localStorage.setItem(historyStorageKey, JSON.stringify(history));
    } catch {
      // Reading history remains available for this session when storage is blocked.
    }
  }, [history, historyReady, historyStorageKey]);

  useEffect(() => {
    if (mock) return;
    const controller = new AbortController();
    void Promise.allSettled([
      fetchHomeFeatured(controller.signal),
      fetchTaxonomy(controller.signal),
      fetchSources(controller.signal),
    ]).then(([featuredResult, topicsResult, sourcesResult]) => {
      if (controller.signal.aborted) return;
      if (featuredResult.status === "fulfilled") {
        const nextFeatured = featuredResult.value.items.map((item) => item.article);
        setLoadedFeatured(nextFeatured);
        setLoadedFeaturedStatus(nextFeatured.length ? "ready" : "empty");
        setFeaturedError("");
      } else {
        setLoadedFeatured([]);
        setLoadedFeaturedStatus("error");
        setFeaturedError(featuredResult.reason instanceof Error ? featuredResult.reason.message : "精选资讯暂时无法载入。");
      }
      if (topicsResult.status === "fulfilled") {
        setLoadedTopics(topicsResult.value.items);
        setLoadedTopicStatus(topicsResult.value.items.length ? "ready" : "empty");
      } else {
        setLoadedTopics([]);
        setLoadedTopicStatus("error");
      }
      if (sourcesResult.status === "fulfilled") {
        setLoadedSources(sourcesResult.value.items);
        setLoadedSourceStatus(sourcesResult.value.items.length ? "ready" : "empty");
      } else {
        setLoadedSources([]);
        setLoadedSourceStatus("error");
      }
    });
    return () => controller.abort();
  }, [mock]);

  useEffect(() => {
    if (mock) return;
    const cursor = pageCursors[pageIndex] ?? null;
    const requestKey = JSON.stringify({ filters, pageIndex, cursor });

    const params = new URLSearchParams({ period: filters.period, limit: String(PAGE_SIZE), sort: filters.sort });
    if (filters.topic) params.set("topic", filters.topic);
    if (filters.region) params.set("region", filters.region);
    if (filters.source) params.set("source", filters.source);
    if (filters.sourceType) params.set("source_type", filters.sourceType);
    if (filters.q.trim()) params.set("q", filters.q.trim());
    if (cursor) params.set("cursor", cursor);
    const controller = new AbortController();
    void fetchHomeArticles(params, controller.signal).then((response) => {
      setListResult({
        key: requestKey,
        status: response.items.length ? "ready" : "empty",
        articles: response.items,
        nextCursor: response.next_cursor,
        error: "",
      });
    }).catch((error: unknown) => {
      if (error instanceof Error && error.name === "AbortError") return;
      setListResult({
        key: requestKey,
        status: "error",
        articles: [],
        nextCursor: null,
        error: error instanceof Error ? error.message : "资讯暂时无法载入，请稍后再试。",
      });
    });
    return () => controller.abort();
  }, [filters, pageCursors, pageIndex, mock]);

  const currentCursor = pageCursors[pageIndex] ?? null;
  const listRequestKey = JSON.stringify({ filters, pageIndex, cursor: currentCursor });
  const mockListResult = useMemo(() => {
    const matching = filterMockArticles(filters);
    const offset = pageIndex * MOCK_PAGE_SIZE;
    const page = matching.slice(offset, offset + MOCK_PAGE_SIZE);
    return {
      status: page.length ? "ready" as const : "empty" as const,
      articles: page,
      nextCursor: offset + MOCK_PAGE_SIZE < matching.length ? String(offset + MOCK_PAGE_SIZE) : null,
      error: "",
    };
  }, [filters, pageIndex]);
  const visibleListResult = mock
    ? mockListResult
    : listResult?.key === listRequestKey
      ? listResult
      : { status: "loading" as const, articles: [], nextCursor: null, error: "" };
  const articles = visibleListResult.articles;
  const listStatus = visibleListResult.status;
  const listError = visibleListResult.error;
  const nextCursor = visibleListResult.nextCursor;

  useEffect(() => {
    articleCardsRef.current = [...articles, ...featured, ...history.map((entry) => entry.article)];
  }, [articles, featured, history]);

  useEffect(() => {
    const target = view.kind === "article" ? 0 : savedScrollPositions.current.get(getViewKey(view)) ?? 0;
    const frame = requestAnimationFrame(() => readingAreaRef.current?.scrollTo({ top: target, behavior: "instant" }));
    return () => cancelAnimationFrame(frame);
  }, [view, getViewKey]);

  useEffect(() => {
    if (view.kind !== "article") return;
    const card = articleCardsRef.current
      .find((article) => article.id === view.id);
    if (card) {
      setHistory((current) => [
        { article: card, viewedAt: new Date().toISOString() },
        ...current.filter((entry) => entry.article.id !== card.id),
      ].slice(0, 30));
    }
    setDetail(null);
    setDetailStatus("loading");
    setDetailError("");
    if (mock) {
      const mockDetail = MOCK_ARTICLE_DETAILS[view.id];
      if (mockDetail) {
        setDetail(mockDetail);
        setDetailStatus("ready");
      } else {
        setDetailError("这篇演示资讯没有详情内容。");
        setDetailStatus("error");
      }
      return;
    }
    const controller = new AbortController();
    void fetchArticleDetail(view.id, controller.signal).then((response) => {
      setDetail(response);
      setDetailStatus("ready");
    }).catch((error: unknown) => {
      if (error instanceof Error && error.name === "AbortError") return;
      setDetailError(error instanceof Error ? error.message : "文章详情暂时无法载入。");
      setDetailStatus("error");
    });
    return () => controller.abort();
  }, [view, mock]);

  const activeTopic = view.kind === "topic" ? view.topic : null;
  const availableSourceTypes = useMemo(
    () => [...new Set(sources.map((source) => source.source_type).filter(Boolean))].sort(),
    [sources],
  );
  const detailBack = useCallback(() => {
    if (view.kind !== "article") return;
    transitionTo(view.from);
  }, [transitionTo, view]);

  const openArticle = useCallback((article: ArticleCard, from: PageView) => {
    const next: ActiveView = { kind: "article", id: article.id, from };
    transitionTo(next);
  }, [transitionTo]);

  const setTopic = (topic: Topic) => {
    setFilters({ ...INITIAL_FILTERS, topic: topic.slug });
    setDraftQuery("");
    setPageCursors([null]);
    setPageIndex(0);
    navigate({ kind: "topic", topic });
  };

  const applyFilters = (next: Filters) => {
    setFilters(next);
    setPageCursors([null]);
    setPageIndex(0);
  };

  const submitSearch = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    applyFilters({ ...filters, q: draftQuery });
  };

  const goNextPage = () => {
    if (!nextCursor) return;
    setPageCursors((current) => [...current.slice(0, pageIndex + 1), nextCursor]);
    setPageIndex((current) => current + 1);
  };

  const goPreviousPage = () => setPageIndex((current) => Math.max(0, current - 1));

  const clearHistory = () => {
    setHistory([]);
    setHistoryCleared(true);
  };

  const renderListState = () => {
    if (listStatus === "loading") {
      return <div className={styles.statePanel} role="status"><span className={styles.stateMark} />正在载入资讯…</div>;
    }
    if (listStatus === "error") {
      return (
        <div className={`${styles.statePanel} ${styles.stateError}`} role="alert">
          <strong>资讯暂时无法载入</strong>
          <p>{listError}</p>
          <button className={styles.inlineButton} type="button" onClick={() => applyFilters({ ...filters })}>重试 <Icon name="arrow" size={15} /></button>
        </div>
      );
    }
    if (listStatus === "empty") {
      return (
        <div className={styles.statePanel}>
          <strong>没有匹配的资讯</strong>
          <button className={styles.inlineButton} type="button" onClick={() => applyFilters(INITIAL_FILTERS)}>清除筛选 <Icon name="arrow" size={15} /></button>
        </div>
      );
    }
    return null;
  };

  const renderArticleList = (rows: ArticleCard[], listFrom: PageView, startIndex = 0, kind: "article" | "featured" = "article") => (
    <div className={styles.articleList} data-home-stagger>
      {rows.map((article, index) => (
        <button
          className={`${styles.articleRow} ${kind === "featured" ? styles.featuredRow : ""}`}
          data-home-stagger
          type="button"
          key={article.id}
          onClick={() => openArticle(article, listFrom)}
        >
          <span className={styles.articleIndex}>{kind === "featured" ? `TOP ${startIndex + index + 1}` : String((pageIndex * (mock ? MOCK_PAGE_SIZE : PAGE_SIZE)) + index + 1).padStart(2, "0")}</span>
          <span className={styles.articleRowBody}>
            <span className={styles.articleRowMeta}><time>{formatDateTime(articleDate(article))}</time><span className={styles.metaDot} />{article.source.name}<span className={styles.metaDot} />{regionLabel(article.region)}</span>
            <strong>{article.title || article.source_title}</strong>
            {kind === "featured" && article.summary ? <span className={styles.articleRowSummary}>{article.summary}</span> : null}
          </span>
          {imagePreview(article) ? <Image className={styles.articleThumbnail} src={imagePreview(article)!} alt={article.media_preview?.alt_text || ""} width={88} height={60} unoptimized loading="lazy" /> : null}
          <span className={styles.articleRowArrow}><Icon name="arrow" size={16} /></span>
        </button>
      ))}
    </div>
  );

  const renderFeed = (feedView: PageView, includeFeatured: boolean) => (
    <>
      {includeFeatured ? <section className={styles.featuredSection} aria-label="精选资讯" data-home-stagger>
        {featuredStatus === "ready" ? renderArticleList(featured.slice(0, 6), feedView, 0, "featured") : (
          <div className={`${styles.statePanel} ${featuredStatus === "error" ? styles.stateError : ""}`} role={featuredStatus === "error" ? "alert" : undefined}>
            <strong>{featuredStatus === "error" ? "精选资讯暂时无法载入" : featuredStatus === "empty" ? "暂无精选资讯" : "正在载入精选资讯…"}</strong>
            {featuredStatus === "error" ? <p>{featuredError}</p> : null}
          </div>
        )}
      </section> : null}
      <section className={styles.feedSection} aria-labelledby="feed-title" data-home-stagger>
        <div className={styles.feedTools}>
          <span id="feed-title" className={styles.feedLabel}>{activeTopic ? activeTopic.name_zh : feedView.kind === "search" ? "搜索结果" : "近期资讯"}</span>
          {includeFeatured || feedView.kind === "topic" ? <div className={styles.periodSwitch} aria-label="资讯时间范围">{(["24h", "7d", "30d"] as const).map((period) => <button type="button" key={period} className={filters.period === period ? styles.periodActive : ""} aria-pressed={filters.period === period} onClick={() => applyFilters({ ...filters, period })}>{period === "24h" ? "24 小时" : period === "7d" ? "7 天" : "30 天"}</button>)}</div> : null}
        </div>
        {renderListState()}
        {listStatus === "ready" ? renderArticleList(articles, feedView) : null}
        {listStatus === "ready" ? (
          <div className={styles.pagination}>
            <span>{articles.length} 条</span>
            <div><button type="button" disabled={pageIndex === 0} onClick={goPreviousPage}>上一页</button><button type="button" disabled={!nextCursor} onClick={goNextPage}>下一页 <Icon name="arrow" size={14} /></button></div>
          </div>
        ) : null}
      </section>
    </>
  );

  const renderSearchControls = () => (
    <section className={styles.searchPanel} aria-label="资讯筛选" data-home-stagger>
      <form className={styles.searchForm} onSubmit={submitSearch}>
        <Icon name="search" size={19} />
        <input value={draftQuery} onChange={(event) => setDraftQuery(event.target.value)} placeholder="输入关键词，例如：警务大模型" aria-label="搜索关键词" />
        <button type="submit">搜索资讯 <Icon name="arrow" size={15} /></button>
      </form>
      <div className={styles.filterGrid}>
        <label><span>时间范围</span><select value={filters.period} onChange={(event) => applyFilters({ ...filters, period: event.target.value as ArticlePeriod })}><option value="24h">近 24 小时</option><option value="7d">近 7 天</option><option value="30d">近 30 天</option></select></label>
        <label><span>资讯地区</span><select value={filters.region} onChange={(event) => applyFilters({ ...filters, region: event.target.value as ArticleRegion | "" })}><option value="">全部地区</option><option value="domestic">国内</option><option value="foreign">国外</option></select></label>
        <label><span>主题分类</span><select value={filters.topic} onChange={(event) => applyFilters({ ...filters, topic: event.target.value })}><option value="">全部主题</option>{topicMenuTopics.map((topic) => <option key={topic.id} value={topic.slug}>{topic.name_zh}</option>)}</select></label>
        <label><span>具体来源</span><select value={filters.source} onChange={(event) => applyFilters({ ...filters, source: event.target.value })}><option value="">{sources.length ? "全部来源" : sourceStatus === "loading" ? "来源目录载入中" : sourceStatus === "error" ? "来源目录暂不可用" : "暂无来源目录"}</option>{sources.map((source) => <option key={source.id} value={source.id}>{source.name}</option>)}</select></label>
        <label><span>来源类型</span><select value={filters.sourceType} onChange={(event) => applyFilters({ ...filters, sourceType: event.target.value })}><option value="">全部来源</option>{availableSourceTypes.map((type) => <option key={type} value={type}>{sourceTypeLabel(type)}</option>)}</select></label>
        <label><span>排列方式</span><select value={filters.sort} onChange={(event) => applyFilters({ ...filters, sort: event.target.value as ArticleSort })}><option value="recent">最新发布</option><option value="importance">关注度优先</option></select></label>
      </div>
      <div className={styles.searchFootnote}><button type="button" onClick={() => { setDraftQuery(""); applyFilters(INITIAL_FILTERS); }}>重置筛选</button></div>
    </section>
  );

  const renderArticleDetail = () => {
    if (detailStatus === "loading") return <div className={styles.statePanel} role="status"><span className={styles.stateMark} />正在载入文章与来源材料…</div>;
    if (detailStatus === "error" || !detail) return <div className={`${styles.statePanel} ${styles.stateError}`} role="alert"><strong>文章详情暂时不可用</strong><p>{detailError}</p><button className={styles.inlineButton} type="button" onClick={detailBack}>返回资讯列表 <Icon name="arrow" size={15} /></button></div>;
    const body = detail.zh_body || detail.source_body;
    return (
       <article className={styles.detailArticle} data-home-stagger>
        <button className={styles.detailBack} type="button" onClick={detailBack}><Icon name="back" size={16} />返回列表</button>
        <div className={styles.detailTopline}><span>{regionLabel(detail.region)} / {detail.source.name}</span><time>{formatDateTime(articleDate(detail))}</time><span>重要性 {Math.round(detail.importance_score)}%</span></div>
        <h2>{detail.title || detail.source_title}</h2>
        {detail.summary ? <p className={styles.detailSummary}>{detail.summary}</p> : null}
        <div className={styles.detailLabels}>{(detail.topics ?? []).map((slug) => <span key={slug}>{topicLabel(slug, topics)}</span>)}<span>{detail.language.toLocaleUpperCase()}</span></div>
        {detail.media.map((media, index) => media.kind === "image" ? <figure className={styles.detailMedia} key={`${media.url}-${index}`} style={{ backgroundImage: `url("${media.thumbnail_url || media.url}")` }}><figcaption>{media.caption || media.alt_text || "来源图片"}</figcaption></figure> : null)}
        <section className={styles.detailSection}><span>正文</span>{body ? <div className={styles.detailBody}>{body.split(/\n{2,}/).map((paragraph, index) => <p key={index}>{paragraph}</p>)}</div> : <div className={styles.missingContent}>尚未获取可阅读的正文。</div>}</section>
        {detail.source_title ? <section className={styles.originalTitle}><span>原始标题</span><p>{detail.source_title}</p></section> : null}
        {detail.source_body && detail.zh_body ? <details className={styles.originalDetails}><summary>查看可获取的原文内容</summary><p>{detail.source_body}</p></details> : null}
        <section className={styles.sourceCard}><div><span>来源</span><strong>{detail.source.name}</strong><span>{detail.source_title || detail.url}</span></div><a href={detail.url} target="_blank" rel="noreferrer">原文链接 <Icon name="external" size={16} /></a></section>
      </article>
    );
  };

  return (
    <div ref={dashboardRef} className={styles.dashboard} style={dashboardStyle}>
      <button ref={scrimRef} className={`${styles.mobileScrim} ${menuOpen ? styles.mobileScrimOpen : ""}`} type="button" aria-label="关闭菜单" onClick={() => setMenuOpen(false)} tabIndex={menuOpen ? 0 : -1} />
      <aside ref={sidebarRef} className={`${styles.sidebar} ${menuOpen ? styles.sidebarOpen : ""}`} aria-label="主菜单" data-home-sidebar>
        <button className={`${styles.menuItem} ${view.kind === "search" ? styles.menuItemActive : ""}`} type="button" onClick={() => { setDraftQuery(filters.q); navigate({ kind: "search" }); }}><Icon name="search" size={18} /><span>搜索</span></button>
        <BranchedTopicMenu topics={topics} activeSlug={activeTopic?.slug ?? ""} status={topicStatus} onSelect={setTopic} />
        <button className={`${styles.menuItem} ${view.kind === "history" ? styles.menuItemActive : ""}`} type="button" onClick={() => navigate({ kind: "history" })}><Icon name="clock" size={18} /><span>浏览历史</span>{history.length ? <span className={styles.historyCount}>{history.length}</span> : null}</button>
        <div className={styles.menuSpacer} aria-hidden="true" />
        <button className={`${styles.menuItem} ${styles.accountNav} ${view.kind === "account" ? styles.menuItemActive : ""}`} type="button" onClick={() => navigate({ kind: "account" })}><Icon name="user" size={18} /><span>账号</span></button>
      </aside>
      <div className={styles.contentRegion}>
        <div ref={mobileBarRef} className={styles.mobileBar} data-home-mobile-bar>
          <button type="button" onClick={() => setMenuOpen(true)} aria-label="打开菜单" aria-expanded={menuOpen}><Icon name="menu" size={20} /><span>菜单</span></button>
          {view.kind === "article" ? <button className={styles.mobileBack} type="button" onClick={detailBack} aria-label="返回列表"><Icon name="back" size={19} /><span>返回</span></button> : null}
        </div>
        <main ref={readingAreaRef} className={styles.readingArea}>
          <div ref={viewStageRef} className={styles.viewStage} data-home-view>
            {view.kind === "home" ? renderFeed(view, true) : null}
            {view.kind === "topic" ? renderFeed(view, false) : null}
            {view.kind === "search" ? <>{renderSearchControls()}{renderFeed(view, false)}</> : null}
            {view.kind === "article" ? renderArticleDetail() : null}
            {view.kind === "history" ? <section className={styles.historySection} data-home-stagger>
            <div className={styles.viewTools}><span className={styles.feedLabel}>浏览历史</span>{history.length ? <button className={styles.clearButton} type="button" onClick={clearHistory}><Icon name="clear" size={15} />清空</button> : null}</div>
            {!historyReady ? <div className={styles.statePanel}>正在读取…</div> : history.length ? <div className={styles.historyList}>{history.map((entry, index) => <button type="button" className={styles.historyRow} key={`${entry.article.id}-${entry.viewedAt}`} onClick={() => openArticle(entry.article, view)}><span className={styles.historyNo}>{String(index + 1).padStart(2, "0")}</span><span className={styles.historyCopy}><small>{formatDateTime(articleDate(entry.article))} · {entry.article.source.name} · {timeAgo(entry.viewedAt)}</small><strong>{entry.article.title || entry.article.source_title}</strong></span><Icon name="arrow" size={16} /></button>)}</div> : <div className={styles.emptyHistory}><strong>{historyCleared ? "浏览历史已清空" : "暂无浏览记录"}</strong><button className={styles.inlineButton} type="button" onClick={() => navigate({ kind: "home" })}>返回资讯列表 <Icon name="arrow" size={15} /></button></div>}
            </section> : null}
            {view.kind === "account" ? <section className={styles.accountPage} data-home-stagger>
            <div className={styles.viewTools}><span className={styles.feedLabel}>账号</span></div>
            <div className={styles.accountRows}><div><span>账号状态</span><strong>访客</strong></div><div><span>浏览历史</span><strong>{history.length} 条</strong></div><div><span>可用主题</span><strong>{topics.length} 个</strong></div><div><span>登录</span><strong>暂未开放</strong></div></div>
            </section> : null}
          </div>
        </main>
      </div>
    </div>
  );
}
