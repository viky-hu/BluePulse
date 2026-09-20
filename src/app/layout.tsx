import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Blue Pulse",
  description: "Blue Pulse logo animation",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
