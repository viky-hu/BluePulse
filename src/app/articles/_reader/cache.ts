import { createTimedPageCache } from '../../_lib/page-cache.ts';
import { articleKey } from './route.ts';
import type { ArticlePageData } from './types';
const pages = createTimedPageCache<ArticlePageData>(60000, 16);
const cacheKey = (key: string, mock: boolean) => `${mock ? 'mock' : 'live'}:${articleKey(key)}`;
export const getCachedArticle = (key: string, mock: boolean) => pages.get(cacheKey(key, mock)) ?? null;
export const invalidateArticle = (key: string, mock: boolean) => pages.invalidate(cacheKey(key, mock));
/** SSR hydration seeds the same document cache without renewing the upstream deadline. */
export function primeArticle(data: ArticlePageData, mock: boolean) {
    if (data.status === 'ready' && data.expiresAt > Date.now()) {
        void pages.load(cacheKey(data.key, mock), () => data, { force: true, shouldCache: value => value.status === 'ready', expiresAt: value => value.expiresAt });
    }
}
export const loadArticle = (key: string, mock: boolean, options: {
    force?: boolean;
} = {}) => pages.load(cacheKey(key, mock), async () => {
    const { requestArticlePage } = await import('./data.ts');
    return requestArticlePage(key, mock);
}, {
    force: options.force, shouldCache: data => data.status === 'ready', expiresAt: data => data.expiresAt
});
