import type { ArticleDetail } from '../_data';
import type { ArticleReader, ReaderArticle, ArticlePageData } from './types';
import { cleanBody, plainTextHtml } from './text.ts';
import { responseDeadline } from '../../_lib/http-cache.ts';
import { ARTICLE_ID_PATTERN, articleRoute, articleKey } from './route.ts';
export { ARTICLE_ID_PATTERN, articleRoute, articleKey } from './route.ts';
export function emptyArticlePage(key: string): ArticlePageData {
    return {
        key: articleKey(key), status: 'loading', item: null, error: null, expiresAt: 0, taxonomy: []
    };
}
function validReader(value: unknown): value is ArticleReader {
    if (!value || typeof value !== 'object')
        return false;
    const r = value as ArticleReader;
    const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
    const story = (v: unknown) => v === null || (object(v) && typeof v.publicId === 'string' && /^[a-zA-Z0-9_-]{1,80}$/.test(v.publicId) && typeof v.title === 'string');
    const url = (v: unknown) => {
        if (v === null)
            return true;
        if (typeof v !== 'string' || /[\u0000-\u0020\u007f]/.test(v) || !/^(?:https?:\/\/|\/(?!\/))/.test(v))
            return false;
        try {
            return ['https:', 'http:'].includes(new URL(v, 'http://pulse.local').protocol);
        }
        catch {
            return false;
        }
    };
    const srcSet = (v: unknown) => v === undefined || (typeof v === 'string' && v.split(',').every(part => {
        const [src, size, ...extra] = part.trim().split(/\s+/);
        return url(src) && (!size || /^\d+(?:\.\d+)?[wx]$/.test(size)) && !extra.length;
    }));
    const group = r.group === null || (object(r.group) && typeof r.group.factId === 'string' && /^[a-zA-Z0-9_-]{1,80}$/.test(r.group.factId) && Number.isInteger(r.group.reportCount) && r.group.reportCount >= 0 && Number.isInteger(r.group.additionalSourceCount) && r.group.additionalSourceCount >= 0);
    const post = r.x === null || (object(r.x) && typeof r.x.authorName === 'string' && typeof r.x.handle === 'string' && url(r.x.avatarUrl) && srcSet(r.x.avatarSrcSet) && Array.isArray(r.x.media) && r.x.media.every(m => object(m) && ['image', 'video'].includes(String(m.kind)) && m.url !== null && url(m.url) && url(m.poster) && url(m.fullUrl ?? null) && srcSet(m.srcSet)) && (r.x.quoted === null || (object(r.x.quoted) && typeof r.x.quoted.text === 'string' && typeof r.x.quoted.authorName === 'string' && typeof r.x.quoted.handle === 'string' && r.x.quoted.url !== null && url(r.x.quoted.url) && (r.x.quoted.translation === null || typeof r.x.quoted.translation === 'string'))));
    if (!group || !post || !story(r.story) || !Array.isArray(r.relatedStories) || !r.relatedStories.every(value => value !== null && story(value)) || !(r.channel === undefined || r.channel === 'news' || r.channel === 'x') || !(r.reason === undefined || r.reason === null || typeof r.reason === 'string') || !(r.selected === undefined || typeof r.selected === 'boolean') || !(r.sameEvent === undefined || r.sameEvent === null || (object(r.sameEvent) && typeof r.sameEvent.id === 'string' && ARTICLE_ID_PATTERN.test(r.sameEvent.id) && typeof r.sameEvent.title === 'string')))
        return false;
    return ['full', 'summary-only'].includes(r.readingMode) && ['zh', 'original'].includes(r.bodyLanguage) && typeof r.hasTranslation === 'boolean' && typeof r.indexable === 'boolean' && typeof r.markdownAvailable === 'boolean' && Array.isArray(r.outline) && Array.isArray(r.relatedStories) && Array.isArray(r.tags) && r.tags.every(t => typeof t === 'string') && (r.body === null || (typeof r.body === 'object' && r.body !== null && (r.body.zh === null || typeof r.body.zh === 'string') && (r.body.original === null || typeof r.body.original === 'string') && [null, 'original', 'translation'].includes(r.body.zhKind) && typeof r.body.complete === 'boolean'));
}
function normalizeLegacy(raw: unknown): ArticleDetail {
    if (!raw || typeof raw !== 'object') throw new Error('文章数据格式异常。');
    const value = raw as Record<string, unknown>;
    const source = value.source as Record<string, unknown> | null;
    if (typeof value.id !== 'string' || !ARTICLE_ID_PATTERN.test(value.id) ||
        typeof value.title !== 'string' || !value.title.trim() ||
        typeof value.language !== 'string' || !value.language.trim() ||
        typeof value.url !== 'string' ||
        typeof value.importance_score !== 'number' || !Number.isFinite(value.importance_score) ||
        !source || typeof source !== 'object' || typeof source.name !== 'string' || !source.name.trim()) {
        throw new Error('文章数据格式异常。');
    }
    const nullable = (field: unknown): string | null => typeof field === 'string' ? field : null;
    const strings = (field: unknown): string[] => Array.isArray(field) ? field.filter((entry): entry is string => typeof entry === 'string') : [];
    return {
        id: value.id, title: value.title, language: value.language, url: value.url,
        importance_score: value.importance_score,
        source: {id: typeof source.id === 'string' ? source.id : '', name: source.name,
            slug: typeof source.slug === 'string' ? source.slug : '',
            source_type: typeof source.source_type === 'string' ? source.source_type : ''},
        source_title: typeof value.source_title === 'string' ? value.source_title : value.title,
        summary: nullable(value.summary), author: nullable(value.author),
        source_body: nullable(value.source_body), zh_body: nullable(value.zh_body),
        published_at: nullable(value.published_at), first_seen_at: nullable(value.first_seen_at),
        region: nullable(value.region), topics: strings(value.topics),
        entities: Array.isArray(value.entities) ? value.entities.filter(entry => entry && typeof entry.slug === 'string' && typeof entry.name === 'string' && typeof entry.entity_type === 'string').map(entry => ({slug:entry.slug,name:entry.name,entity_type:entry.entity_type})) : [],
        media: Array.isArray(value.media) ? value.media.filter(entry => entry && typeof entry.kind === 'string' && typeof entry.url === 'string').map(entry => ({kind:entry.kind,url:entry.url, thumbnail_url: nullable(entry.thumbnail_url), caption: nullable(entry.caption), alt_text: nullable(entry.alt_text)})) : [],
        parse_status: typeof value.parse_status === 'string' ? value.parse_status : 'unknown',
        quality_status: typeof value.quality_status === 'string' ? value.quality_status : 'unknown',
        body_status: ['full_text','abstract_only','summary_only','metadata_only','partial_text'].includes(String(value.body_status)) ? value.body_status as ArticleDetail['body_status'] : 'metadata_only',
        translation_status: ['not_required','available','pending','failed','source_unavailable','too_long'].includes(String(value.translation_status)) ? value.translation_status as ArticleDetail['translation_status'] : 'source_unavailable',
    };
}
export function normalizeArticle(raw: unknown, language: 'zh' | 'original' = 'zh'): ReaderArticle {
    const article = normalizeLegacy(raw);
    const wire = raw as ArticleDetail & {
        reader?: unknown;
    };
    const explicit = Object.hasOwn(wire, 'reader');
    if (explicit && !validReader(wire.reader))
        throw new Error('文章阅读数据格式异常。');
    const r = explicit ? wire.reader as ArticleReader : null;
    const restricted = r?.readingMode === 'summary-only';
    let bodyHtml: string | null = null;
    let bodyLanguage: 'zh' | 'original' = r?.bodyLanguage ?? 'original';
    if (r) {
        bodyLanguage = r.bodyLanguage;
        bodyHtml = restricted ? null : r.body?.[bodyLanguage] ?? null;
        if (!restricted && bodyHtml === null) {
            const alternate = bodyLanguage === 'zh' ? 'original' : 'zh';
            if (r.body?.[alternate] != null) {
                bodyLanguage = alternate;
                bodyHtml = r.body[alternate];
            }
        }
    }
    else {
        const chinese = /^zh(?:-|$)/i.test(article.language);
        bodyLanguage = language === 'zh' && (!!article.zh_body || chinese) ? 'zh' : 'original';
        const text = bodyLanguage === 'zh' ? (article.zh_body ?? (chinese ? article.source_body : null)) : article.source_body;
        bodyHtml = text ? plainTextHtml(text) : null;
    }
    const cleaned = bodyHtml ? cleanBody(bodyHtml) : {
        html: null, outline: []
    };
    return {
        article: restricted ? {
            ...article, source_body: null, zh_body: null, author: null, topics: [], media: []
        } : explicit ? {...article, source_body:null, zh_body:null} : article, bodyHtml: cleaned.html, bodyLanguage, hasTranslation: restricted ? false : r?.hasTranslation ?? Boolean(article.zh_body && article.source_body && !/^zh/i.test(article.language)), complete: restricted ? false : r ? (r.body?.complete ?? false) : (article.body_status === 'full_text'), zhKind: restricted ? null : r ? (r.body?.zhKind ?? null) : (bodyLanguage === 'zh' ? (article.zh_body ? 'translation' : 'original') : null), readingMode: restricted ? 'summary-only' : 'full', outline: cleaned.outline, reason: restricted ? null : r?.reason ?? null, selected: restricted ? false : r?.selected ?? false, sameEvent: restricted || !r?.sameEvent ? null : {id:r.sameEvent.id,title:r.sameEvent.title}, group: restricted || !r?.group ? null : {factId:r.group.factId,reportCount:r.group.reportCount,additionalSourceCount:r.group.additionalSourceCount}, story: restricted || !r?.story ? null : {publicId:r.story.publicId,title:r.story.title}, relatedStories: restricted ? [] : (r?.relatedStories ?? []).map(story=>({publicId:story.publicId,title:story.title})), tags: restricted ? [] : r?.tags ?? [], channel: r?.channel ?? 'news', x: restricted || !r?.x ? null : {
            authorName:r.x.authorName, handle:r.x.handle,avatarUrl:r.x.avatarUrl,
            ...(r.x.avatarSrcSet ? {avatarSrcSet:r.x.avatarSrcSet} : {}),
            media:r.x.media.map(media=>({kind:media.kind,url:media.url,poster:media.poster,
                width:typeof media.width==='number'&&Number.isFinite(media.width)?media.width:null,
                height:typeof media.height==='number'&&Number.isFinite(media.height)?media.height:null,
                alt:typeof media.alt==='string'?media.alt:null,
                ...(media.fullUrl?{fullUrl:media.fullUrl}:{}),...(media.srcSet?{srcSet:media.srcSet}:{})})),
            quoted:r.x.quoted ? {authorName:r.x.quoted.authorName,handle:r.x.quoted.handle,
                text:r.x.quoted.text,url:r.x.quoted.url,translation:r.x.quoted.translation} : null
        }, indexable: restricted ? false : r?.indexable ?? false, markdownAvailable: restricted ? false : r?.markdownAvailable ?? false
    };
}
export async function requestArticlePage(key: string, mock: boolean, signal?: AbortSignal): Promise<ArticlePageData> {
    const data = emptyArticlePage(key);
    const route = articleRoute(data.key);
    if (!route) {
        data.status = 'not-found';
        return data;
    }
    try {
        if (mock) {
            const { mockReaderArticle, mockReaderTaxonomy } = await import('./mock.ts');
            data.taxonomy = mockReaderTaxonomy;
            const raw = mockReaderArticle(route.id, route.language);
            if (!raw) {
                data.status = 'not-found';
                return data;
            }
            data.item = normalizeArticle(raw, route.language);
            data.expiresAt = Date.now() + 60000;
        }
        else {
            const response = await fetch(`/api/bluepulse/articles/${route.id}?body_language=${route.language}`, {
                cache: 'no-store', signal: signal ?? AbortSignal.timeout(12000)
            });
            if (!response.ok) {
                data.status = response.status === 404 ? 'not-found' : 'error';
                data.error = response.status === 404 ? null : `文章暂时无法载入（${response.status}）。`;
                return data;
            }
            data.item = normalizeArticle(await response.json(), route.language);
            data.expiresAt = responseDeadline(response.headers);
            try {
            const taxonomyResponse = await fetch('/api/bluepulse/taxonomy', {
                cache: 'no-store', signal: signal ?? AbortSignal.timeout(12000)
            });
            if (taxonomyResponse.ok) {
                const taxonomy = await taxonomyResponse.json();
                const list = Array.isArray(taxonomy) ? taxonomy : taxonomy.items;
                if (Array.isArray(list) && list.every(t => t && typeof t.slug === 'string' && typeof t.name_zh === 'string')) {
                    data.taxonomy = list;
                    data.expiresAt = Math.min(data.expiresAt, responseDeadline(taxonomyResponse.headers));
                }
                else
                    data.expiresAt = 0;
            }
            else
                data.expiresAt = 0;
            } catch {
                data.taxonomy = [];
                data.expiresAt = 0;
            }
        }
        data.status = 'ready';
    }
    catch (error) {
        data.status = 'error';
        data.error = error instanceof Error ? error.message : '文章暂时无法载入。';
    }
    return data;
}
