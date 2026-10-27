"use client";

import { useEffect, useSyncExternalStore, type Ref } from "react";
import Link from "next/link";
import { isMenuItemActive, MENU_SECTIONS } from "../navigation-config";
import { MenuIcon } from "./MenuIcon";
import { PulseWordmark } from "./PulseWordmark";
import styles from "./sidebar.module.css";

const mobileQuery = "(max-width: 768px)";
function subscribeMobile(notify: () => void) {
  const query = window.matchMedia(mobileQuery);
  query.addEventListener("change", notify);
  return () => query.removeEventListener("change", notify);
}
const getMobile = () => window.matchMedia(mobileQuery).matches;
const getServerMobile = () => false;

/** Adapted from AIHOT Sidebar/SideLink; the parent retains ownership of entry animation. */
export function PulseSidebar({ ref, className, pathname, hrefFor, open, inactive, onClose }: {
  ref: Ref<HTMLElement>; className: string; pathname: string; hrefFor: (href: string) => string;
  open: boolean; inactive: boolean; onClose: () => void;
}) {
  const mobile = useSyncExternalStore(subscribeMobile, getMobile, getServerMobile);
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && window.matchMedia(mobileQuery).matches) { event.preventDefault(); onClose(); }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);
  const searchActive = pathname === "/search";
  return <aside ref={ref} id="pulse-main-menu" className={`${styles.sidebar} ${className}`} data-open={open} aria-label="主菜单" data-home-sidebar inert={inactive || (mobile && !open)}>
    <header className={styles.header}>
      <Link href={hrefFor("/")} className={styles.brand} aria-label="Pulse 首页"><PulseWordmark /></Link>
      <Link href={hrefFor("/search")} className={`${styles.item} ${styles.search}`} aria-current={searchActive ? "page" : undefined}>
        <span className={styles.icon}><MenuIcon name="search" /></span><span className={styles.label}>搜索</span>
      </Link>
    </header>
    <nav className={styles.navigation} aria-label="主导航">
      {MENU_SECTIONS.map(section => <section key={section.title} className={styles.section} aria-label={section.title}>
        <h2 className={styles.sectionTitle}>{section.title}</h2>
        <ul className={styles.items}>{section.items.map(item => <li key={item.href}>
          <Link href={hrefFor(item.href)} className={styles.item} aria-current={isMenuItemActive(item.href, pathname) ? "page" : undefined}>
            <span className={styles.icon}><MenuIcon name={item.icon} /></span><span className={styles.label}>{item.label}</span>
          </Link>
        </li>)}</ul>
      </section>)}
    </nav>
  </aside>;
}
