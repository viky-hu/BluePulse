import { articleMetadata, renderArticle, type ArticleRouteProps } from "../_reader/server";
export function generateMetadata(props: ArticleRouteProps) { return articleMetadata(props, "zh"); }
export default function ArticleDetailPage(props: ArticleRouteProps) { return renderArticle(props, "zh"); }
