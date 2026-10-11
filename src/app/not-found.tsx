import Link from "next/link";
import { RouteReady } from "./_components/home/MainShell";
export default function NotFound() { return <><RouteReady /><p>没有找到这个页面。</p><Link href="/">返回精选</Link></>; }
