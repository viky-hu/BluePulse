"use client";

// Adapted from AIHOT components/shell/{TabBar,PhoneBar,nav,screens}.ts(x), MIT.
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import { useLayoutEffect, useRef, useSyncExternalStore, type ReactNode, type Ref } from "react";
import { createPortal } from "react-dom";
import { useMainShell } from "../MainShell";
import { MenuIcon } from "../menu/MenuIcon";
import { PulseWordmark } from "../menu/PulseWordmark";
import { IntentLink } from "../../feed/IntentLink";
import { useSiteState } from "../../../_lib/use-site-state";
import { MOBILE_TABS, canNoteMobileScreen, mobileScreen, mobileTabAction, mobileTabState, savedMobileTab, type MobileTabKey } from "./screen";
import styles from "./mobile-chrome.module.css";

function Brand({ href }: { href: string }) {
  return <IntentLink href={href} className={styles.brand} aria-label="Pulse 首页"><PulseWordmark /></IntentLink>;
}

/** The stable shell owns this host, so route filters never scroll the phone bar out of view. */
export function MobileHeader({ ref, pathname, hrefFor }: {
  ref: Ref<HTMLElement>; pathname: string; hrefFor: (href: string) => string;
}) {
  return <header ref={ref} className={styles.header} data-mobile-header>
    <div className={`${styles.row} ${styles.defaultRow}`}>
      <div className={styles.leading}><Brand href={hrefFor("/")} /></div>
      <div className={styles.center}><span className={styles.title}>{mobileScreen(pathname).title}</span></div>
      <div className={styles.actions} />
    </div>
  </header>;
}

/** A page supplies only its row; Pulse retains one shared header and its safe-area spacing. */
export function PhoneBar({ leading, center, title, actions }: {
  leading?: ReactNode; center?: ReactNode; title?: ReactNode; actions?: ReactNode;
}) {
  const shell = useMainShell();
  if (!shell.phoneBarHost) return null;
  // Portalled controls live outside the stage's inert subtree, so follow its navigation guard.
  return createPortal(<div className={styles.row} data-phone-bar-content inert={!shell.active}>
    <div className={styles.leading}>{leading ?? <Brand href={shell.href("/")} />}</div>
    <div className={styles.center}>{center ?? <span className={styles.title}>{title}</span>}</div>
    <div className={styles.actions}>{actions}</div>
  </div>, shell.phoneBarHost);
}

const tabEvent = "pulse-mobile-tab";
function subscribeTab(notify: () => void) {
  window.addEventListener("popstate", notify);
  window.addEventListener(tabEvent, notify);
  return () => { window.removeEventListener("popstate", notify); window.removeEventListener(tabEvent, notify); };
}
const serverTab = () => null;
const browserTab = () => savedMobileTab(window.history.state) ?? null;

export function MobileTabBar({ changelogVersion }: { changelogVersion: string | null }) {
  const shell = useMainShell();
  const screen = mobileScreen(shell.pathname);
  const { state } = useSiteState(shell.mock);
  const unread = !!changelogVersion && state.ready && (!state.seen || state.seen < changelogVersion);
  const restored = useSyncExternalStore(subscribeTab, browserTab, serverTab);
  const last = useRef<MobileTabKey | undefined>(undefined);
  const active = screen.tab ?? restored ?? screen.fallback;
  useLayoutEffect(() => {
    // POP changes the browser entry before Next commits its hook values. Never stamp the old route
    // over that entry. Each shared search page keeps its own source tab across POP and reload.
    if (!canNoteMobileScreen(shell.routeKey, `${location.pathname}${location.search}`)) return;
    const saved = savedMobileTab(history.state);
    const tab = screen.tab ?? saved ?? last.current ?? screen.fallback;
    last.current = tab;
    if (saved !== tab) {
      history.replaceState(mobileTabState(history.state, tab), "", location.href);
      window.dispatchEvent(new Event(tabEvent));
    }
  }, [shell.routeKey, screen.tab, screen.fallback]);
  if (screen.toolbar) return null;
  return <nav className={styles.tabs} data-mobile-tabs aria-label="底部导航" inert={shell.entry !== "stable"}>
    <div className={styles.tabGrid}>{MOBILE_TABS.map(tab => {
      const on = tab.key === active;
      return <IntentLink key={tab.key} href={shell.href(tab.href)} className={styles.tab} aria-current={on ? "page" : undefined}
        onClick={event => {
          if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
          event.preventDefault();
          if (shell.entry !== "stable") return;
          const scroller = document.querySelector<HTMLElement>("[data-p0-scroller]");
          const action = mobileTabAction(tab.key, active, shell.pathname, scroller?.scrollTop ?? 0);
          if (action === "scroll") {
            const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
            scroller?.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
          } else if (action === "refresh") {
            if (shell.active) shell.navigate(shell.routeKey);
          } else shell.navigate(tab.href, { origin: "main-menu" });
        }}>
        {tab.icon === "more" ? <svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="3.8" /><path d="M4.8 20.2c.9-3.5 3.8-5.7 7.2-5.7s6.3 2.2 7.2 5.7" /></svg> : <MenuIcon name={tab.icon} />}
        <span>{tab.label}</span>
        {tab.key === "more" && unread && <span className={styles.dot} aria-label="有新的更新" />}
      </IntentLink>;
    })}</div>
  </nav>;
}
