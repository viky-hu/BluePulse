import type { Metadata } from "next";
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

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // URL-dependent shared layout is server-rendered for the first paint on every route.
  await connection();
  return (
    <html lang="zh-CN" className={googleSans.variable} suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: `try{var m=new URLSearchParams(location.search).get('mock')==='1';var entered=localStorage.getItem('blue-pulse-entry-complete-v1'+(m?':mock':''))==='1';document.documentElement.dataset.pulseEntry=location.pathname==='/'&&!entered?'intro':'stable'}catch(e){document.documentElement.dataset.pulseEntry=location.pathname==='/'?'intro':'stable'}` }} /></head>
      <body><Suspense><MainShell changelogVersion={changelog.latestVersion}>{children}</MainShell></Suspense></body>
    </html>
  );
}
