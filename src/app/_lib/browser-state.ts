// Adapted from AIHOT apps/web/app/lib/local-state.ts (MIT); see third-party license notice.
// Stable snapshots, guarded storage, subscription cleanup and fresh reads before edits follow AIHOT.
import type { ArticleCard } from "./home-data";

export interface LocalStarredItem { id: string; title: string; summary: string | null; sourceName: string; publishedAt: string | null; score: number | null; savedAt: string }
export interface HistoryEntry { article: ArticleCard; viewedAt: string }
export interface BrowserSnapshot { ready: boolean; entered: boolean; starred: LocalStarredItem[]; history: HistoryEntry[]; notice: string | null }
export interface BrowserStateStore {
  getSnapshot(): BrowserSnapshot; getServerSnapshot(): BrowserSnapshot;
  subscribe(listener: () => void): () => void; hydrate(): void; markEntered(): void;
  toggleStar(item: Omit<LocalStarredItem, "savedAt">): void; removeStar(id: string): void;
  recordRead(article: ArticleCard): void; clearHistory(): void;
}
export interface BrowserStateOptions { storage?: () => Storage | null; eventTarget?: EventTarget; now?: () => Date }
export function browserKeys(mock = false) {
  const suffix = mock ? ":mock" : "";
  return { entry: `blue-pulse-entry-complete-v1${suffix}`, starred: `blue-pulse-starred-items-v1${suffix}`, history: `blue-pulse-reading-history-v1${suffix}` };
}
const EMPTY: BrowserSnapshot = { ready: false, entered: false, starred: [], history: [], notice: null };
const MEMORY_NOTICE = "浏览器存储不可用，变更仅在本次访问有效。";
const CORRUPT_NOTICE = "已保留无法读取的浏览器数据，变更仅在本次访问有效。";
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const text = (v: unknown): v is string => typeof v === "string" && v.trim().length > 0;
const date = (v: unknown): v is string => typeof v === "string" && /^\d{4}-\d{2}-\d{2}T/.test(v) && Number.isFinite(Date.parse(v));
function validStar(v: unknown, mock: boolean): v is LocalStarredItem {
  if (!v || typeof v !== "object") return false;
  const s = v as LocalStarredItem;
  return text(s.id) && (mock || uuid.test(s.id)) && text(s.title) && typeof s.sourceName === "string" && (s.summary === null || typeof s.summary === "string") && (s.publishedAt === null || date(s.publishedAt)) && (s.score === null || (typeof s.score === "number" && Number.isFinite(s.score))) && date(s.savedAt);
}
function validHistory(v: unknown): v is HistoryEntry {
  if (!v || typeof v !== "object") return false;
  const h = v as HistoryEntry;
  return date(h.viewedAt) && !!h.article && text(h.article.id) && text(h.article.title) && typeof h.article.url === "string" && !!h.article.source && typeof h.article.source.name === "string";
}
function unique<T>(list: T[], key: (v: T) => string, limit: number): T[] {
  const seen = new Set<string>();
  return list.filter(v => { const id = key(v); if (seen.has(id)) return false; seen.add(id); return true; }).slice(0, limit);
}
export function createBrowserState(mock = false, options: BrowserStateOptions = {}): BrowserStateStore {
  const keys = browserKeys(mock);
  const now = options.now ?? (() => new Date());
  const target = options.eventTarget ?? (typeof window !== "undefined" ? window : null);
  const listeners = new Set<() => void>();
  const memoryOnly = new Set<string>();
  let snapshot = EMPTY;
  function storage() { try { return options.storage ? options.storage() : typeof window !== "undefined" ? window.localStorage : null; } catch { return null; } }
  function update(next: BrowserSnapshot) {
    if (JSON.stringify(next) === JSON.stringify(snapshot)) return;
    snapshot = next;
    for (const listener of listeners) listener();
  }
  function read(): BrowserSnapshot {
    const next = { ...snapshot, ready: true };
    const s = storage();
    if (!s) return { ...next, notice: MEMORY_NOTICE };
    for (const field of ["entry", "starred", "history"] as const) {
      const key = keys[field];
      if (memoryOnly.has(key)) continue;
      try {
        const raw = s.getItem(key);
        if (field === "entry") {
          if (raw !== null && raw !== "1") throw Error("invalid entry");
          next.entered = raw === "1";
        } else {
          const parsed: unknown = raw === null ? [] : JSON.parse(raw);
          if (!Array.isArray(parsed)) throw Error("invalid list");
          // Invalid rows remain recoverable: do not replace the stored array on a later edit.
          if (field === "starred") {
            if (!parsed.every(v => validStar(v, mock))) throw Error("invalid star");
            next.starred = unique(parsed, v => v.id, 500);
          } else {
            if (!parsed.every(validHistory)) throw Error("invalid history");
            next.history = unique(parsed, v => v.article.id, 30);
          }
        }
      } catch { memoryOnly.add(key); next.notice = CORRUPT_NOTICE; }
    }
    return next;
  }
  function write(field: "entry" | "starred" | "history", value: unknown, next: BrowserSnapshot) {
    const key = keys[field];
    if (!memoryOnly.has(key)) {
      try {
        const s = storage(); if (!s) throw Error("unavailable");
        s.setItem(key, field === "entry" ? "1" : JSON.stringify(value));
      } catch { memoryOnly.add(key); next.notice = MEMORY_NOTICE; }
    }
    update(next);
  }
  const onStorage = (event: Event) => {
    const e = event as StorageEvent;
    if (e.storageArea && e.storageArea !== storage()) return;
    if (e.key === null || Object.values(keys).includes(e.key)) update(read());
  };
  return {
    getSnapshot: () => snapshot, getServerSnapshot: () => EMPTY,
    subscribe(listener) {
      if (!listeners.size) target?.addEventListener("storage", onStorage);
      listeners.add(listener);
      return () => { listeners.delete(listener); if (!listeners.size) target?.removeEventListener("storage", onStorage); };
    },
    hydrate() { update(read()); },
    markEntered() { const next = read(); next.entered = true; write("entry", "1", next); },
    toggleStar(item) {
      // Explicit projection excludes full text or arbitrary fields supplied by callers.
      const saved = { id: item.id, title: item.title, summary: item.summary, sourceName: item.sourceName, publishedAt: item.publishedAt, score: item.score, savedAt: now().toISOString() };
      if (!validStar(saved, mock)) return;
      const next = read();
      next.starred = next.starred.some(v => v.id === item.id) ? next.starred.filter(v => v.id !== item.id) : [saved, ...next.starred].slice(0, 500);
      write("starred", next.starred, next);
    },
    removeStar(id) { const next = read(); next.starred = next.starred.filter(v => v.id !== id); write("starred", next.starred, next); },
    recordRead(article) {
      const entry = { article, viewedAt: now().toISOString() };
      if (!validHistory(entry)) return;
      const next = read(); next.history = [entry, ...next.history.filter(v => v.article.id !== article.id)].slice(0, 30);
      write("history", next.history, next);
    },
    clearHistory() { const next = read(); next.history = []; write("history", [], next); },
  };
}
const stores = new Map<boolean, BrowserStateStore>();
export function getBrowserState(mock = false): BrowserStateStore {
  let store = stores.get(mock);
  if (!store) { store = createBrowserState(mock); stores.set(mock, store); }
  return store;
}
