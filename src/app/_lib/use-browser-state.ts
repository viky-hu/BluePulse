"use client";

import { useEffect, useSyncExternalStore } from "react";
import { getBrowserState } from "./browser-state";

export function useBrowserState(mock = false) {
  const store = getBrowserState(mock);
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getServerSnapshot);
  useEffect(() => { store.hydrate(); }, [store]);
  return { state, store };
}
