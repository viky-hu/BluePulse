import { InitialIntro } from "./_components/intro/InitialIntro";
import { getFeaturedWhitePapers } from "./_lib/featured";

export default async function Home() {
  const articles = await getFeaturedWhitePapers();
  return <InitialIntro articles={articles} />;
}
