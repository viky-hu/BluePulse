"use client";
import { createPortal } from "react-dom";
import { InitialIntro } from "../intro/InitialIntro";
import type { WhitePaperArticle } from "../intro/white-paper-data";
import { useMainShell } from "./MainShell";

export function RootEntry({ whitePapers }: { whitePapers: WhitePaperArticle[] }) {
  const shell = useMainShell();
  return shell.entry === "intro" && shell.introHost
    ? createPortal(<InitialIntro whitePapers={whitePapers} onMainReady={shell.introFinished} />, shell.introHost)
    : null;
}
