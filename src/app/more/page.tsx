import type { Metadata } from "next";
import { changelog } from "../_lib/site-changelog";
import { MorePage } from "./MorePage";

export const metadata: Metadata = { title: "更多 · Pulse", description: "本浏览器的收藏、阅读记录及 Pulse 工具入口。", robots: { index: false } };
export default function MoreRoute() { return <MorePage changelogVersion={changelog.latestVersion} />; }
