"use client";
import { RouteReady } from "./_components/home/MainShell";
export default function ErrorPage({ reset }: { reset: () => void }) { return <><RouteReady /><p role="alert">内容暂时无法载入。</p><button onClick={reset}>重新载入</button></>; }
