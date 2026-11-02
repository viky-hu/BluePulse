import type { FeedArticle } from '../../_lib/feed-types';
const previews = new Map<string, FeedArticle>();
const key = (id: string, mock: boolean) => `${mock ? 'mock' : 'live'}:${id}`;
export function rememberArticlePreview(item: FeedArticle, mock: boolean) {
    const k = key(item.id, mock);
    previews.delete(k);
    previews.set(k, item);
    if (previews.size > 40)
        previews.delete(previews.keys().next().value!);
}
export function takeArticlePreview(id: string, mock: boolean): FeedArticle | null {
    const k = key(id, mock);
    const item = previews.get(k) ?? null;
    previews.delete(k);
    return item;
}
