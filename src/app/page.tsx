import { InitialIntro } from "./_components/intro/InitialIntro";
import { MOCK_WHITE_PAPER_ARTICLES } from "./_components/intro/white-paper-data";
import { getFeaturedWhitePapers } from "./_lib/featured";

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ mock?: string | string[] }>;
}) {
  const params = await searchParams;
  const mock = params.mock === "1" || (Array.isArray(params.mock) && params.mock[0] === "1");
  const whitePapers = mock ? MOCK_WHITE_PAPER_ARTICLES : await getFeaturedWhitePapers();
  return <InitialIntro mockData={mock} whitePapers={whitePapers} />;
}
