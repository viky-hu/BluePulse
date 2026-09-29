import { InitialIntro } from "./_components/intro/InitialIntro";

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ mock?: string | string[] }>;
}) {
  const params = await searchParams;
  const mock = params.mock === "1" || (Array.isArray(params.mock) && params.mock[0] === "1");
  return <InitialIntro mockData={mock} />;
}
