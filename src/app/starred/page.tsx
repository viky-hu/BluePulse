import type { Metadata } from 'next';
import StarredPage from './StarredPage';
export const metadata: Metadata = { title: '我的收藏 | Pulse', description: '保存在当前浏览器上的 Pulse 收藏。', robots: { index: false, follow: false } };
export default function Page() { return <StarredPage />; }
