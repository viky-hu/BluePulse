"use client";

// Form, attachment controls and reading hierarchy adapted from AIHOT routes/feedback.tsx (MIT).
// Copyright (c) 2026 数字生命卡兹克. See THIRD_PARTY_NOTICES.md.
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { RouteReady, useMainShell } from "../_components/home/MainShell";
import { ReadingAsideCard, ReadingLayout } from "../_components/reading/ReadingLayout";
import { lastPage } from "../_lib/site-state";
import { createDraftStore, emptyDraft, type FeedbackDraft } from "./_draft";
import { choosePageUrl, MAX_TEXT, receiptId, retryDeadline, safePageUrl, screenshotError, screenshotType, submissionError } from "./_feedback";
import styles from "./feedback.module.css";

type State = { kind: "idle" | "sending" | "error" | "done"; message?: string; id?: number };
type Shot = { file: File; url: string };
const TIPS = ["出问题的页面或文章链接", "你看到了什么，原本想做什么", "有截图更好，记得先遮盖敏感信息"];

function FeedbackAside() {
  return <>
    <ReadingAsideCard title="写清楚这几点，处理更快"><ol className={styles.tips}>{TIPS.map((tip, index) => <li key={tip}><span>{String(index + 1).padStart(2, "0")}</span><span>{tip}</span></li>)}</ol></ReadingAsideCard>
    <ReadingAsideCard title="来源方"><p>如果你是来源方，希望更正、下架或调整展示方式，写明对应的文章链接和你的诉求即可。</p></ReadingAsideCard>
  </>;
}

export function FeedbackForm({ receivingEnabled }: { receivingEnabled: boolean }) {
  const { mock } = useMainShell();
  const from = useSearchParams().get("from");
  return <FeedbackEditor key={`${mock}:${from ?? ""}`} mock={mock} from={from} receivingEnabled={receivingEnabled} />;
}

function FeedbackEditor({ mock, from, receivingEnabled }: { mock: boolean; from: string | null; receivingEnabled: boolean }) {
  const { href } = useMainShell();
  const [draft, setDraft] = useState<FeedbackDraft>(emptyDraft);
  const [hydrated, setHydrated] = useState(false);
  const [saved, setSaved] = useState<"initial" | "saving" | "local" | "memory" | "malformed">("initial");
  const [shot, setShot] = useState<Shot | null>(null);
  const [state, setState] = useState<State>({ kind: "idle" });
  const [dragging, setDragging] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);
  const store = useRef<ReturnType<typeof createDraftStore> | null>(null);
  const currentDraft = useRef<FeedbackDraft>(emptyDraft());
  const ready = useRef(false), successful = useRef(false), submitting = useRef(false), mounted = useRef(false);
  const autosave = useRef<ReturnType<typeof setTimeout> | null>(null);
  const controller = useRef<AbortController | null>(null);
  const retryAt = useRef(0);

  useEffect(() => {
    mounted.current = true;
    store.current = createDraftStore(mock);
    const restored = store.current.read();
    const initial = restored.draft ?? emptyDraft();
    initial.pageUrl = choosePageUrl(from, initial.pageUrl, lastPage(mock), document.referrer, location.origin);
    currentDraft.current = initial;
    ready.current = true;
    setDraft(initial);
    setSaved(restored.issue === "malformed" ? "malformed" : restored.issue ? "memory" : "initial");
    setHydrated(true);
    const flush = () => {
      if (autosave.current) clearTimeout(autosave.current);
      if (ready.current && !successful.current) store.current?.write(currentDraft.current);
    };
    window.addEventListener("pagehide", flush);
    return () => {
      mounted.current = false;
      flush(); ready.current = false;
      controller.current?.abort();
      window.removeEventListener("pagehide", flush);
    };
  }, [mock, from]);

  useEffect(() => {
    if (!hydrated || successful.current) return;
    autosave.current = setTimeout(() => {
      if (successful.current) return;
      const result = store.current?.write(currentDraft.current);
      setSaved(result ? "local" : store.current?.read().issue === "malformed" ? "malformed" : "memory");
    }, 400);
    return () => { if (autosave.current) clearTimeout(autosave.current); };
  }, [draft, hydrated]);

  useEffect(() => {
    if (!shot) return;
    return () => URL.revokeObjectURL(shot.url);
  }, [shot]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setInterval(() => setCooldown(Math.max(0, Math.ceil((retryAt.current - Date.now()) / 1000))), 1000);
    return () => clearInterval(timer);
  }, [cooldown]);

  const edit = (field: keyof FeedbackDraft, value: string) => {
    if (submitting.current || !ready.current) return;
    const next = { ...currentDraft.current, [field]: value };
    currentDraft.current = next; setDraft(next);
    setSaved(previous => previous === "malformed" || previous === "memory" ? previous : "saving");
    if (state.kind === "error") setState({ kind: "idle" });
  };

  const pick = (picked?: File | null) => {
    if (!picked || submitting.current || !ready.current) return;
    const error = screenshotError(picked);
    if (error) { setState({ kind: "error", message: error }); return; }
    const type = screenshotType(picked);
    const file = picked.type === type ? picked : new File([picked], picked.name, { type });
    setShot({ file, url: URL.createObjectURL(file) }); setState({ kind: "idle" });
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting.current || successful.current || !ready.current || (!mock && !receivingEnabled) || Date.now() < retryAt.current) return;
    if (currentDraft.current.content.trim().length < 2) { setState({ kind: "error", message: "请至少写下两个字的反馈内容。" }); return; }
    const pageUrl = safePageUrl(currentDraft.current.pageUrl, location.origin);
    if (pageUrl === null) { setState({ kind: "error", message: "关联页面请填写有效的 http(s) 链接或本站相对路径。" }); return; }
    submitting.current = true; setState({ kind: "sending" });
    store.current?.write(currentDraft.current);
    const request = new AbortController(); controller.current = request;
    const timeout = setTimeout(() => request.abort(), 15000);
    try {
      let id: number | null;
      if (mock) {
        await new Promise<void>((resolve, reject) => {
          const finish = () => { request.signal.removeEventListener("abort", abort); resolve(); };
          const timer = setTimeout(finish, 250);
          const abort = () => { clearTimeout(timer); request.signal.removeEventListener("abort", abort); reject(new Error("aborted")); };
          request.signal.addEventListener("abort", abort, { once: true });
        });
        id = 10001;
      } else {
        const form = new FormData();
        form.set("content", currentDraft.current.content);
        form.set("email", currentDraft.current.email);
        form.set("pageUrl", pageUrl);
        if (shot) form.set("screenshot", shot.file);
        const response = await fetch("/api/bluepulse/site/feedback", { method: "POST", body: form, signal: request.signal });
        const body: unknown = await response.json().catch(() => null);
        if (!mounted.current) return;
        const deadline = retryDeadline(response.headers.get("Retry-After"));
        if (deadline) { retryAt.current = deadline; setCooldown(Math.ceil((deadline - Date.now()) / 1000)); }
        id = receiptId(response.status, body);
        if (id === null) {
          const code = body && typeof body === "object" && "error" in body && body.error && typeof body.error === "object" && "code" in body.error ? body.error.code : null;
          const requestId = body && typeof body === "object" && "error" in body && body.error && typeof body.error === "object" && "request_id" in body.error && typeof body.error.request_id === "string" ? body.error.request_id.slice(0, 100) : null;
          setState({ kind: "error", message: `${submissionError(response.status, code)}${requestId ? `（请求编号：${requestId}）` : ""}` }); return;
        }
      }
      if (!mounted.current) return;
      successful.current = true;
      if (autosave.current) clearTimeout(autosave.current);
      const cleared = store.current?.clear();
      currentDraft.current = emptyDraft(); setDraft(emptyDraft()); setShot(null);
      setState({ kind: "done", id, message: cleared ? undefined : mock ? "浏览器未允许清除原有演示草稿；演示未向服务器发送。" : "浏览器未允许清除原有本地草稿；本次反馈已确认收到。" });
    } catch {
      if (mounted.current) setState({ kind: "error", message: "网络中断或等待超时，暂时无法确认反馈是否收到。内容仍保留在本页；请稍后再试，避免连续重复发送。" });
    } finally {
      clearTimeout(timeout); controller.current = null; submitting.current = false;
    }
  };

  if (state.kind === "done") return <><RouteReady /><ReadingLayout className={styles.page}><section className={styles.success} aria-live="polite">
    <div className={styles.check} aria-hidden="true">✓</div>
    <h1>{mock ? "演示提交完成，谢谢你" : "收到了，谢谢你"}</h1>
    <p>{mock ? "演示反馈编号" : "反馈编号"} <strong>#{state.id}</strong>{mock ? "，这是本机演示回执，未向服务器发送。" : "，需要回复时我们会引用这个编号。"}</p>
    {state.message && <p className={styles.notice}>{state.message}</p>}
    <Link href={href("/")} className={styles.primary}>回到精选</Link>
  </section></ReadingLayout></>;

  const sending = state.kind === "sending";
  const disabled = !hydrated || sending;
  const canSend = !disabled && (mock || receivingEnabled) && draft.content.trim().length >= 2 && cooldown === 0;
  return <><RouteReady ready={hydrated} /><ReadingLayout aside={<FeedbackAside />} className={styles.page}>
    <header className={styles.header}><h1>说说你的想法</h1><p>关于警务科技资讯的内容、来源或阅读体验，有建议或遇到问题，都可以告诉我们。</p></header>
    {mock ? <p className={styles.notice} data-feedback-mode="mock">演示模式：提交仅在本页模拟，不向服务器发送；演示草稿单独保存。</p> : !receivingEnabled ? <p className={styles.notice} data-feedback-mode="disabled">在线反馈接收尚未开放。可以先编辑并在本机保存草稿，当前不会产生服务器回执。需要联系我们，请前往<Link href={href("/about#pulse-contact")}>关于页的联系方式</Link>。</p> : <p className={styles.notice} data-feedback-mode="live">在线反馈已开放。收到有效回执后才会清除本机草稿。</p>}
    <form onSubmit={submit} className={`${styles.form} ${dragging ? styles.dragging : ""}`} aria-busy={sending}
      onPaste={event => { const file = Array.from(event.clipboardData.files).find(item => screenshotType(item).startsWith("image/")); if (file && !disabled) { event.preventDefault(); pick(file); } }}
      onDragOver={event => { if (event.dataTransfer.types.includes("Files")) { event.preventDefault(); if (!disabled) setDragging(true); } }}
      onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false); }}
      onDrop={event => { event.preventDefault(); setDragging(false); if (!disabled) pick(event.dataTransfer.files[0]); }}>
      <fieldset disabled={disabled} className={styles.fields}>
        <div><label htmlFor="fb-content">想说点什么？</label><div className={styles.contentWrap}><textarea id="fb-content" required rows={9} maxLength={MAX_TEXT} value={draft.content} onChange={event => edit("content", event.target.value)} placeholder="例如：某篇警务无人机文章的来源链接打不开，或希望增加一个公开信源……" aria-describedby="fb-count" /><span id="fb-count" className={styles.counter}>{draft.content.length} / {MAX_TEXT}</span></div></div>
        <div><label htmlFor="fb-email">邮箱 <span>（选填）</span></label><input id="fb-email" type="email" maxLength={200} value={draft.email} onChange={event => edit("email", event.target.value)} placeholder="方便我们在需要时回复你" autoComplete="email" /></div>
        <div><label htmlFor="fb-page">关联页面 <span>（选填）</span></label><input id="fb-page" type="text" inputMode="url" maxLength={500} value={draft.pageUrl} onChange={event => edit("pageUrl", event.target.value)} placeholder="文章链接或 /articles/…" aria-describedby="fb-page-hint" /><p id="fb-page-hint" className={styles.hint}>可修改为你想反馈的页面链接。</p></div>
        <div><span className={styles.label}>截图 <span>（选填，一张）</span></span>
          {shot ? <div className={styles.attachment}>
            {/* Local object URLs have no remote image optimization path. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={shot.url} alt="待发送截图预览" width={96} height={64} />
            <div className={styles.fileInfo}><span>{shot.file.name}</span><small>{(shot.file.size / 1024 / 1024).toFixed(2)} MB</small></div>
            <div className={styles.fileActions}><button type="button" onClick={() => fileRef.current?.click()}>更换</button><button type="button" onClick={() => setShot(null)} aria-label="移除截图">移除</button></div>
          </div> : <button type="button" className={styles.upload} onClick={() => fileRef.current?.click()}><span className={styles.imageIcon} aria-hidden="true">＋</span><span><strong>添加一张问题截图</strong><small>粘贴或拖到这里也可以 · 请先遮盖敏感信息；PNG、JPEG 或 WebP，原图不超过 5 MB</small></span></button>}
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp" className={styles.fileInput} tabIndex={-1} aria-label="选择反馈截图" onChange={event => { pick(event.target.files?.[0]); event.target.value = ""; }} />
        </div>
      </fieldset>
      <div className={styles.statusArea}>
        {state.kind === "error" && <p role="alert" className={styles.error}>{state.message}</p>}
        {cooldown > 0 && <p className={styles.hint} role="status">请在 {cooldown} 秒后再试。</p>}
        <p className={styles.draftStatus} role="status" data-feedback-draft={saved}>{saved === "local" ? "文字草稿已保存在当前浏览器，截图不会保存。" : saved === "malformed" ? "原有本地草稿无法读取，已保留原数据；本次文字仅在当前页面会话暂存。" : saved === "memory" ? "浏览器未允许保存草稿；文字仅在当前页面会话暂存，刷新或关闭可能丢失。" : saved === "saving" ? "正在保存文字草稿……" : "文字草稿仅保存在当前浏览器，不会跨设备同步。"}</p>
      </div>
      <footer className={styles.footer}><p>请勿提交密钥、身份证件或与问题无关的敏感信息。</p><button className={styles.primary} type="submit" disabled={!canSend}>{sending ? "正在发送……" : mock ? "演示发送反馈" : "发送反馈"}</button></footer>
    </form>
    <details className={styles.treatment}><summary>反馈数据如何处理</summary><div><p>文字草稿仅保存在当前浏览器；截图只暂存在内存中，刷新或离开页面后需要重新选择。只有发送时，反馈内容、选填邮箱、关联页面和截图才会提交。</p><p>提交的数据用于私下处理意见、更正或下架请求，不作为公开内容展示。如需删除已提交的数据，请通过<Link href={href("/about#pulse-contact")}>现有联系方式</Link>说明反馈编号。演示模式不会提交数据。</p></div></details>
  </ReadingLayout></>;
}
