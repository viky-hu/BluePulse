import type { Metadata } from "next";
import { FeedbackForm } from "./FeedbackForm";

export const metadata: Metadata = { title: "意见反馈 · Blue Pulse", description: "告诉 Pulse 哪里可以做得更好：内容、功能、来源更正或下架请求。", robots: { index: false, follow: false } };
export default function FeedbackPage() { return <FeedbackForm receivingEnabled={process.env.BLUEPULSE_FEEDBACK_ENABLED === "1"} />; }
