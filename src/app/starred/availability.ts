// Adapted from AIHOT starred.tsx and publication/availability.ts (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
export type Availability = { status: 'public' | 'summary-only' | 'unavailable' | 'unknown'; sourceName?: string };
export function parseAvailability(data: unknown, ids: string[]): Record<string, Availability> {
  const rows = (data as { items?: unknown } | null)?.items;
  if (!Array.isArray(rows) || rows.length !== ids.length) throw Error('invalid availability');
  const remaining = new Set(ids);
  const out: Record<string, Availability> = {};
  for (const row of rows) {
    if (!row || typeof row.id !== 'string' || !remaining.delete(row.id) || typeof row.available !== 'boolean') throw Error('invalid availability');
    const status = row.status ?? (row.available ? 'public' : 'unavailable');
    if (!['public', 'summary-only', 'unavailable'].includes(status) || row.available !== (status !== 'unavailable') || (row.source_name !== undefined && typeof row.source_name !== 'string')) throw Error('invalid availability');
    out[row.id] = { status, ...(row.source_name ? { sourceName: row.source_name } : {}) };
  }
  if (remaining.size) throw Error('invalid availability');
  return out;
}
export async function loadAvailability(ids: string[], signal: AbortSignal, request: typeof fetch = fetch) {
  const unique = [...new Set(ids)];
  const batches: string[][] = [];
  for (let offset = 0; offset < unique.length; offset += 100) batches.push(unique.slice(offset, offset + 100));
  const parts = await Promise.all(batches.map(async batch => {
    try {
      const response = await request(`/api/bluepulse/articles/availability?ids=${encodeURIComponent(batch.join(','))}`, { cache: 'no-store', signal: AbortSignal.any([signal, AbortSignal.timeout(12000)]) });
      if (!response.ok) throw Error('availability');
      return { items: parseAvailability(await response.json(), batch), error: false };
    } catch { return { items: {}, error: true }; }
  }));
  return { items: Object.assign({}, ...parts.map(p => p.items)) as Record<string, Availability>, error: parts.some(p => p.error) };
}
