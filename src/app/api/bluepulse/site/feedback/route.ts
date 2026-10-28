import { proxyFeedback } from "./_proxy";
export const dynamic = "force-dynamic";
export function POST(request: Request) {
  return proxyFeedback(request, { enabled: process.env.BLUEPULSE_FEEDBACK_ENABLED === "1", apiBase: process.env.BLUEPULSE_API_URL ?? "http://127.0.0.1:8000", trustProxy: process.env.BLUEPULSE_TRUST_PROXY === "1", publicOrigin: process.env.BLUEPULSE_SITE_ORIGIN });
}
