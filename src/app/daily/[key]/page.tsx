import { notFound } from "next/navigation";
import { DailyPage } from "../DailyPage";
import { isDailyDate } from "../_route";
export const metadata = { title: "AI日报 · Pulse" };
export default async function Page({ params }: { params: Promise<{ key: string }> }) {
  if (!isDailyDate((await params).key)) notFound();
  return <DailyPage />;
}
