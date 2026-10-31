import { notFound } from "next/navigation";
import { RouteReady } from "../../_components/home/MainShell";
import { PUBLIC_ID } from "../../_components/featured/_data";
import styles from "../../_components/home/section-page.module.css";

export default async function StoryPage({ params }: { params: Promise<{ publicId: string }> }) {
  const { publicId } = await params;
  if (!PUBLIC_ID.test(publicId)) notFound();
  return <div className={styles.page}><RouteReady /><header className={styles.header}><h1>事件详情</h1><p>追踪国内外警务科技事件及其直接进展。</p></header><p className={styles.status} role="status">事件详情正在建设中，事件与证据服务尚未接入。</p></div>;
}
