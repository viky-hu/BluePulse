// Adapted from AIHOT apps/web/app/lib/session-cache.ts and restore.ts (MIT).
// Preserves bounded session memory and the original save time during reads; see third-party notice.
interface Envelope { version: 1; savedAt: number; value: unknown }
const AGE = 30 * 60 * 1000;
const LIMIT = 20;
const memory = new Map<string, Envelope>();
const fallback = new Set<string>();
// Keep damaged/unknown data recoverable for the entire document lifetime, even after eviction.
const protectedKeys = new Set<string>();
const prefix = (mock: boolean) => `blue-pulse-session-v1:${mock ? "mock" : "live"}:`;
function storage() { try { return typeof window !== "undefined" ? window.sessionStorage : null; } catch { return null; } }
function wellFormed(value: unknown): value is Envelope {
  if (!value || typeof value !== "object") return false;
  const e = value as Envelope;
  return e.version === 1 && typeof e.savedAt === "number" && Number.isFinite(e.savedAt) && e.savedAt >= 0 && e.savedAt <= Date.now() && Object.hasOwn(e, "value");
}
function valid(value: unknown): value is Envelope { return wellFormed(value) && Date.now() - value.savedAt <= AGE; }
function inspectStored(s: Storage, key: string): Envelope | null {
  const raw = s.getItem(key);
  if (raw === null) return null;
  let parsed: unknown;
  try { parsed = JSON.parse(raw); } catch { protectedKeys.add(key); return null; }
  if (!wellFormed(parsed)) { protectedKeys.add(key); return null; }
  if (!valid(parsed)) { s.removeItem(key); return null; }
  return parsed;
}
function removeRecoverable(key: string) {
  if (protectedKeys.has(key)) return;
  try { const s = storage(); if (s) { inspectStored(s, key); if (!protectedKeys.has(key)) s.removeItem(key); } } catch {}
}
function remember(key: string, value: Envelope, scope: string) {
  memory.delete(key); memory.set(key, value);
  const keys = [...memory.keys()].filter(k => k.startsWith(scope));
  while (keys.length > LIMIT) { const oldest = keys.shift()!; memory.delete(oldest); fallback.delete(oldest); removeRecoverable(oldest); }
}
export function saveSessionSnapshot<T>(key: string, value: T, mock = false): void {
  const scope = prefix(mock), fullKey = scope + key;
  // JSON clone makes the saved snapshot independent of later mutations by its caller.
  let envelope: Envelope;
  try { envelope = JSON.parse(JSON.stringify({ version: 1, savedAt: Date.now(), value })); if (!valid(envelope)) return; } catch { return; }
  remember(fullKey, envelope, scope);
  if (protectedKeys.has(fullKey)) return;
  try {
    const s = storage(); if (!s) throw Error("unavailable");
    inspectStored(s, fullKey);
    if (protectedKeys.has(fullKey)) return;
    s.setItem(fullKey, JSON.stringify(envelope)); fallback.delete(fullKey);
    const entries: { key: string; savedAt: number }[] = [];
    const storedKeys = Array.from({ length: s.length }, (_, i) => s.key(i)).filter((k): k is string => !!k && k.startsWith(scope));
    for (const k of storedKeys) {
      if (protectedKeys.has(k)) continue;
      const parsed = inspectStored(s, k);
      if (parsed) entries.push({ key: k, savedAt: parsed.savedAt });
    }
    entries.sort((a, b) => a.savedAt - b.savedAt);
    for (const old of entries.slice(0, Math.max(0, entries.length - LIMIT))) { s.removeItem(old.key); memory.delete(old.key); }
  } catch { fallback.add(fullKey); }
}
export function readSessionSnapshot<T>(key: string, mock = false): T | null {
  const scope = prefix(mock), fullKey = scope + key;
  let value: unknown = memory.get(fullKey);
  if (!value && !fallback.has(fullKey) && !protectedKeys.has(fullKey)) { try { const s = storage(); value = s ? inspectStored(s, fullKey) : null; } catch { return null; } }
  if (!valid(value)) { memory.delete(fullKey); fallback.delete(fullKey); removeRecoverable(fullKey); return null; }
  remember(fullKey, value, scope);
  return value.value as T;
}

/** Invalidating data never deletes a separately saved position or damaged recoverable storage. */
export function invalidateSessionSnapshot(key: string, mock = false): void {
  const fullKey = prefix(mock) + key;
  memory.delete(fullKey); fallback.delete(fullKey); removeRecoverable(fullKey);
}
