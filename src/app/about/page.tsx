import type { Metadata } from "next";
import { AboutPulse } from "./AboutPulse";

export const metadata: Metadata = { title: "关于 Pulse · Blue Pulse", description: "了解 Pulse 如何整理国内外公开警务科技资讯，以及青朗先锋实验小组。" };
export default function AboutPage() { return <AboutPulse />; }
