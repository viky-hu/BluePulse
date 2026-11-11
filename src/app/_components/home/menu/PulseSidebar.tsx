"use client";

import { useState, type FocusEvent, type MouseEvent, type Ref } from "react";
import Link from "next/link";
import { isMenuItemActive, MENU_SECTIONS } from "../navigation-config";
import { MenuIcon } from "./MenuIcon";
import { PulseWordmark } from "./PulseWordmark";
import { useSiteState } from "../../../_lib/use-site-state";
import styles from "./sidebar.module.css";

function IntentLink({ href, onPrefetch, onMouseEnter, onFocus, ...props }: React.ComponentProps<typeof Link> & { onPrefetch: (href: string) => void }) {
  const [intent, setIntent] = useState(false);
  const prefetchOnIntent = (event: MouseEvent<HTMLAnchorElement> | FocusEvent<HTMLAnchorElement>) => {
    setIntent(true);
    onPrefetch(event.currentTarget.href);
  };
  return <Link {...props} href={href} prefetch={intent} onMouseEnter={event => { onMouseEnter?.(event); prefetchOnIntent(event); }} onFocus={event => { onFocus?.(event); prefetchOnIntent(event); }} />;
}

/** Adapted from AIHOT Sidebar/SideLink; the parent retains ownership of entry animation. */
export function PulseSidebar({ ref, className, pathname, hrefFor, onPrefetch, inactive, changelogVersion, mock }: {
  ref: Ref<HTMLElement>; className: string; pathname: string; hrefFor: (href: string) => string;
  onPrefetch: (href: string) => void;
  inactive: boolean;
  changelogVersion: string; mock: boolean;
}) {
  const { state } = useSiteState(mock);
  const unread = state.ready && (!state.seen || state.seen < changelogVersion);
  const searchActive = pathname === "/search";
  return <aside ref={ref} id="pulse-main-menu" className={`${styles.sidebar} ${className}`} aria-label="主菜单" data-home-sidebar inert={inactive}>
    <header className={styles.header}>
      <IntentLink href={hrefFor("/")} onPrefetch={onPrefetch} className={styles.brand} aria-label="Pulse 首页"><PulseWordmark /></IntentLink>
      <IntentLink href={hrefFor("/search")} onPrefetch={onPrefetch} className={`${styles.item} ${styles.search}`} aria-current={searchActive ? "page" : undefined}>
        <span className={styles.icon}><MenuIcon name="search" /></span><span className={styles.label}>搜索</span>
      </IntentLink>
    </header>
    <nav className={styles.navigation} aria-label="主导航">
      {MENU_SECTIONS.map(section => <section key={section.title} className={styles.section} aria-label={section.title}>
        <h2 className={styles.sectionTitle}>{section.title}</h2>
        <ul className={styles.items}>{section.items.map(item => <li key={item.href}>
          <IntentLink href={hrefFor(item.href)} onPrefetch={onPrefetch} className={styles.item} aria-current={isMenuItemActive(item.href, pathname) ? "page" : undefined}>
            <span className={styles.icon}><MenuIcon name={item.icon} /></span><span className={styles.label}>{item.label}</span>{item.href === "/changelog" && unread && <span className={styles.unread} aria-label="有新的更新" />}
          </IntentLink>
        </li>)}</ul>
      </section>)}
    </nav>
  </aside>;
}
