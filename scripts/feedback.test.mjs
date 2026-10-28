import assert from 'node:assert/strict';
import test from 'node:test';
import { createDraftStore, draftKey, parseDraft } from '../src/app/feedback/_draft.ts';
import { choosePageUrl, safePageUrl, screenshotType, screenshotError, receiptId, retryDeadline, submissionError } from '../src/app/feedback/_feedback.ts';

test('an upstream unknown result stays uncertain even when the proxy returns 503', () => {
  assert.match(submissionError(503, 'feedback_result_unknown'), /无法确认/);
  assert.match(submissionError(503, 'feedback_not_connected'), /暂不可用/);
});

const draft = { content: '文章的来源链接打不开', email: '', pageUrl: '/articles/42' };
function storage() {
  const data = new Map();
  return { data, getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value), removeItem: key => data.delete(key) };
}
test('draft accepts bounded strings without coercing unknown fields', () => {
  assert.deepEqual(parseDraft(draft), draft);
  assert.equal(parseDraft({ ...draft, content: 42 }), null);
  assert.equal(parseDraft({ ...draft, content: 'x'.repeat(2001) }), null);
  assert.equal(parseDraft({ ...draft, email: 'x'.repeat(255) }), null);
  assert.equal(parseDraft({ ...draft, pageUrl: 'x'.repeat(2049) }), null);
});
test('normal and demo drafts remain separate and clear after confirmed success', () => {
  const s = storage();
  const live = createDraftStore(false, () => s), demo = createDraftStore(true, () => s);
  live.clear(); demo.clear();
  assert.equal(live.write(draft), true);
  assert.deepEqual(live.read().draft, draft);
  assert.equal(demo.read().draft, null);
  assert.notEqual(draftKey(false), draftKey(true));
  assert.equal(live.clear(), true);
  assert.equal(createDraftStore(false, () => s).read().draft, null);
});
test('malformed stored draft is preserved while edits have memory fallback', () => {
  const s = storage(); s.setItem(draftKey(false), '{broken');
  const store = createDraftStore(false, () => s);
  assert.equal(store.read().issue, 'malformed');
  assert.equal(store.write(draft), false);
  assert.equal(s.getItem(draftKey(false)), '{broken');
  assert.deepEqual(createDraftStore(false, () => s).read().draft, draft);
  store.clear();
});
test('denied localStorage keeps SPA draft but reports unavailable', () => {
  const denied = () => { throw Error('denied'); };
  const store = createDraftStore(true, denied);
  assert.equal(store.write(draft), false);
  const restored = createDraftStore(true, denied).read();
  assert.deepEqual(restored.draft, draft);
  assert.equal(restored.issue, 'unavailable');
  store.clear();
});
test('quota failure returns the edited memory draft instead of the older stored version', () => {
  const s = storage();
  const store = createDraftStore(false, () => s);
  store.clear(); store.write(draft);
  const changed = { ...draft, content: '这是最新的修改，不能被旧草稿覆盖' };
  s.setItem = () => { throw Error('quota'); };
  assert.equal(store.write(changed), false);
  assert.deepEqual(createDraftStore(false, () => s).read().draft, changed);
  assert.equal(store.read().issue, 'unavailable');
  store.clear();
});
test('source URL precedence uses explicit source then draft then prior page', () => {
  const origin = 'https://pulse.test';
  assert.equal(choosePageUrl('/search?q=test', '/articles/1', '/pool', '/about', origin), '/search?q=test');
  assert.equal(choosePageUrl('javascript:alert(1)', '/articles/1', '/pool', '/about', origin), '/articles/1');
  assert.equal(choosePageUrl(null, '', '/feedback?mock=1', 'https://pulse.test/about', origin), 'https://pulse.test/about');
  assert.equal(choosePageUrl(null, '', null, 'https://external.test/a', origin), '');
});
test('page URLs reject executable and cross-origin relative inputs', () => {
  for (const input of ['javascript:alert(1)', 'data:text/html,x', '//evil.test/a', '\\evil.test/a', '/x\ny']) assert.equal(safePageUrl(input, 'https://pulse.test'), null);
  assert.equal(safePageUrl('/articles/1', 'https://pulse.test'), '/articles/1');
  assert.equal(safePageUrl('https://source.test/a', 'https://pulse.test'), 'https://source.test/a');
});
test('screenshots normalize phone JPEG and validate original file size', () => {
  assert.equal(screenshotType({ name: 'capture.jpg', type: 'image/jpg' }), 'image/jpeg');
  assert.equal(screenshotType({ name: 'capture.PNG', type: '' }), 'image/png');
  assert.equal(screenshotType({ name: 'capture.webp', type: 'application/octet-stream' }), 'image/webp');
  assert.equal(screenshotError({ name: 'capture.png', type: 'image/png', size: 5 * 1024 * 1024 }), null);
  assert.match(screenshotError({ name: 'capture.png', type: 'image/png', size: 5 * 1024 * 1024 + 1 }), /5 MB/);
  assert.match(screenshotError({ name: 'capture.svg', type: 'image/svg+xml', size: 10 }), /PNG/);
});
test('only a 201 positive integer receipt confirms submission', () => {
  assert.equal(receiptId(201, { id: 42 }), 42);
  for (const id of [0, -1, 1.2, '42', NaN]) assert.equal(receiptId(201, { id }), null);
  assert.equal(receiptId(200, { id: 42 }), null);
});
test('Retry-After honors seconds and HTTP date', () => {
  const now = Date.parse('2026-10-28T00:00:00Z');
  assert.equal(retryDeadline('30', now), now + 30000);
  assert.equal(retryDeadline('Wed, 28 Oct 2026 00:01:00 GMT', now), now + 60000);
  assert.equal(retryDeadline('invalid', now), 0);
  assert.equal(retryDeadline('-1', now), 0);
});
