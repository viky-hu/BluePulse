import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const microsoftRounded = localFont({
  src: "../../微软简中圆.ttf",
  variable: "--font-microsoft-rounded",
  display: "swap",
  adjustFontFallback: false,
  style: "normal",
  weight: "400",
});

export const metadata: Metadata = {
  title: "Blue Pulse",
  description: "国内外警务科技情报系统",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="zh-CN">
      <body className={microsoftRounded.variable}>{children}</body>
    </html>
  );
}
