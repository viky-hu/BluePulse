// Adapted from AIHOT icons.tsx (MIT), Copyright (c) 2026 数字生命卡兹克.
export function StarredIcon({ name, size = 14 }: { name: 'bookmark' | 'download' | 'close'; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{name === 'bookmark' ? <path d="M6 3.5h12v17l-6-4-6 4z" /> : name === 'download' ? <path d="M12 4v11M7 10l5 5 5-5M5 20h14" /> : <path d="M6 6l12 12M18 6L6 18" />}</svg>;
}
