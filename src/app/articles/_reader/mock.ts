// Explicit fixtures only. AIHOT reading-body semantics adapted to police technology examples.
import { mockArticle, MOCK_TAXONOMY } from '../_mock';
export const mockReaderTaxonomy = MOCK_TAXONOMY.items;
import type { ArticleReader } from './types';
export const READER_DEMO_ID = '4ed2a8d4-efb7-4ce6-8a43-4ee36f27d001';
export const READER_SUMMARY_ID = '4ed2a8d4-efb7-4ce6-8a43-4ee36f27d002';
export function mockReaderArticle(id: string, language: 'zh' | 'original' = 'zh') {
    const article = mockArticle(id);
    if (!article)
        return null;
    const summary = id === READER_SUMMARY_ID;
    const sections = ['公开试点与应用边界', '数据质量与现场验证', '人工复核与审计记录', '跨部门协同流程', '部署条件与后续观察'];
    const zh = sections.map((title, i) => `<h2>${title}</h2><p>警务科技系统的公开评估应以可核查证据为基础。这是独立的演示数据，不代表真实部署效果。第${i + 1}阶段关注现场条件、样本范围和责任分工。</p><p>工作人员保留人工判断和复核通道，记录每次检索的用途、访问范围及结果。技术团队根据反馈持续调整流程，并对信息来源进行核验。</p><h3>观察与核验</h3><ul><li>记录样本范围与更新时间。</li><li>区分技术能力和实际业务效果。</li></ul>`).join('') + '<h2>评估指标</h2><table><thead><tr><th>环节</th><th>核验要求</th></tr></thead><tbody><tr><td>信息检索</td><td>来源可追溯</td></tr><tr><td>人工复核</td><td>结论有记录</td></tr></tbody></table><pre><code class="language-json">{ &quot;reviewRequired&quot;: true, &quot;mode&quot;: &quot;demo&quot; }</code></pre><figure><img src="/logo.svg" alt="青朗先锋标识演示图"><figcaption>本地演示图片</figcaption></figure>';
    const original = '<h2>Public evaluation</h2><p>This is an explicit demonstration of a police technology research reader. It does not describe a verified deployment.</p><h2>Evidence and human review</h2><p>Maintain traceable sources, documented review and clear operating limits.</p><pre><code class="language-json">{ &quot;reviewRequired&quot;: true }</code></pre>';
    const reader: ArticleReader = {
        readingMode: summary ? 'summary-only' : 'full', body: summary ? null : {
            zh: language === 'zh' ? zh : null, original: language === 'original' ? original : null, zhKind: 'translation', complete: true
        }, bodyLanguage: language, hasTranslation: !summary, outline: [], reason: summary ? null : '演示：关注公开证据、应用边界与人工复核。', selected: !summary, sameEvent: null, group: null, story: null, relatedStories: [], tags: summary ? [] : ['人工复核', '公开评估'], channel: 'news', x: null, indexable: false, markdownAvailable: !summary
    };
    return {
        ...article, importance_score: article.importance_score > 0 && article.importance_score < 1 ? Math.round(article.importance_score * 100) : article.importance_score, reader
    };
}
