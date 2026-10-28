"use client";

import { useEffect, useLayoutEffect, useRef, useTransition } from "react";
import { useRouter } from "next/navigation";

/** One refresh owns one transition. Unmounting abandons its pending UI when navigation supersedes it. */
export function RouteRefresh({ id, onComplete }: { id: number; onComplete: (id: number) => void }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const started = useRef(false), observedPending = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    startTransition(() => router.refresh());
  }, [router]);
  useLayoutEffect(() => {
    if (pending) observedPending.current = true;
    else if (observedPending.current) onComplete(id);
  }, [pending, id, onComplete]);
  return null;
}
