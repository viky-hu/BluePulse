// AIHOT OutlineSheet scrolling, adapted to the shared p0 scroll area (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import { isCompactReader } from "./format";
export function compactReaderContainer() {
    const content = document.querySelector<HTMLElement>("[data-p0-scroller] > [data-home-view]");
    return !!content && isCompactReader(content.clientWidth, Number.parseFloat(getComputedStyle(document.documentElement).fontSize) || 16);
}
export function readerScroller(element: HTMLElement | null) {
    return element?.closest<HTMLElement>("[data-p0-scroller]") ?? null;
}
export function scrollToSection(id: string) {
    const target = document.getElementById(id);
    const area = readerScroller(target);
    if (!target || !area)
        return;
    const bar = area.querySelector<HTMLElement>("[data-reader-bar]");
    const offset = bar && getComputedStyle(bar).display !== "none" ? bar.offsetHeight + 20 : 24;
    area.scrollTo({
        top: area.scrollTop + target.getBoundingClientRect().top - area.getBoundingClientRect().top - offset, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"
    });
    history.replaceState(history.state, "", `${location.pathname}${location.search}#${encodeURIComponent(id)}`);
}
