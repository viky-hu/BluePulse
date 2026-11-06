// Pulse HTTP contract, distinct from AIHOT's public API version and payload.
export function siteOrigin(raw?: string): string | null {
  if (!raw || raw !== raw.trim() || !/^https?:\/\/[^/?#\\]+\/?$/i.test(raw)) return null;
  try {
    const url = new URL(raw);
    if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password || !['', '/'].includes(url.pathname) || url.search || url.hash || /\s/.test(raw)) return null;
    return url.origin;
  } catch { return null; }
}

export type AgentKind = 'latest' | 'search';
export function isAgentList(value: unknown, kind: AgentKind): boolean {
  if (!value || typeof value !== 'object') return false;
  const body = value as Record<string, unknown>;
  if (body.schema_version !== 1 || !Array.isArray(body.items) || !body.query || typeof body.query !== 'object') return false;
  const query = body.query as Record<string, unknown>;
  return query.kind === kind && query.sort_basis === 'source_publication_then_first_seen' &&
    ['24h', '7d', '30d', ...(kind === 'search' ? ['all'] : [])].includes(String(query.window)) &&
    typeof query.limit === 'number' && query.limit >= 1 && query.limit <= 30 &&
    (kind === 'latest' ? query.q === null : typeof query.q === 'string');
}

export const AGENT_PATH = '/api/v1/agent';
export const LATEST_PATH = `${AGENT_PATH}/latest?window=7d&limit=10`;
export const SEARCH_PATH = `${AGENT_PATH}/search?q=${encodeURIComponent('警务技术')}&window=all&limit=10`;
export type AgentTab = 'guide' | 'api';
export const tabKey = (value: string | null): AgentTab => value === 'api' ? 'api' : 'guide';
export const tabHref = (value: AgentTab) => value === 'guide' ? '/agent' : '/agent?tab=api';
export const ANCHORS: Record<string, AgentTab> = { 'agent-api-reference': 'api', 'agent-api-recovery': 'api', 'agent-guide-capabilities': 'guide' };
