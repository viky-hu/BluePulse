import { notFound, permanentRedirect } from "next/navigation";
import Link from "next/link";
import { RouteReady } from "../../_components/home/MainShell";
import { ARTICLE_ID_PATTERN } from "../../_components/home/home-routes";
import { StoryView } from "./StoryView";
import type { StoryDetail } from "./story-data";
import styles from "./story.module.css";

async function loadStory(id: string) {
  const base = (process.env.BLUEPULSE_API_URL ?? "http://127.0.0.1:8000").trim().replace(/\/+$/, "");
  try {
    const response = await fetch(`${base}/api/v1/site/stories/${id}`, {
      cache: "no-store", redirect: "manual", signal: AbortSignal.timeout(6000),
    });
    if (response.status === 308) {
      const target = response.headers.get("Location")?.replace(/^\/story\//, "") ?? "";
      return ARTICLE_ID_PATTERN.test(target) ? { redirect: `/story/${target}` } : {};
    }
    if (!response.ok) return { status: response.status };
    const story = await response.json() as StoryDetail;
    return story.publicId === id && story.title && Array.isArray(story.timeline) ? { story } : {};
  } catch {
    return {};
  }
}

export default async function StoryPage({ params }: { params: Promise<{ publicId: string }> }) {
  const { publicId } = await params;
  if (!ARTICLE_ID_PATTERN.test(publicId)) notFound();
  const result = await loadStory(publicId.toLowerCase());
  if (result.redirect) permanentRedirect(result.redirect);
  if (result.status === 404) notFound();
  if (result.story) return <StoryView key={result.story.publicId} story={result.story} />;
  return <div className={styles.page}><RouteReady />
    <header className={styles.hero}><h1>事件详情</h1></header>
    <p className={styles.empty} role="status">暂时无法读取事件详情。请稍后刷新，或<Link href="/hot">返回热点榜</Link>。</p>
  </div>;
}
