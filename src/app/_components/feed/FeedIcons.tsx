// AIHOT components/icons.tsx (MIT), Copyright (c) 2026 数字生命卡兹克.
export function FeedIcon({ name, filled = false }: { name: "search" | "close" | "bookmark" | "next" | "down" | "external" | "left" | "right"; filled?: boolean }) {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {name === "search" ? <><circle cx="11" cy="11" r="6.5" /><path d="M20 20l-4.2-4.2" /></> : name === "close" ? <path d="M6 6l12 12M18 6L6 18" /> : name === "bookmark" ? <path d="M6 3.5h12v17l-6-4-6 4z" fill={filled ? "currentColor" : "none"} /> : name === "down" ? <path d="M6 9l6 6 6-6" /> : name === "external" ? <path d="M7 17L17 7M8 7h9v9" /> : name === "left" ? <path d="M19 12H5M11 18l-6-6 6-6" /> : name === "right" ? <path d="M5 12h14M13 6l6 6-6 6" /> : <path d="M9 5l7 7-7 7" />}
  </svg>;
}
