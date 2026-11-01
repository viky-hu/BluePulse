// AIHOT nameplate geometry (MIT). Copyright (c) 2026 数字生命卡兹克.
const boxes = { daily: "0 -122.0 718.3 244.0", weekly: "0 -122.0 758.6 244.0", monthly: "0 -122.0 744.2 244.0", archive: "0 -122.0 1138.4 244.0" } as const;
export function Nameplate({ which, className = "" }: { which: keyof typeof boxes; className?: string }) { return <svg viewBox={boxes[which]} className={className} aria-hidden="true" focusable="false"><use href={`/daily/nameplates/${which}.svg#accent`} className="fill-accent" /><use href={`/daily/nameplates/${which}.svg#ink`} className="fill-ink" /></svg>; }
