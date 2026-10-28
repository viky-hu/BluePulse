import type { Metadata } from "next";
import { changelog } from "../_lib/site-changelog";
import { Changelog } from "./Changelog";
export const metadata: Metadata = { title: "更新日志 · Pulse", description: "Pulse 的功能更新、优化、公告与下线记录。" };
export default function ChangelogPage() { return <Changelog data={changelog} />; }
