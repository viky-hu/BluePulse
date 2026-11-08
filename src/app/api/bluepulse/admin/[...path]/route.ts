import { proxyAdmin } from "../_proxy";

export const dynamic = "force-dynamic";

async function handle(request: Request, context: RouteContext<"/api/bluepulse/admin/[...path]">) {
  return proxyAdmin(request, (await context.params).path, {
    origin: process.env.BLUEPULSE_SITE_ORIGIN,
    apiBase: process.env.BLUEPULSE_API_URL ?? "http://127.0.0.1:8000",
    trustProxy: process.env.BLUEPULSE_TRUST_PROXY === "1",
  });
}

export { handle as GET, handle as POST, handle as PATCH, handle as DELETE };
