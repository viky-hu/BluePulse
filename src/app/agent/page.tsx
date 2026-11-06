import { AgentPage } from './AgentPage';
import { siteOrigin } from './_contract';
export const dynamic = 'force-dynamic';
export const metadata = { title: 'Agent 接入 · Pulse', description: '通过匿名只读 HTTP，在你的 Agent 中查询 Pulse 公开警务科技资讯。' };
export default function Page() { return <AgentPage origin={siteOrigin(process.env.BLUEPULSE_SITE_ORIGIN)} />; }
