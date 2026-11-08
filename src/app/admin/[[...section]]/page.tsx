import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { RouteReady } from "../../_components/home/MainShell";
import { AdminConsole } from "../AdminConsole";
import { adminSections, type AdminSection } from "../sections";

export const metadata: Metadata = {
  title: "管理后台 · Blue Pulse",
  robots: { index: false, follow: false },
};

export default async function AdminPage({ params }: PageProps<"/admin/[[...section]]">) {
  const { section = [] } = await params;
  const selected = section[0] ?? "runs";
  if (section.length > 1 || !Object.hasOwn(adminSections, selected)) notFound();
  return <><RouteReady /><AdminConsole section={selected as AdminSection} /></>;
}
