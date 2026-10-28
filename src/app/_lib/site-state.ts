// AIHOT local-state.ts changelog read marker and last-page tracking adaptation (MIT).
import { validVersion } from "../changelog/_data.ts";
type Snapshot = { ready: boolean; seen: string | null };
type Options = { storage?: () => Pick<Storage, "getItem" | "setItem"> | null; eventTarget?: EventTarget };
const EMPTY: Snapshot = { ready: false, seen: null };
export const seenKey = (mock = false) => `blue-pulse-changelog-seen-v1${mock ? ":mock" : ""}`;
export function createSiteStateStore(mock = false, options: Options = {}) {
  const key = seenKey(mock), listeners = new Set<() => void>();
  let snapshot = EMPTY, memoryOnly = false;
  const storage = () => { try { return options.storage ? options.storage() : typeof window !== "undefined" ? window.localStorage : null; } catch { return null; } };
  const target = options.eventTarget ?? (typeof window !== "undefined" ? window : null);
  const emit = (seen: string | null) => {
    if (snapshot.ready && snapshot.seen === seen) return;
    snapshot = { ready: true, seen }; listeners.forEach(listener => listener());
  };
  const read = () => {
    if (memoryOnly) return snapshot.seen;
    try { const raw = storage()?.getItem(key); if (raw && !validVersion(raw)) { memoryOnly = true; return snapshot.seen; } return raw || null; } catch { return snapshot.seen; }
  };
  const onStorage = (event: Event) => { const e = event as StorageEvent; if ((e.key === key || e.key === null) && (!e.storageArea || e.storageArea === storage())) emit(read()); };
  return {
    getSnapshot: () => snapshot, getServerSnapshot: () => EMPTY,
    subscribe(listener: () => void) { if (!listeners.size) target?.addEventListener("storage", onStorage); listeners.add(listener); return () => { listeners.delete(listener); if (!listeners.size) target?.removeEventListener("storage", onStorage); }; },
    hydrate() { emit(read()); },
    markSeen(version: string) {
      if (!validVersion(version)) return;
      const current = read(), seen = current && current > version ? current : version;
      if (!memoryOnly) { try { const s = storage(); if (!s) throw Error(); s.setItem(key, seen); } catch { memoryOnly = true; } }
      emit(seen);
    },
  };
}
const stores = new Map<boolean, ReturnType<typeof createSiteStateStore>>();
export function getSiteState(mock = false) { if (!stores.has(mock)) stores.set(mock, createSiteStateStore(mock)); return stores.get(mock)!; }
const pageKey = (mock: boolean) => `blue-pulse-last-page-v1${mock ? ":mock" : ""}`;
const pages = new Map<boolean, string>();
export function rememberPage(path: string, mock = false) {
  if (!path.startsWith("/") || path.startsWith("//") || path.split("?")[0] === "/feedback") return;
  pages.set(mock, path);
  try { window.sessionStorage.setItem(pageKey(mock), path); } catch {}
}
export function lastPage(mock = false): string | null {
  try { const path = window.sessionStorage.getItem(pageKey(mock)); if (path?.startsWith("/") && !path.startsWith("//") && path.split("?")[0] !== "/feedback") return path; } catch {}
  return pages.get(mock) ?? null;
}
