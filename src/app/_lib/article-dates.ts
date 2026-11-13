export type ArticleDates = {
  published_at?: string | null;
  published_date?: string | null;
  first_seen_at?: string | null;
};

export function isCalendarDate(value?: string | null): value is string {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export function articlePublicationDate(article: ArticleDates) {
  if (article.published_at && Number.isFinite(Date.parse(article.published_at))) return article.published_at;
  return isCalendarDate(article.published_date) ? article.published_date : null;
}
