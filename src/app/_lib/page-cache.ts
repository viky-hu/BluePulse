type Entry<T> = {
  expiresAt: number;
  hasValue: boolean;
  value?: T;
  pending?: Promise<T>;
};

/** Same-document reuse, bounded by both a local cap and the upstream's absolute deadline. */
export function createTimedPageCache<T>(
  ttlMs: number,
  maxEntries: number,
  now: () => number = Date.now,
) {
  if (!Number.isFinite(ttlMs) || ttlMs <= 0) throw new RangeError("ttlMs must be positive");
  if (!Number.isInteger(maxEntries) || maxEntries <= 0) throw new RangeError("maxEntries must be a positive integer");

  const pages = new Map<string, Entry<T>>();

  function touch(key: string, entry: Entry<T>) {
    pages.delete(key);
    pages.set(key, entry);
  }

  function trim() {
    const completed = [...pages].filter(([, entry]) => entry.hasValue).length;
    let remaining = completed;
    if (remaining <= maxEntries) return;
    for (const [key, entry] of pages) {
      if (!entry.hasValue) continue;
      pages.delete(key);
      remaining -= 1;
      if (remaining <= maxEntries) return;
    }
  }

  function get(key: string): T | undefined {
    const entry = pages.get(key);
    if (!entry) return undefined;
    if (entry.pending) return undefined;
    if (!entry.hasValue || entry.expiresAt <= now()) {
      pages.delete(key);
      return undefined;
    }
    touch(key, entry);
    return entry.value;
  }

  function load(
    key: string,
    loader: () => Promise<T> | T,
    options: { force?: boolean; shouldCache?: (value: T) => boolean; expiresAt?: (value: T) => number } = {},
  ): Promise<T> {
    if (options.force) pages.delete(key);
    else {
      const existing = pages.get(key);
      if (existing?.pending) return existing.pending;
      if (existing?.hasValue && existing.expiresAt > now()) {
        touch(key, existing);
        return Promise.resolve(existing.value as T);
      }
      if (existing) pages.delete(key);
    }

    const entry: Entry<T> = { expiresAt: 0, hasValue: false };
    pages.set(key, entry);
    trim();

    const pending = Promise.resolve()
      .then(loader)
      .then(value => {
        if (pages.get(key) === entry) {
          const deadline = options.expiresAt?.(value) ?? now() + ttlMs;
          if ((options.shouldCache?.(value) ?? true) && Number.isFinite(deadline) && deadline > now()) {
            entry.value = value;
            entry.hasValue = true;
            entry.expiresAt = Math.min(deadline, now() + ttlMs);
            entry.pending = undefined;
            touch(key, entry);
            trim();
          } else {
            pages.delete(key);
          }
        }
        return value;
      }, error => {
        if (pages.get(key) === entry) pages.delete(key);
        throw error;
      });
    entry.pending = pending;
    return pending;
  }

  return { get, load, invalidate: (key: string) => pages.delete(key) };
}
