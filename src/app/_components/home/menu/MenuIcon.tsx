// Adapted from AIHOT apps/web/app/components/icons.tsx (MIT). See THIRD_PARTY_NOTICES.md.
import type { ReactNode } from "react";
import type { MenuIcon as IconName } from "../navigation-config";

const shapes: Record<IconName | "search", ReactNode> = {
  bolt: <path d="M13 2.5L4.5 13.5H11l-1 8L19.5 10.5H13z" />,
  list: <><path d="M8 6h13M8 12h13M8 18h13" /><circle cx="3.5" cy="6" r="1" /><circle cx="3.5" cy="12" r="1" /><circle cx="3.5" cy="18" r="1" /></>,
  flame: <path d="M12 22c4 0 7-2.7 7-7 0-3.6-2.4-6.2-4-8-.5 2-1.6 3.4-3 4 .3-3-1-6-4-8 0 4-4 6.5-4 11 0 4.3 3 8 8 8z" />,
  doc: <><rect x="5" y="3.5" width="14" height="17" rx="2" /><path d="M8.5 8h7M8.5 12h7M8.5 16h4" /></>,
  grid: <><rect x="3.5" y="3.5" width="7" height="7" rx="1.5" /><rect x="13.5" y="3.5" width="7" height="7" rx="1.5" /><rect x="3.5" y="13.5" width="7" height="7" rx="1.5" /><rect x="13.5" y="13.5" width="7" height="7" rx="1.5" /></>,
  plug: <path d="M9 3v5M15 3v5M7 8h10v3a5 5 0 01-10 0zM12 16v5" />,
  heart: <path d="M12 20s-7.5-4.6-7.5-10.2A4.3 4.3 0 0112 7.3a4.3 4.3 0 017.5 2.5C19.5 15.4 12 20 12 20z" />,
  history: <><path d="M3.5 12a8.5 8.5 0 102.5-6" /><path d="M3.5 4v4h4" /><path d="M12 8v4l2.5 2" /></>,
  message: <path d="M4 5h16v11H9l-5 4z" />,
  search: <><circle cx="11" cy="11" r="6.5" /><path d="M20 20l-4.2-4.2" /></>,
};

export function MenuIcon({ name }: { name: IconName | "search" }) {
  return <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{shapes[name]}</svg>;
}
