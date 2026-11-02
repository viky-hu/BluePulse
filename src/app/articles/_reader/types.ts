// AIHOT site contracts/detail adaptation (MIT). Copyright (c) 2026 数字生命卡兹克.
import type { ArticleDetail, TopicInfo } from '../_data';
import type { GroupInfo, MediaView } from '../../_lib/feed-types';
export type { GroupInfo } from '../../_lib/feed-types';
export interface OutlineEntry {
    id: string;
    text: string;
    level: number;
}
export interface StoryRef {
    publicId: string;
    title: string;
}
export interface ReaderPost {
    authorName: string;
    handle: string;
    avatarUrl: string | null;
    avatarSrcSet?: string;
    media: MediaView[];
    quoted: {
        authorName: string;
        handle: string;
        text: string;
        url: string;
        translation: string | null;
    } | null;
}
export interface ArticleReader {
    readingMode: 'full' | 'summary-only';
    body: {
        zh: string | null;
        original: string | null;
        zhKind: 'translation' | 'original' | null;
        complete: boolean;
    } | null;
    bodyLanguage: 'zh' | 'original';
    hasTranslation: boolean;
    outline: OutlineEntry[];
    reason?: string | null;
    selected?: boolean;
    sameEvent?: {
        id: string;
        title: string;
    } | null;
    group: GroupInfo | null;
    story: StoryRef | null;
    relatedStories: StoryRef[];
    tags: string[];
    channel?: 'news' | 'x';
    x: ReaderPost | null;
    indexable: boolean;
    markdownAvailable: boolean;
}
export interface ReaderArticle extends Omit<ArticleReader, 'body' | 'outline' | 'selected' | 'reason' | 'sameEvent' | 'channel'> {
    article: ArticleDetail;
    bodyHtml: string | null;
    complete: boolean;
    zhKind: 'translation' | 'original' | null;
    outline: OutlineEntry[];
    selected: boolean;
    reason: string | null;
    sameEvent: {
        id: string;
        title: string;
    } | null;
    channel: 'news' | 'x';
}
export interface ArticlePageData {
    key: string;
    status: 'loading' | 'ready' | 'not-found' | 'error';
    item: ReaderArticle | null;
    error: string | null;
    expiresAt: number;
    taxonomy: TopicInfo[];
}
export interface StoryFollowup {
    factId: string;
    representative: {
        id: string;
        title: string;
        source: {
            name: string;
        };
        timelineAt: string;
    };
}
export interface StoryFollowupsResponse {
    items: StoryFollowup[];
    more: boolean;
}
