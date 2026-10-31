import { RootEntry } from "./_components/home/RootEntry";
import { redirect } from "next/navigation";
import { FeaturedFeed } from "./_components/featured/FeaturedFeed";
import { MOCK_WHITE_PAPER_ARTICLES } from "./_components/intro/white-paper-data";
import { getFeaturedWhitePapers } from "./_lib/featured";

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const query = Array.isArray(params.q) ? params.q[0] : params.q;
  if (query?.trim()) {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) for (const item of Array.isArray(value) ? value : value === undefined ? [] : [value]) search.append(key, item);
    redirect(`/all?${search}`);
  }
  const mock = params.mock === "1" || (Array.isArray(params.mock) && params.mock[0] === "1");
  const whitePapers = mock ? MOCK_WHITE_PAPER_ARTICLES : await getFeaturedWhitePapers();
  return <><RootEntry whitePapers={whitePapers} /><FeaturedFeed /></>;
}
