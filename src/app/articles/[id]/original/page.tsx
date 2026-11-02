import { articleMetadata, renderArticle, type ArticleRouteProps } from "../../_reader/server";
export function generateMetadata(props: ArticleRouteProps) { return articleMetadata(props, "original"); }
export default function ArticleOriginalPage(props: ArticleRouteProps) { return renderArticle(props, "original"); }
