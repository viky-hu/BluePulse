import type { Metadata } from "next";
import { DailyPage } from "./DailyPage";

export const metadata: Metadata = { title: "AI日报 · Pulse" };

export default function DailyLayout({ children }: LayoutProps<"/daily">) {
  return <><DailyPage />{children}</>;
}
