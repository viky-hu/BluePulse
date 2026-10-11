import { RouteReady } from "./_components/home/MainShell";
export default function Loading() { return <><RouteReady ready={false} /><p role="status">正在载入内容…</p></>; }
