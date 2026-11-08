"use client";

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { adminSections, type AdminSection } from "./sections";
import styles from "./admin.module.css";

export type AdminRequest = <T>(path: string, method?: string, body?: object) => Promise<T>;
type DataProps = { request: AdminRequest; reload: () => void };
type Submit = (form: FormData) => Promise<unknown>;

const feedbackStatuses = ["new", "triaged", "replied", "resolved", "spam"];
const sourceFlags = {
  enabled: "启用采集", excerpt_allowed: "公开摘要", full_text_allowed: "站内全文",
  media_allowed: "公开媒体", syndicate_full_text_allowed: "允许全文分发",
} as const;
const topics = ["product", "practice", "paper", "law", "embodied", "public-opinion", "low-altitude"];

function text(form: FormData, name: string) { return String(form.get(name) ?? "").trim(); }
function reason(form: FormData) { return { reason: text(form, "reason") }; }
function ReasonField({ title = "操作原因" }: { title?: string }) {
  return <label>{title}<input name="reason" required maxLength={500} /></label>;
}
function Json({ data }: { data: unknown }) {
  return <pre className={styles.json}>{JSON.stringify(data, null, 2)}</pre>;
}

function Action({ children, submit, label, reload, danger = false }: {
  children?: ReactNode; submit: Submit; label: string; reload: () => void; danger?: boolean;
}) {
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ body: string; error: boolean } | null>(null);
  async function perform(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setMessage(null);
    const form = event.currentTarget;
    try {
      await submit(new FormData(form));
      setMessage({ body: "已保存", error: false });
      reload();
    } catch (error) {
      setMessage({ body: error instanceof Error ? error.message : "操作失败。", error: true });
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }
  return <form className={styles.form} onSubmit={perform}>
    {children}
    <button type="submit" className={danger ? styles.danger : undefined} disabled={busy}>{label}</button>
    {message && <span role={message.error ? "alert" : "status"} className={message.error ? styles.error : styles.meta}>{message.body}</span>}
  </form>;
}

function More({ path, request, label }: { path: string; request: AdminRequest; label: string }) {
  const [data, setData] = useState<unknown>();
  const [error, setError] = useState("");
  function load() {
    setError("");
    request(path).then(setData, cause => setError(cause instanceof Error ? cause.message : "加载失败。"));
  }
  return <div>
    <button type="button" onClick={load}>{label}</button>
    {error && <p role="alert" className={styles.error}>{error}</p>}
    {data !== undefined && <Json data={data} />}
  </div>;
}

type SourceRow = {
  id: string; slug: string; name: string; version: string; selection_threshold: number | null;
  tier: string | null; participant_key: string | null; participation_mode: string; interval_minutes: number;
  owner_entity: string | null; publisher_role: string | null;
} & Record<keyof typeof sourceFlags, boolean>;

function Sources({ rows, request, reload }: DataProps & { rows: SourceRow[] }) {
  return <ul className={styles.rows}>{rows.map(row => <li key={row.id}><details>
    <summary>{row.name} <span className={styles.meta}>{row.slug} · {row.enabled ? "启用" : "停用"}</span></summary>
    <Action label="保存信源设置" reload={reload} submit={form => request(`sources/${row.id}`, "PATCH", {
      ...reason(form),
      version: row.version,
      ...Object.fromEntries(Object.keys(sourceFlags).map(key => [key, form.has(key)])),
      selection_threshold: text(form, "threshold") === "" ? null : Number(text(form, "threshold")),
      tier: text(form, "tier") || null,
      participant_key: text(form, "participant") || null,
      owner_entity: text(form, "owner_entity") || null,
      publisher_role: text(form, "publisher_role") || null,
      participation_mode: text(form, "mode"),
      interval_minutes: Number(text(form, "interval")),
    })}>
      <fieldset className={styles.wide}>
        <legend>采集与许可</legend>
        {(Object.keys(sourceFlags) as (keyof typeof sourceFlags)[]).map(key =>
          <label key={key}><span><input name={key} type="checkbox" defaultChecked={row[key]} />{sourceFlags[key]}</span></label>)}
      </fieldset>
      <label>精选门槛<input name="threshold" type="number" min={0} max={100} defaultValue={row.selection_threshold ?? ""} placeholder="待校准" /></label>
      <label>来源级别<select name="tier" defaultValue={row.tier ?? ""}>
        <option value="">未分级</option>{["T1", "T1_5", "T2", "EXCLUDE_MP"].map(value => <option key={value}>{value}</option>)}
      </select></label>
      <label>参与方归一标识<input name="participant" maxLength={120} defaultValue={row.participant_key ?? ""} /></label>
      <label>主体规范名称<input name="owner_entity" maxLength={120} defaultValue={row.owner_entity ?? ""} /></label>
      <label>发布者角色<select name="publisher_role" defaultValue={row.publisher_role ?? ""}>
        <option value="">未核实</option><option value="organization">机构</option><option value="person">个人</option>
      </select></label>
      <label>参与模式<select name="mode" defaultValue={row.participation_mode}>
        <option value="editorial">编辑来源</option><option value="signal">讨论信号</option><option value="isolated">隔离</option>
      </select></label>
      <label>采集间隔（分钟）<input name="interval" type="number" required min={5} max={1440} defaultValue={row.interval_minutes} /></label>
      <ReasonField />
    </Action>
    <More path={`sources/${row.id}/runs`} request={request} label="查看近期采集记录" />
  </details></li>)}</ul>;
}

type ArticleRow = {
  id: string; source_title: string; zh_title: string | null; zh_summary: string | null;
  state: string; public: boolean; withdrawn: boolean; selection_status: string; grouping_status: string;
};

function Content({ rows, request, reload }: DataProps & { rows: ArticleRow[] }) {
  return <>
    <details><summary>合并事件</summary>
      <Action label="合并事件" reload={reload} submit={form => request("stories/merge", "POST", {
        ...reason(form), from_id: text(form, "from"), into_id: text(form, "into"),
      })}>
        <label>待合并事件 ID<input name="from" required /></label>
        <label>保留事件 ID<input name="into" required /></label><ReasonField />
      </Action>
    </details>
    <ul className={styles.rows}>{rows.map(row => <li key={row.id}><details>
      <summary>{row.zh_title || row.source_title} <span className={styles.meta}>{row.public ? "公开" : row.state} · {row.grouping_status}</span></summary>
      <p className={styles.meta}>{row.id} · {row.selection_status}</p>
      {row.zh_summary && <p>{row.zh_summary}</p>}
      <More path={`content/${row.id}`} request={request} label="查看归组、覆盖与回执" />
      <Action label="保存人工覆盖" reload={reload} submit={form => {
        const fields: Record<string, unknown> = reason(form);
        for (const key of ["zh_title", "zh_summary"] as const) {
          if (form.has(`clear_${key}`)) fields[key] = null;
          else if (text(form, key)) fields[key] = text(form, key);
        }
        if (form.has("clear_topics")) fields.topics = null;
        else if (form.getAll("topics").length) fields.topics = form.getAll("topics");
        for (const key of ["relevant", "selected"]) {
          const value = text(form, key);
          if (value) fields[key] = value === "auto" ? null : value === "yes";
        }
        return request(`content/${row.id}/override`, "POST", fields);
      }}>
        <label className={styles.wide}>覆盖标题<input name="zh_title" maxLength={200} placeholder={row.zh_title ?? ""} /></label>
        <label className={styles.wide}>覆盖摘要<textarea name="zh_summary" maxLength={4000} /></label>
        <label>覆盖栏目<select name="topics" multiple>{topics.map(topic => <option key={topic}>{topic}</option>)}</select></label>
        <label>相关性<select name="relevant"><option value="">保持现状</option><option value="yes">相关</option><option value="no">不相关</option><option value="auto">恢复模型判断</option></select></label>
        <label>精选<select name="selected"><option value="">保持现状</option><option value="yes">人工确认候选</option><option value="no">取消精选资格</option><option value="auto">恢复模型判断</option></select></label>
        <fieldset>
          <legend>恢复模型文案或栏目</legend>
          <label><span><input type="checkbox" name="clear_zh_title" />标题</span></label>
          <label><span><input type="checkbox" name="clear_zh_summary" />摘要</span></label>
          <label><span><input type="checkbox" name="clear_topics" />栏目</span></label>
        </fieldset>
        <ReasonField />
      </Action>
      <Action label="保存归组决定" reload={reload} submit={form => request(`content/${row.id}/membership`, "POST", {
        ...reason(form), fact_id: text(form, "fact_id") || null, standalone: form.has("standalone"),
      })}>
        <label>归入事实 ID<input name="fact_id" /></label><label><span><input type="checkbox" name="standalone" />保持独立</span></label><ReasonField />
      </Action>
      <Action label="排入重处理" reload={reload} submit={form => request(`content/${row.id}/rerun`, "POST", {
        ...reason(form), step: text(form, "step"),
      })}>
        <label>处理步骤<select name="step"><option value="analyze">重新分析</option><option value="group">重新归组</option><option value="translate">重新翻译</option></select></label><ReasonField />
      </Action>
      <Action label={row.withdrawn ? "恢复公开资格核验" : "撤回文章"} danger={!row.withdrawn} reload={reload}
        submit={form => request(`content/${row.id}/visibility`, "POST", { ...reason(form), withdrawn: !row.withdrawn })}>
        <ReasonField />
      </Action>
    </details></li>)}</ul>
  </>;
}

type FeedbackRow = {
  id: number; content: string | null; email: string | null; page_url: string | null; source_hash: string | null;
  status: string; screenshot: boolean; note: string | null; version: number; erased_at: string | null;
};

function Feedback({ rows, bans, request, reload }: DataProps & { rows: FeedbackRow[]; bans: { source_hash: string; reason: string }[] }) {
  return <>
    <ul className={styles.rows}>{rows.map(row => <li key={row.id}><details>
      <summary>#{row.id} · {row.status} · {row.content?.slice(0, 65) || "已删除"}</summary>
      {!row.erased_at && <>
        <p>{row.content}</p>
        <p className={styles.meta}>{row.email} {row.page_url}</p>
        {row.screenshot && <a href={`/api/bluepulse/admin/feedback/${row.id}/screenshot`} target="_blank" rel="noreferrer">打开私有截图</a>}
        <Action label="保存处理记录" reload={reload} submit={form => request(`feedback/${row.id}`, "PATCH", {
          status: text(form, "status"), note: text(form, "note") || null, version: row.version,
        })}>
          <label>处理状态<select name="status" defaultValue={row.status}>{feedbackStatuses.map(status => <option key={status}>{status}</option>)}</select></label>
          <label className={styles.wide}>内部备注<textarea name="note" maxLength={5000} defaultValue={row.note ?? ""} /></label>
        </Action>
        {row.source_hash && !bans.some(ban => ban.source_hash === row.source_hash) && <Action label="封禁来源" reload={reload}
          submit={form => request("feedback-bans", "POST", { ...reason(form), source_hash: row.source_hash })}><ReasonField /></Action>}
        <Action label="清除反馈个人材料" danger reload={reload}
          submit={form => request(`feedback/${row.id}/erase`, "POST", reason(form))}><ReasonField /></Action>
      </>}
    </details></li>)}</ul>
    {bans.length > 0 && <><h2>封禁列表</h2><ul className={styles.rows}>{bans.map(ban => <li key={ban.source_hash}>
      <p>{ban.reason}</p><p className={styles.meta}>{ban.source_hash}</p>
      <Action label="解除封禁" reload={reload} submit={() => request(`feedback-bans/${ban.source_hash}`, "DELETE")} />
    </li>)}</ul></>}
  </>;
}

type RunData = {
  queue: { kind: string; status: string; count: number }[]; pending_due: number; unknown_receipts: number;
  jobs: { id: string; kind: string; status: string; error: string | null; attempts: number }[];
  receipts: { key: string; subject: string; purpose: string; status: string; error: string | null; attempts: number }[];
};

function Runs({ jobs, receipts, queue, pending_due, unknown_receipts, request, reload }: DataProps & RunData) {
  return <>
    <h2>任务</h2>
    <p role="status">已到期待处理 {pending_due} 项 · 结果未知 {unknown_receipts} 条</p>
    {queue.length > 0 && <details><summary>查看各阶段积压</summary>
      <ul className={styles.rows}>{queue.map(row => <li key={`${row.kind}:${row.status}`}>{row.kind} · {row.status} · {row.count}</li>)}</ul>
    </details>}
    {!jobs.length && <p>暂无任务记录。</p>}
    <ul className={styles.rows}>{jobs.map(row => <li key={row.id}><details>
      <summary>{row.kind} · {row.status} · {row.attempts} 次</summary>
      <p className={styles.meta}>{row.id} {row.error}</p>
      {["failed", "pending"].includes(row.status) && <Action label="重新排队" reload={reload}
        submit={form => request(`runs/${row.id}/requeue`, "POST", reason(form))}><ReasonField /></Action>}
    </details></li>)}</ul>
    <h2>付费回执</h2>
    {!receipts.length && <p>暂无付费回执。</p>}
    <ul className={styles.rows}>{receipts.map(row => <li key={row.key}><details>
      <summary>{row.purpose} · {row.status} · {row.attempts} 次</summary>
      <p className={styles.meta}>{row.subject} {row.error}</p>
      {row.status === "unknown" && <Action label="记录核账并放行" reload={reload}
        submit={form => request(`receipts/${row.key}/release`, "POST", { ...reason(form), billed: text(form, "billed") === "yes" })}>
        <label>计费核对<select name="billed" defaultValue="" required><option value="" disabled>请选择</option><option value="yes">已计费</option><option value="no">未计费</option></select></label>
        <ReasonField title="核账说明" />
      </Action>}
    </details></li>)}</ul>
  </>;
}

type ModelData = { aliases: string[]; rows: { capability: string; label: string; override: string | null }[] };
function Models({ aliases, rows, request, reload }: DataProps & ModelData) {
  return <ul className={styles.rows}>{rows.map(row => <li key={row.capability}>
    <Action label="保存选择" reload={reload} submit={form => request(`models/${row.capability}`, "POST", {
      ...reason(form), model: text(form, "model") || null,
    })}>
      <label>{row.label}<select name="model" defaultValue={row.override ?? ""}>
        <option value="">部署默认</option>{aliases.map(alias => <option key={alias}>{alias}</option>)}
      </select></label><ReasonField />
    </Action>
  </li>)}</ul>;
}

type Evaluation = { id: number; label: string; created_at: string; models: string[] };
function Evaluations({ rows, request, reload }: DataProps & { rows: Evaluation[] }) {
  return <>
    <Action label="导入评测" reload={reload} submit={form => {
      let report: object;
      try { report = JSON.parse(text(form, "report")); } catch { throw new Error("评测报告不是有效 JSON。"); }
      return request("evaluations", "POST", { label: text(form, "label"), report });
    }}>
      <label>评测名称<input name="label" maxLength={160} required /></label>
      <label className={styles.wide}>SelectBench 报告 JSON<textarea name="report" required maxLength={1_000_000} /></label>
    </Action>
    <ul className={styles.rows}>{rows.map(row => <li key={row.id}><details>
      <summary>{row.label} · {row.models.join("、")}</summary>
      <More path={`evaluations/${row.id}`} request={request} label="查看评测结果" />
    </details></li>)}</ul>
  </>;
}

type Issue = { key: string; version: number };
function Daily({ rows, request, reload }: DataProps & { rows: Issue[] }) {
  return <ul className={styles.rows}>{rows.map(row => <li key={row.key}><details>
    <summary>{row.key} · 第 {row.version} 版</summary>
    <Action label="订正并保存旧版本" reload={reload} submit={form => request(`daily/${row.key}/correct`, "POST", {
      ...reason(form), version: row.version,
    })}><ReasonField title="订正原因" /></Action>
  </details></li>)}</ul>;
}

type Audit = { id: number; actor: string; action: string; subject: string | null; reason: string | null; changes: object | null; created_at: string };
function AuditLog({ rows }: { rows: Audit[] }) {
  return <ul className={styles.rows}>{rows.map(row => <li key={row.id}><details>
    <summary>{row.action} · {row.actor} · {row.created_at}</summary>
    <p className={styles.meta}>{row.subject} {row.reason}</p>
    {row.changes && <Json data={row.changes} />}
  </details></li>)}</ul>;
}

type Dataset = {
  runs: RunData; sources: { rows: SourceRow[] }; content: { rows: ArticleRow[] };
  feedback: { rows: FeedbackRow[]; bans: { source_hash: string; reason: string }[] };
  daily: { rows: Issue[] }; models: ModelData; evaluations: { rows: Evaluation[] }; audit: { rows: Audit[] };
};

function renderPanel<S extends AdminSection>(section: S, data: Dataset[S], props: DataProps) {
  switch (section) {
    case "runs": return <Runs {...props} {...(data as Dataset["runs"])} />;
    case "sources": return <Sources {...props} {...(data as Dataset["sources"])} />;
    case "content": return <Content {...props} {...(data as Dataset["content"])} />;
    case "feedback": return <Feedback {...props} {...(data as Dataset["feedback"])} />;
    case "daily": return <Daily {...props} {...(data as Dataset["daily"])} />;
    case "models": return <Models {...props} {...(data as Dataset["models"])} />;
    case "evaluations": return <Evaluations {...props} {...(data as Dataset["evaluations"])} />;
    case "audit": return <AuditLog {...(data as Dataset["audit"])} />;
  }
}

export function AdminPanels<S extends AdminSection>({ section, request }: { section: S; request: AdminRequest }) {
  const [data, setData] = useState<Dataset[S]>();
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [query, setQuery] = useState({ q: "", status: "", page: 1 });
  const reload = () => setRevision(value => value + 1);
  const paginated = ["content", "feedback", "audit"].includes(section);

  useEffect(() => {
    let stale = false;
    const params = new URLSearchParams();
    if (query.q) params.set("q", query.q);
    if (query.status) params.set("status", query.status);
    if (query.page !== 1) params.set("page", String(query.page));
    request<Dataset[S]>(section + (params.size ? "?" + params : "")).then(value => {
      if (!stale) { setError(""); setData(value); }
    }, cause => {
      if (!stale) setError(cause instanceof Error ? cause.message : "读取失败。");
    });
    return () => { stale = true; };
  }, [query, request, revision, section]);

  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setQuery({ q: text(form, "q"), status: text(form, "status"), page: 1 });
  }

  const rowCount = data && "rows" in data ? data.rows.length : null;
  return <div aria-label={adminSections[section]}>
    <div className={styles.toolbar}>
      <button type="button" onClick={reload}>刷新</button>
      {(section === "content" || section === "feedback") && <form className={styles.toolbar} onSubmit={filter}>
        <label>关键词<input name="q" maxLength={200} /></label>
        {section === "feedback" && <label>状态<select name="status"><option value="">全部</option>
          {feedbackStatuses.map(status => <option key={status}>{status}</option>)}
        </select></label>}
        <button>筛选</button>
      </form>}
    </div>
    {error && <p role="alert" className={styles.error}>{error}</p>}
    {!data && !error && <p role="status">正在读取管理数据…</p>}
    {rowCount === 0 && <p>暂无记录。</p>}
    {data && renderPanel(section, data, { request, reload })}
    {paginated && <div className={styles.toolbar}>
      <button type="button" disabled={query.page <= 1} onClick={() => setQuery(current => ({ ...current, page: current.page - 1 }))}>上一页</button>
      <span>第 {query.page} 页</span>
      <button type="button" disabled={rowCount !== 50} onClick={() => setQuery(current => ({ ...current, page: current.page + 1 }))}>下一页</button>
    </div>}
  </div>;
}
