import type { Metadata } from "next";
import { HotPage } from "./HotPage";
export const metadata: Metadata = { title: "热点榜 | Blue Pulse", description: "过去48小时，智慧警务科技领域讨论最多的10件事：热度指数、趋势与组成热度的公开来源。" };
export default function Page() { return <HotPage />; }
