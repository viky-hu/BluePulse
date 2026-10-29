"use client";
import { useEffect, useState } from 'react';
import { MOCK_ARTICLE_DETAILS } from '../_lib/home-mock';
import { loadAvailability, type Availability } from './availability';
export function useAvailability(ids: string[], ready: boolean, mock: boolean, refreshRevision: number): { items: Record<string, Availability>; error: boolean } {
  const idsKey = [...new Set(ids)].sort().join(',');
  const key = `${mock}:${refreshRevision}:${idsKey}`;
  const [result, setResult] = useState<{ key: string; items: Record<string, Availability>; error: boolean }>({ key: '', items: {}, error: false });
  useEffect(() => {
    if (!ready) return;
    const controller = new AbortController();
    const entries = idsKey ? idsKey.split(',') : [];
    const promise = mock
      ? Promise.resolve({ items: Object.fromEntries(entries.map(id => [id, { status: MOCK_ARTICLE_DETAILS[id] ? 'public' : 'unavailable' }])) as Record<string, Availability>, error: false })
      : loadAvailability(entries, controller.signal);
    promise.then(next => { if (!controller.signal.aborted) setResult({ ...next, key }); });
    return () => controller.abort();
  }, [idsKey, ready, mock, key]);
  return result.key === key ? result : { items: {}, error: false };
}
