import sanitizeHtml from 'sanitize-html';
import type { OutlineEntry } from './types';
export const escapeHtml = (text: string) => text.replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[c]!));
export function plainTextHtml(text: string): string {
    return text.replace(/\r\n?/g, '\n').split(/\n\s*\n/).map(p => `<p>${escapeHtml(p).replace(/\n/g, '<br>')}</p>`).join('');
}
export function cleanBody(html: string): {
    html: string;
    outline: OutlineEntry[];
} {
    const clean = sanitizeHtml(html, {
        allowedTags: ['video', 'source', 'picture', 'h5', 'h6', 'tfoot', 'caption', 'u', 'mark', 'span', 'dl', 'dt', 'dd', 'p', 'br', 'h2', 'h3', 'h4', 'ul', 'ol', 'li', 'blockquote', 'pre', 'code', 'strong', 'em', 'b', 'i', 's', 'del', 'a', 'img', 'figure', 'figcaption', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'hr', 'sup', 'sub'], allowedAttributes: {
            a: ['href', 'title', 'rel'], img: ['src', 'srcset', 'alt', 'title', 'width', 'height'], video: ['src', 'poster', 'width', 'height', 'controls', 'preload'], source: ['src', 'srcset', 'type', 'media'], code: ['class'], th: ['colspan', 'rowspan'], td: ['colspan', 'rowspan']
        }, allowedClasses: {code: [/^language-[\w-]+$/], pre: [/^language-[\w-]+$/]}, allowedSchemes: ['http', 'https'], allowProtocolRelative: false, transformTags: {
            a: (_tag, attrs) => ({
                tagName: 'a', attribs: {
                    ...attrs, rel: 'noopener noreferrer'
                }
            })
        }
    });
    const outline: OutlineEntry[] = [];
    let n = 0;
    const result = clean.replace(/<h([2-4])>([\s\S]*?)<\/h\1>/gi, (_m, level: string, inner: string) => {
        const id = `sec-${++n}`;
        const text = sanitizeHtml(inner, {
            allowedTags: [], allowedAttributes: {}
        }).replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>');
        if (text.trim())
            outline.push({
                id, text: text.trim().slice(0, 80), level: Number(level)
            });
        return `<h${level} id="${id}">${inner}</h${level}>`;
    });
    return {
        html: result, outline
    };
}
