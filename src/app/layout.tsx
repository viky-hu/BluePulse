import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { Suspense } from "react";
import { connection } from "next/server";
import { MainShell } from "./_components/home/MainShell";
import { changelog } from "./_lib/site-changelog";
import "./globals.css";

const googleSans = localFont({
  src: "./fonts/GoogleSans-Variable.woff2",
  variable: "--font-google-sans",
  display: "swap",
  style: "normal",
  weight: "400 700",
});

export const metadata: Metadata = {
  title: "Blue Pulse",
  description: "国内外警务科技情报系统",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover" };

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // URL-dependent shared layout is server-rendered for the first paint on every route.
  await connection();
  return (
    <html lang="zh-CN" className={googleSans.variable} suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: `var p=new URLSearchParams(location.search),mobile=matchMedia('(max-width: 768px)').matches,entered=false;try{entered=localStorage.getItem('blue-pulse-entry-complete-v1'+(p.get('mock')==='1'?':mock':''))==='1'}catch(e){}document.documentElement.dataset.pulseEntry=location.pathname==='/'&&(p.get('intro')==='1'||(!mobile&&!entered))?'intro':'stable'` }} /></head>
      <body><Suspense><MainShell changelogVersion={changelog.latestVersion}>{children}</MainShell></Suspense></body>
    </html>
  );
}
