import { proxyAgent } from '../_proxy';
export const dynamic = 'force-dynamic';
export function GET(request: Request) { return proxyAgent(request, '/search', process.env.BLUEPULSE_API_URL ?? 'http://127.0.0.1:8000'); }
