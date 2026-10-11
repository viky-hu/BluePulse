"use client";

import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { gsap } from "gsap";
import { useGSAP } from "@gsap/react";
import { fetchTaxonomy, type Topic } from "../../_lib/home-data";
import { MOCK_TAXONOMY } from "../../_lib/home-mock";
import { useBrowserState } from "../../_lib/use-browser-state";
import { readSessionSnapshot, saveSessionSnapshot } from "../../_lib/session-restore";
import { BranchedTopicMenu } from "./BranchedTopicMenu";
import { canonicalHref, entryMode, parseHomeRoute } from "./home-routes";
import { finishEnter, finishExit, requestNavigation, type NavigationState } from "./view-transition";
import { MainScene } from "./MainScene";
import menuStyles from "./home.module.css";
import styles from "./main-shell.module.css";

gsap.registerPlugin(useGSAP);
type Entry = "pending" | "intro" | "revealing" | "stable";
type ShellContext = {
  mock: boolean; routeKey: string; pathname: string; restore: boolean; entry: Entry;
  introHost: HTMLDivElement | null; introFinished: () => void;
  ready: (key: string, value: boolean) => void; navigate: (href: string) => void;
  href: (href: string) => string; topics: Topic[]; refreshRevision: number;
};
const Context = createContext<ShellContext | null>(null);
export function useMainShell() { const context = useContext(Context); if (!context) throw Error("Missing Pulse shared layout"); return context; }
export function RouteReady({ ready = true }: { ready?: boolean }) {
  const { ready: report, routeKey } = useMainShell();
  useEffect(() => { report(routeKey, ready); return () => report(routeKey, false); }, [report, routeKey, ready]);
  return null;
}

type Position = { top: number; anchor: string | null; offset: number };
function position(scroller: HTMLElement): Position {
  const top = scroller.getBoundingClientRect().top;
  const item = [...scroller.querySelectorAll<HTMLElement>("[data-card-key]")].find(row => row.getBoundingClientRect().bottom > top);
  return { top: scroller.scrollTop, anchor: item?.dataset.cardKey ?? null, offset: item ? item.getBoundingClientRect().top - top : 0 };
}

export function MainShell({ children }: { children: ReactNode }) {
  const pathname = usePathname(), search = useSearchParams(), router = useRouter();
  const mock = search.get("mock") === "1";
  const key = canonicalHref(`${pathname}?${search}`);
  const { state: browser, store } = useBrowserState(mock);
  const root = useRef<HTMLDivElement>(null), stage = useRef<HTMLDivElement>(null), scroller = useRef<HTMLElement>(null), menu = useRef<HTMLElement>(null);
  const motion = useRef<gsap.core.Animation | null>(null), motionKey = useRef("");
  const [entry, setEntry] = useState<Entry>("pending");
  const [introHost, setIntroHost] = useState<HTMLDivElement | null>(null);
  const [navigation, setNavigation] = useState<NavigationState<string>>({ phase: "idle", currentKey: key, pending: null });
  const navigationRef = useRef(navigation);
  const keyRef = useRef(key);
  const [readyKeys, setReadyKeys] = useState<Record<string, boolean>>({});
  const [activation, setActivation] = useState({ key, restore: false });
  const [pendingRoute, setPendingRoute] = useState<string | null>(null);
  // An owned push carries its intent before URL commit. Any other key change is history traversal.
  const restore = pendingRoute === null && (activation.key !== key || activation.restore);
  const [menuOpen, setMenuOpen] = useState(false);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [refreshRevision, setRefreshRevision] = useState(0);
  const [topicStatus, setTopicStatus] = useState<"loading" | "ready" | "error">("loading");
  const visibleTopics = mock ? MOCK_TAXONOMY.items : topics;
  const visibleTopicStatus = mock ? "ready" : topicStatus;
  const initial = useRef(true), restored = useRef<string | null>(null), revealing = useRef(false);
  const { contextSafe } = useGSAP({ scope: root });
  const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  useLayoutEffect(() => { navigationRef.current = navigation; keyRef.current = key; }, [navigation, key]);
  const ready = useCallback((routeKey: string, value: boolean) => {
    if (routeKey !== keyRef.current) return;
    setReadyKeys(previous => previous[routeKey] === value ? previous : { [routeKey]: value });
  }, []);
  const href = useCallback((target: string) => {
    const url = new URL(target, "https://pulse.local");
    if (mock) url.searchParams.set("mock", "1");
    return `${url.pathname}${url.search}${url.hash}`;
  }, [mock]);
  const savePosition = useCallback(() => {
    // DOM replacement clamps scrollTop before content/anchors are ready. Never persist that transient value.
    if (scroller.current && restored.current === keyRef.current && navigationRef.current.phase === "idle") {
      saveSessionSnapshot(`position:${keyRef.current}`, position(scroller.current), mock);
    }
  }, [mock]);

  // The head bootstrap has already chosen the pre-paint state. This effect only hydrates it.
  useLayoutEffect(() => {
    if (!initial.current) return;
    initial.current = false; store.hydrate();
    const mode = entryMode(pathname, store.getSnapshot().entered);
    document.documentElement.dataset.pulseEntry = mode;
    setEntry(mode === "intro" ? "intro" : "stable");
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial history activation before paint
    if (performance.getEntriesByType("navigation").some(item => (item as PerformanceNavigationTiming).type === "back_forward")) setActivation({ key, restore: true });
  }, [key, pathname, store]);

  useEffect(() => {
    const controller = new AbortController();
    if (mock) return;
    fetchTaxonomy(AbortSignal.any([controller.signal, AbortSignal.timeout(12000)])).then(data => { setTopics(data.items); setTopicStatus("ready"); }).catch(() => { if (!controller.signal.aborted) setTopicStatus("error"); });
    return () => controller.abort();
  }, [mock]);

  const navigate = useCallback((target: string) => {
    const destination = href(target), targetKey = canonicalHref(destination);
    if (targetKey === navigationRef.current.currentKey && navigationRef.current.phase === "idle") {
      setRefreshRevision(value => value + 1); setActivation({ key: targetKey, restore: false }); router.refresh(); return;
    }
    savePosition(); setMenuOpen(false); restored.current = null;
    const step = requestNavigation(navigationRef.current, { key: targetKey, view: destination }, reduced());
    navigationRef.current = step.state; setNavigation(step.state);
    if (step.commit) {
      setActivation({ key: step.commit.key, restore: false }); setPendingRoute(step.commit.key);
      setReadyKeys({}); router.push(step.commit.view, { scroll: false });
    }
  }, [href, router, savePosition]);

  useEffect(() => {
    const onPop = () => {
      const target = canonicalHref(`${location.pathname}${location.search}`);
      // Next can commit a cached traversal before this callback. Only save the still-outgoing DOM.
      if (keyRef.current !== target) { savePosition(); restored.current = null; }
      motion.current?.kill(); motionKey.current = "";
      navigationRef.current = { phase: "idle", currentKey: target, pending: null };
      setNavigation(navigationRef.current); setPendingRoute(null); setActivation({ key: target, restore: true }); setMenuOpen(false);
      contextSafe(() => { if (stage.current) gsap.set(stage.current, { autoAlpha: 1, y: 0 }); })();
    };
    // Restoration is already classified by URL activation; this listener only cancels ongoing motion.
    window.addEventListener("popstate", onPop, true); window.addEventListener("pagehide", savePosition);
    return () => { window.removeEventListener("popstate", onPop, true); window.removeEventListener("pagehide", savePosition); };
  }, [savePosition, contextSafe]);

  useLayoutEffect(() => {
    if (pendingRoute === key) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- acknowledge the committed Next URL before paint
      setPendingRoute(null);
    } else if (pendingRoute === null && activation.key !== key) {
      restored.current = null;
      // Classify an externally committed history route.
      setActivation({ key, restore: true });
    }
  }, [key, pendingRoute, activation.key]);

  useLayoutEffect(() => {
    if (pendingRoute === null && navigation.phase === "idle" && key !== navigation.currentKey) {
      motion.current?.kill(); motionKey.current = "";
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync external Next navigation
      setNavigation({ phase: "idle", currentKey: key, pending: null });
      contextSafe(() => { if (stage.current) gsap.set(stage.current, { autoAlpha: 1, y: 0 }); })();
    }
  }, [key, pendingRoute, navigation.phase, navigation.currentKey, contextSafe]);

  useLayoutEffect(() => {
    if (entry !== "stable" || !stage.current) return;
    const token = `${navigation.phase}:${navigation.currentKey}`;
    if (motionKey.current === token) return;
    if (navigation.phase === "exiting") {
      motionKey.current = token; motion.current?.kill();
      contextSafe(() => {
        motion.current = gsap.to(stage.current, { autoAlpha: 0, y: -5, duration: .22, ease: "power2.in", onComplete: () => {
          const step = finishExit(navigationRef.current); navigationRef.current = step.state; setNavigation(step.state);
          if (step.commit) {
            setActivation({ key: step.commit.key, restore: false }); setPendingRoute(step.commit.key);
            setReadyKeys({}); router.push(step.commit.view, { scroll: false });
          }
        } });
      })();
    } else if (navigation.phase === "entering" && key === navigation.currentKey && readyKeys[key]) {
      motionKey.current = token;
      contextSafe(() => {
        motion.current = gsap.fromTo(stage.current, { autoAlpha: 0, y: 7 }, { autoAlpha: 1, y: 0, duration: reduced() ? 0 : .4, ease: "power2.out", onComplete: () => {
          const step = finishEnter(navigationRef.current); navigationRef.current = step.state; setNavigation(step.state);
        } });
      })();
    } else if (navigation.phase === "idle") motionKey.current = token;
  }, [entry, navigation.phase, navigation.currentKey, key, readyKeys, contextSafe, router]);

  useLayoutEffect(() => {
    if (!readyKeys[key] || !scroller.current || restored.current === key || (pendingRoute !== null && pendingRoute !== key)) return;
    const area = scroller.current;
    const saved = restore ? readSessionSnapshot<Position>(`position:${key}`, mock) : null;
    area.scrollTop = saved && Number.isFinite(saved.top) ? saved.top : 0;
    if (saved?.anchor && Number.isFinite(saved.offset)) {
      const anchor = [...area.querySelectorAll<HTMLElement>("[data-card-key]")].find(item => item.dataset.cardKey === saved.anchor);
      if (anchor) area.scrollTop += anchor.getBoundingClientRect().top - area.getBoundingClientRect().top - saved.offset;
    }
    restored.current = key;
  }, [key, readyKeys, restore, pendingRoute, mock]);

  useEffect(() => {
    if (!readyKeys[key]) return;
    if (entry === "stable") store.markEntered();
    if (entry !== "revealing" || revealing.current) return;
    revealing.current = true;
    contextSafe(() => {
      motion.current = gsap.timeline({ onComplete: () => {
        store.markEntered(); setEntry("stable"); motionKey.current = "";
        gsap.set(menu.current, { clearProps: "opacity,visibility,transform" });
      } })
        .fromTo(menu.current, { autoAlpha: 0, x: -12 }, { autoAlpha: 1, x: 0, duration: reduced() ? 0 : .5 })
        .fromTo(stage.current, { autoAlpha: 0, y: 12 }, { autoAlpha: 1, y: 0, duration: reduced() ? 0 : .5 }, reduced() ? 0 : .15);
    })();
  }, [entry, key, readyKeys, store, contextSafe]);

  useEffect(() => () => { motion.current?.kill(); }, []);
  const introFinished = useCallback(() => { document.documentElement.dataset.pulseEntry = "stable"; setEntry("revealing"); }, []);
  const context = useMemo<ShellContext>(() => ({ mock, routeKey: key, pathname, restore, entry, introHost, introFinished, ready, navigate, href, topics: visibleTopics, refreshRevision }), [mock, key, pathname, restore, entry, introHost, introFinished, ready, navigate, href, visibleTopics, refreshRevision]);
  const route = parseHomeRoute(pathname, search);
  const capture = (event: MouseEvent<HTMLDivElement>) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const anchor = (event.target as Element).closest<HTMLAnchorElement>("a[href]");
    if (!anchor || anchor.hasAttribute("download") || (anchor.target && anchor.target !== "_self")) return;
    const url = new URL(anchor.href);
    if (url.origin !== location.origin || url.hash || !parseHomeRoute(url.pathname, url.searchParams).valid) return;
    event.preventDefault(); navigate(`${url.pathname}${url.search}`);
  };
  return <Context.Provider value={context}>
    <div ref={root} className={styles.shell} data-entry={entry} onClickCapture={capture}>
      <MainScene />
      <div className={menuStyles.dashboard}>
        <button className={styles.mobileToggle} onClick={() => setMenuOpen(!menuOpen)} aria-label={menuOpen ? "关闭菜单" : "打开菜单"} aria-expanded={menuOpen}>☰ 菜单</button>
        <button className={styles.scrim} data-open={menuOpen} onClick={() => setMenuOpen(false)} aria-label="关闭菜单" tabIndex={menuOpen ? 0 : -1} />
        <aside ref={menu} className={`${menuStyles.sidebar} ${styles.menu}`} data-open={menuOpen} aria-label="主菜单" data-home-sidebar inert={entry === "intro" || entry === "revealing"}>
          <Link href={href("/")} className={styles.brand}>Blue Pulse · 精选</Link>
          <Link href={href("/search")} className={`${menuStyles.menuItem} ${route.kind === "search" ? menuStyles.menuItemActive : ""}`} aria-current={route.kind === "search" ? "page" : undefined}><span aria-hidden>⌕</span><span>搜索</span></Link>
          <BranchedTopicMenu topics={visibleTopics} activeSlug={route.filters.topic} status={visibleTopicStatus} hrefForTopic={slug => href(`/topics/${slug}`)} />
          <Link className={`${menuStyles.menuItem} ${route.kind === "history" ? menuStyles.menuItemActive : ""}`} href={href("/history")}><span aria-hidden>◷</span><span>浏览历史</span>{browser.history.length ? <span className={menuStyles.historyCount}>{browser.history.length}</span> : null}</Link>
          <Link className={`${menuStyles.menuItem} ${route.kind === "starred" ? menuStyles.menuItemActive : ""}`} href={href("/starred")}><span aria-hidden>☆</span><span>本机收藏</span>{browser.starred.length ? <span className={menuStyles.historyCount}>{browser.starred.length}</span> : null}</Link>
        </aside>
      </div>
      <div className={styles.frame} data-p0-content>
        {navigation.phase === "entering" && !readyKeys[key] ? <div className={styles.navigationStatus} role="status">正在载入内容…</div> : null}
        <main ref={scroller} className={styles.scroller} data-p0-scroller onScroll={savePosition}>
          <div ref={stage} className={styles.stage} data-phase={navigation.phase} data-home-view={pathname} inert={entry === "intro" || entry === "revealing" || navigation.phase !== "idle"}>{children}</div>
        </main>
      </div>
      {browser.notice ? <p role="status" className={styles.notice}>{browser.notice}</p> : null}
      <div className={styles.entryCover} />
      <div ref={setIntroHost} className={styles.introHost} />
    </div>
  </Context.Provider>;
}
