import type { Metadata } from "next";
import localFont from "next/font/local";
import "cn-fontsource-ding-talk-jin-bu-ti-regular/font.css";
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

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="zh-CN" className={googleSans.variable}>
      <body>{children}</body>
    </html>
  );
}
