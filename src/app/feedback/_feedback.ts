// Screenshot rules adapted from AIHOT routes/feedback.tsx (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
export const MAX_IMAGE = 5 * 1024 * 1024;
export const MAX_TEXT = 2000;
type Screenshot = { type: string; name: string; size: number };
export function screenshotType(file: Pick<Screenshot, "type" | "name">): string {
  const type = file.type.trim().toLowerCase();
  if (type === "image/jpg") return "image/jpeg";
  if (type && type !== "application/octet-stream") return type;
  if (/\.png$/i.test(file.name)) return "image/png";
  if (/\.jpe?g$/i.test(file.name)) return "image/jpeg";
  if (/\.webp$/i.test(file.name)) return "image/webp";
  return type;
}
export function screenshotError(file: Screenshot): string | null {
  if (!/^image\/(png|jpeg|webp)$/.test(screenshotType(file))) return "截图需要是 PNG、JPEG 或 WebP。";
  if (file.size > MAX_IMAGE) return "截图原图不超过 5 MB。";
  return null;
}
export function safePageUrl(input: string, origin: string): string | null {
  const value = input.trim();
  if (!value) return "";
  if (value.length > 500 || /[\u0000-\u0020\\]/.test(value) || value.startsWith("//")) return null;
  try {
    const absolute = /^[a-z][a-z\d+.-]*:/i.test(value);
    const url = new URL(value, origin);
    if (!/^https?:$/.test(url.protocol) || url.username || url.password || (!absolute && url.origin !== origin)) return null;
    return absolute ? url.href : `${url.pathname}${url.search}${url.hash}`;
  } catch { return null; }
}
export function choosePageUrl(explicit: string | null, draft: string, previous: string | null, referrer: string, origin: string): string {
  const sameOriginReferrer = (() => { try { return new URL(referrer).origin === origin ? referrer : null; } catch { return null; } })();
  for (const value of [explicit, draft, previous, sameOriginReferrer]) {
    if (!value) continue;
    const safe = safePageUrl(value, origin);
    if (safe && new URL(safe, origin).pathname.replace(/\/$/, "") !== "/feedback") return safe;
  }
  return "";
}
export function receiptId(status: number, body: unknown): number | null {
  const id = body && typeof body === "object" ? (body as Record<string, unknown>).id : null;
  return status === 201 && typeof id === "number" && Number.isSafeInteger(id) && id > 0 ? id : null;
}
export function retryDeadline(value: string | null, now = Date.now()): number {
  if (!value || /^-/.test(value)) return 0;
  const deadline = /^\d+$/.test(value.trim()) ? now + Number(value) * 1000 : Date.parse(value);
  return Number.isFinite(deadline) && deadline > now ? deadline : 0;
}
export function submissionError(status: number, code?: unknown): string {
  if (code === "feedback_result_unknown") return "暂时无法确认反馈是否收到，请保留内容，避免连续重复发送。";
  switch (status) {
    case 400: return "反馈内容或附件未通过校验，请检查后重试。";
    case 403: return "当前请求未获允许，请刷新页面后重试。";
    case 413: return "提交的附件过大，请换一张较小的截图。";
    case 429: return "提交过于频繁，请稍后再试。";
    case 404: case 503: return "反馈接收暂不可用，请保留草稿，或通过关于页联系我们。";
    default: return "暂时无法确认反馈是否收到，请保留当前内容，稍后再试。";
  }
}
