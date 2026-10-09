export type TransitionPhase = "idle" | "exiting" | "entering";
export type NavigationRequest<T> = { key: string; view: T; commit?: () => void };
export type NavigationState<T> = {
  phase: TransitionPhase;
  currentKey: string;
  pending: NavigationRequest<T> | null;
};
export type NavigationStep<T> = { state: NavigationState<T>; commit?: NavigationRequest<T> };

export function requestNavigation<T>(
  state: NavigationState<T>, request: NavigationRequest<T>, reducedMotion = false,
): NavigationStep<T> {
  if (reducedMotion) {
    return {
      state: { phase: "idle", currentKey: request.key, pending: null },
      ...(request.key !== state.currentKey ? { commit: request } : {}),
    };
  }
  if (state.phase === "idle" && request.key === state.currentKey) return { state };
  return { state: {
    ...state,
    phase: state.phase === "idle" ? "exiting" : state.phase,
    pending: state.phase === "entering" && request.key === state.currentKey ? null : request,
  } };
}

export function finishExit<T>(state: NavigationState<T>): NavigationStep<T> {
  if (state.phase !== "exiting" || !state.pending) return { state };
  const target = state.pending;
  return {
    state: { phase: "entering", currentKey: target.key, pending: null },
    ...(target.key !== state.currentKey ? { commit: target } : {}),
  };
}

export function finishEnter<T>(state: NavigationState<T>): NavigationStep<T> {
  if (state.phase !== "entering") return { state };
  return { state: { ...state, phase: state.pending ? "exiting" : "idle" } };
}
