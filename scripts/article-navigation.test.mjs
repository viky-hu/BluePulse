import assert from "node:assert/strict";
import { test } from "node:test";
import { parseHomeRoute, buildHomeHref } from "../src/app/_components/home/home-routes.ts";
import { allArticleParams } from "../src/app/all/_data.ts";
const readerFormat = await import("../src/app/articles/_reader/format.ts");

const id = "11111111-1111-4111-8111-111111111111";
test("original article URLs retain the article identity and reject extra segments", () => {
  const route = parseHomeRoute(`/articles/${id}/original`, "mock=1");
  assert.equal(route.kind, "article");
  assert.equal(route.valid, true);
  assert.equal(route.articleId, id);
  assert.equal(parseHomeRoute(`/articles/${id}/original/extra`, "").valid, false);
  assert.equal(parseHomeRoute("/articles/invalid/original", "").valid, false);
});
test("article tag links round trip as exact filters, independently from full-text search", () => {
  const filters = parseHomeRoute("/all", "tag=警务智能体&q=公开测试&region=domestic").filters;
  assert.equal(filters.tag, "警务智能体");
  const href = buildHomeHref("/all", filters);
  assert.equal(new URL(href, "https://pulse.local").searchParams.get("tag"), "警务智能体");
  const params = allArticleParams(filters, null);
  assert.equal(params.get("tag"), "警务智能体");
  assert.equal(params.get("q"), "公开测试");
});
test("compact reading uses the actual content width and root rem size", () => {
  assert.equal(typeof readerFormat.isCompactReader, "function");
  assert.equal(readerFormat.isCompactReader(840, 16), true);
  assert.equal(readerFormat.isCompactReader(896, 16), false);
  assert.equal(readerFormat.isCompactReader(1000, 20), true);
});
