// Draft lifecycle adapted from AIHOT routes/feedback.tsx and lib/local-state.ts (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
export type FeedbackDraft = { content: string; email: string; pageUrl: string };
type DraftStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
export type DraftIssue = "malformed" | "unavailable" | null;
const memory = new Map<string, FeedbackDraft | null>();
const pending = new Set<string>();
export const emptyDraft = (): FeedbackDraft => ({ content: "", email: "", pageUrl: "" });
export const draftKey = (mock: boolean) => `bluepulse:feedback-draft:v1:${mock ? "mock" : "live"}`;

export function parseDraft(value: unknown): FeedbackDraft | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const draft = value as Record<string, unknown>;
  if (typeof draft.content !== "string" || draft.content.length > 2000 || typeof draft.email !== "string" || draft.email.length > 200 || typeof draft.pageUrl !== "string" || draft.pageUrl.length > 500) return null;
  return { content: draft.content, email: draft.email, pageUrl: draft.pageUrl };
}

export function createDraftStore(mock: boolean, getStorage: () => DraftStorage = () => window.localStorage) {
  const key = draftKey(mock);
  function inspect(): { stored: FeedbackDraft | null; issue: DraftIssue } {
    try {
      const raw = getStorage().getItem(key);
      if (raw === null) return { stored: null, issue: null };
      try {
        const stored = parseDraft(JSON.parse(raw));
        return { stored, issue: stored ? null : "malformed" };
      } catch { return { stored: null, issue: "malformed" }; }
    } catch { return { stored: null, issue: "unavailable" }; }
  }
  return {
    read() {
      const { stored, issue } = inspect();
      return { draft: (issue || pending.has(key)) && memory.has(key) ? memory.get(key)! : stored, issue: pending.has(key) && !issue ? "unavailable" as const : issue };
    },
    write(draft: FeedbackDraft) {
      if (!parseDraft(draft)) return false;
      memory.set(key, { ...draft });
      pending.add(key);
      if (inspect().issue) return false;
      try { getStorage().setItem(key, JSON.stringify(draft)); pending.delete(key); return true; } catch { return false; }
    },
    clear() {
      memory.set(key, null);
      pending.add(key);
      if (inspect().issue === "malformed") return false;
      try { getStorage().removeItem(key); pending.delete(key); return true; } catch { return false; }
    },
  };
}
