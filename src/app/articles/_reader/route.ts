// Pure route parsing: safe for shared shell imports.
export const ARTICLE_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export function articleRoute(pathname: string): {
    id: string;
    language: 'zh' | 'original';
} | null {
    pathname = new URL(pathname, 'http://pulse.local').pathname;
    const match = /^\/articles\/([^/]+)(\/original)?$/.exec(pathname);
    return match && ARTICLE_ID_PATTERN.test(match[1]) ? {
        id: match[1], language: match[2] ? 'original' : 'zh'
    } : null;
}
export function articleKey(value: string): string {
    const url = new URL(value, 'http://pulse.local');
    url.searchParams.sort();
    return url.pathname.replace(/\/$/, '') + url.search;
}
