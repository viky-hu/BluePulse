// AIHOT lib/format.ts (MIT), with explicit unknown-time handling for legacy Pulse records.
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
export function fullDateTime(value: string | null | undefined) {
    if (!value || !Number.isFinite(Date.parse(value)))
        return "时间待核";
    return new Intl.DateTimeFormat("sv-SE", {
        timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23"
    }).format(new Date(value));
}
export function relativeTime(value: string | null | undefined, now = Date.now()) {
    if (!value || !Number.isFinite(Date.parse(value)))
        return "";
    const seconds = Math.max(0, Math.round((now - Date.parse(value)) / 1000));
    if (seconds < 60)
        return "刚刚";
    const minutes = Math.round(seconds / 60);
    if (minutes < 60)
        return `${minutes} 分钟前`;
    const hours = Math.round(minutes / 60);
    if (hours < 24)
        return `${hours} 小时前`;
    const days = Math.round(hours / 24);
    return days < 30 ? `${days} 天前` : fullDateTime(value).slice(0, 10);
}
export function hostOf(value: string) {
    try {
        return new URL(value).hostname.replace(/^www\./, "");
    }
    catch {
        return "";
    }
}
export function isCompactReader(width: number, rem = 16) { return width < 56 * rem; }
