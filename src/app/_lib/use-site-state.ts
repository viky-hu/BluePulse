"use client";
import { useEffect, useSyncExternalStore } from "react";
import { getSiteState } from "./site-state";
export function useSiteState(mock = false) {
  const store = getSiteState(mock);
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getServerSnapshot);
  useEffect(() => { store.hydrate(); }, [store]);
  return { state, store };
}
