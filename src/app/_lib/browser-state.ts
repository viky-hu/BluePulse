// Adapted from AIHOT apps/web/app/lib/local-state.ts (MIT); see third-party license notice.
// Stable snapshots, guarded storage, subscription cleanup and fresh reads before edits follow AIHOT.
import type { ArticleCard } from "./home-data";

export interface LocalStarredItem { id: string; title: string; summary: string | null; sourceName: string; publishedAt: string | null; score: number | null; savedAt: string }
export interface HistoryEntry { article: ArticleCard; viewedAt: string }
export interface LocalDataBundle { version: 1; starred: LocalStarredItem[]; read: string[]; theme: "auto" }
export interface ImportReport { starredAdded: number; starredSkipped: number; readAdded: number; readSkipped: number; readFailed: boolean }
export interface BrowserSnapshot { ready: boolean; entered: boolean; starred: LocalStarredItem[]; readIds: string[]; history: HistoryEntry[]; notice: string | null }
export interface BrowserStateStore {
  getSnapshot(): BrowserSnapshot; getServerSnapshot(): BrowserSnapshot;
  subscribe(listener: () => void): () => void; hydrate(): void; markEntered(): void;
  toggleStar(item: Omit<LocalStarredItem, "savedAt">): void; removeStar(id: string): void;
  recordRead(article: ArticleCard): void; clearHistory(): void;
  exportBundle(): LocalDataBundle; importBundle(text: string): ImportReport;
}
export interface BrowserStateOptions { storage?: () => Storage | null; eventTarget?: EventTarget; now?: () => Date }
export function browserKeys(mock = false) {
  const suffix = mock ? ":mock" : "";
  return { entry: `blue-pulse-entry-complete-v1${suffix}`, starred: `blue-pulse-starred-items-v1${suffix}`, history: `blue-pulse-reading-history-v1${suffix}`, read: `blue-pulse-read-items-v1${suffix}` };
}
const EMPTY: BrowserSnapshot = { ready: false, entered: false, starred: [], readIds: [], history: [], notice: null };
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
  const damaged = new Set<string>();
  const validId = (v: unknown): v is string => text(v) && (mock ? /^[a-zA-Z0-9_-]{1,80}$/.test(v) : uuid.test(v));
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
      } catch { memoryOnly.add(key); damaged.add(key); next.notice = CORRUPT_NOTICE; }
    }
    if (!memoryOnly.has(keys.read)) {
      try {
        const raw = s.getItem(keys.read);
        if (raw === null) {
          // One-time migration: imported read IDs never manufacture historical article snapshots.
          next.readIds = unique(next.history.map(v => v.article.id).filter(validId), v => v, 5000);
          try { s.setItem(keys.read, JSON.stringify(next.readIds)); }
          catch { memoryOnly.add(keys.read); next.notice = MEMORY_NOTICE; }
        } else {
          const parsed: unknown = JSON.parse(raw);
          if (!Array.isArray(parsed) || !parsed.every(validId)) throw Error("invalid read IDs");
          next.readIds = unique(parsed, v => v, 5000);
        }
      } catch { memoryOnly.add(keys.read); damaged.add(keys.read); next.notice = CORRUPT_NOTICE; }
    }
    return next;
  }
  function write(field: "entry" | "starred" | "history" | "read", value: unknown, next: BrowserSnapshot, notify = true) {
    const key = keys[field];
    if (!memoryOnly.has(key)) {
      try {
        const s = storage(); if (!s) throw Error("unavailable");
        s.setItem(key, field === "entry" ? "1" : JSON.stringify(value));
      } catch { memoryOnly.add(key); next.notice = MEMORY_NOTICE; }
    }
    if (notify) update(next);
  }
  function normalizeStar(value: unknown): LocalStarredItem | null {
    if (!value || typeof value !== "object") return null;
    const s = value as Record<string, unknown>;
    if (!validId(s.id) || !text(s.title)) return null;
    // Explicit projection: backups never carry article bodies or arbitrary imported properties.
    return {
      id: s.id, title: s.title, summary: typeof s.summary === "string" ? s.summary : null,
      sourceName: typeof s.sourceName === "string" ? s.sourceName : "",
      publishedAt: date(s.publishedAt) ? s.publishedAt : null,
      savedAt: date(s.savedAt) ? s.savedAt : now().toISOString(),
      score: typeof s.score === "number" && Number.isFinite(s.score) ? s.score : null,
    };
  }
  function importData(raw: string): ImportReport {
    if (raw.length > 2_000_000) throw Error("文件过大（上限 2,000,000 字符）");
    let data: unknown;
    try { data = JSON.parse(raw); } catch { throw Error("不是有效的 JSON 文件"); }
    if (!data || typeof data !== "object" || (data as Record<string, unknown>).version !== 1) throw Error("文件格式不对（需要 version: 1）");
    const incoming = data as Record<string, unknown>;
    const next = read();
    if (damaged.has(keys.starred)) throw Error("这台设备上已有的收藏数据无法读取，为避免覆盖，这次没有导入。");
    const have = new Set(next.starred.map(s => s.id));
    const additions: LocalStarredItem[] = [];
    let starredSkipped = 0, readSkipped = 0;
    for (const row of Array.isArray(incoming.starred) ? incoming.starred : []) {
      const item = normalizeStar(row);
      if (!item) { starredSkipped++; continue; }
      if (have.has(item.id)) continue;
      have.add(item.id); additions.push(item);
    }
    const accepted = additions.slice(0, Math.max(0, 500 - next.starred.length));
    starredSkipped += additions.length - accepted.length;
    const merged = [...next.starred, ...accepted].sort((a, b) => Date.parse(b.savedAt) - Date.parse(a.savedAt));
    try {
      // Imports require durable storage. Ordinary edits still retain their in-memory fallback.
      const s = storage(); if (!s || memoryOnly.has(keys.starred)) throw Error("unavailable");
      s.setItem(keys.starred, JSON.stringify(merged));
    } catch { throw Error("浏览器存储已满或不可用，这次没有导入任何内容。"); }
    next.starred = merged;
    const readHave = new Set(next.readIds), readAdditions: string[] = [];
    for (const value of Array.isArray(incoming.read) ? incoming.read : []) {
      if (!validId(value)) { readSkipped++; continue; }
      if (readHave.has(value)) continue;
      readHave.add(value); readAdditions.push(value);
    }
    const acceptedRead = readAdditions.slice(0, Math.max(0, 5000 - next.readIds.length));
    readSkipped += readAdditions.length - acceptedRead.length;
    let readFailed = false;
    try {
      const s = storage(); if (!s || memoryOnly.has(keys.read)) throw Error("unavailable");
      s.setItem(keys.read, JSON.stringify([...next.readIds, ...acceptedRead]));
      next.readIds = [...next.readIds, ...acceptedRead];
    } catch { readFailed = true; }
    update(next);
    return { starredAdded: accepted.length, starredSkipped, readAdded: readFailed ? 0 : acceptedRead.length, readSkipped, readFailed };
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
      if (validId(article.id)) {
        next.readIds = [article.id, ...next.readIds.filter(id => id !== article.id)].slice(0, 5000);
        write("read", next.readIds, next, false);
      }
      write("history", next.history, next);
    },
    clearHistory() { const next = read(); next.history = []; write("history", [], next); },
    exportBundle() {
      const next = read(); update(next);
      return { version: 1, starred: next.starred.map(item => normalizeStar(item)!), read: [...next.readIds], theme: "auto" };
    },
    importBundle: importData,
  };
}
const stores = new Map<boolean, BrowserStateStore>();
export function getBrowserState(mock = false): BrowserStateStore {
  let store = stores.get(mock);
  if (!store) { store = createBrowserState(mock); stores.set(mock, store); }
  return store;
}
