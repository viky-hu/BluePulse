"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { AdminPanels, type AdminRequest } from "./AdminPanels";
import { adminSections, type AdminSection } from "./sections";
import styles from "./admin.module.css";

type Session = { actor: string; csrf: string };

class AdminError extends Error {
  constructor(readonly status: number, message: string) { super(message); }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch("/api/bluepulse/admin/" + path, {
    ...options,
    cache: "no-store",
    credentials: "same-origin",
  });
  if (response.status === 204) return undefined as T;
  const result = await response.json().catch(() => null);
  if (!response.ok || result === null) {
    throw new AdminError(response.status, result?.error?.message ?? "管理服务暂时不可用。");
  }
  return result;
}

export function AdminConsole({ section }: { section: AdminSection }) {
  const [session, setSession] = useState<Session | null>();
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    request<Session>("session", { signal: controller.signal }).then(setSession, error => {
      if (controller.signal.aborted) return;
      setSession(null);
      if (!(error instanceof AdminError && error.status === 401)) {
        setMessage(error instanceof Error ? error.message : "无法检查会话。");
      }
    });
    return () => controller.abort();
  }, []);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const password = new FormData(form).get("password");
    setPending(true);
    setMessage("");
    try {
      setSession(await request<Session>("login", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }),
      }));
      form.reset();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "登录失败。");
    } finally {
      setPending(false);
    }
  }

  const manage: AdminRequest = async <T,>(path: string, method = "GET", body?: object): Promise<T> => {
    try {
      const headers = new Headers();
      if (session && method !== "GET") headers.set("X-CSRF-Token", session.csrf);
      if (body) headers.set("Content-Type", "application/json");
      return await request<T>(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
    } catch (error) {
      if (error instanceof AdminError && error.status === 401) {
        setSession(null);
        setMessage("会话已失效，请重新登录。");
      }
      throw error;
    }
  };

  async function logout() {
    setPending(true);
    setMessage("");
    try {
      await manage("logout", "POST");
      setSession(null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "退出失败。");
    } finally {
      setPending(false);
    }
  }

  return <section className={styles.shell}>
    <header className={styles.header}>
      <div><p className={styles.kicker}>BLUE PULSE</p><h1>管理后台</h1></div>
      {session && <button type="button" onClick={logout} disabled={pending}>退出登录</button>}
    </header>
    {message && <p role="alert" className={styles.error}>{message}</p>}
    {session === undefined && <p role="status">正在检查管理员会话…</p>}
    {session === null && <form className={styles.login} onSubmit={login}>
      <label>管理员密码<input type="password" name="password" autoComplete="current-password" required maxLength={512} /></label>
      <button className={styles.primary} disabled={pending}>登录</button>
    </form>}
    {session && <>
      <nav className={styles.nav} aria-label="管理分区">
        {(Object.keys(adminSections) as AdminSection[]).map(key =>
          <Link href={`/admin/${key}`} aria-current={key === section ? "page" : undefined} key={key}>{adminSections[key]}</Link>)}
      </nav>
      <AdminPanels key={section} section={section} request={manage} />
    </>}
  </section>;
}
