import Link from "next/link";
import { RouteReady } from "./MainShell";
import styles from "./section-page.module.css";

export function AboutPulse() {
  return <article className={styles.page}>
    <RouteReady />
    <header className={styles.header}><h1>关于 Pulse</h1><p>国内外警务科技情报系统</p></header>
    <div className={styles.prose}>
      <section><h2>让分散的资讯更容易阅读与追踪</h2><p>Pulse 面向警务科技研究人员，也向公众开放阅读。我们将分散在公开来源中的资讯整理为可阅读、可检索、可回溯原始出处的中文内容，帮助读者了解国内外警务科技的发展。</p></section>
      <section><h2>我们关注什么</h2><p>警务应用、公共安全技术装备、人工智能与大模型、网络与数据安全，以及相关政策标准、采购项目和研究成果。除了直接面向警务的实践，也关注可能影响这一领域的重要技术进展。</p></section>
      <section><h2>从阅读到查找</h2><p>可以从精选开始阅读，也可以在全部动态中结合关键词、时间、地区和来源筛选，或按主题浏览。文章保留来源与原文链接，中文整理内容供阅读参考，具体信息可以回到原始材料对照。</p><p><Link href="/all">浏览全部动态</Link><span aria-hidden="true"> · </span><Link href="/topics">查看主题</Link></p></section>
      <section><h2>当前浏览器的阅读记录</h2><p>公众无需登录即可阅读。收藏和浏览历史保存在当前浏览器，清除浏览器数据或更换设备后不会自动同步。</p></section>
      <section><h2>持续建设</h2><p>Pulse 正在逐步完善事件热点、日报和智能体接入等能力。各栏目的当前状态会在页面中说明，功能变化记录在更新日志中。</p><p><Link href="/changelog">查看更新日志</Link></p></section>
    </div>
  </article>;
}

export function PulseChangelog() {
  return <article className={styles.page}>
    <RouteReady />
    <header className={styles.header}><h1>更新日志</h1><p>记录 Pulse 的功能改进与更新。</p></header>
    <div className={styles.prose}>
      <section><time dateTime="2026-10-27">2026 年 10 月 27 日</time><h2>菜单与阅读入口调整</h2><p>新增 Pulse 字标和固定搜索入口，内容栏目整理为精选、全部动态、热点榜、AI日报和主题。“更多”保留 Agent 接入、关于、更新日志与反馈。</p><p>分类目录移入主题页；全部动态支持组合筛选和翻页。正在建设的栏目显示各自的当前状态。</p></section>
      <section><time dateTime="2026-10-25">2026 年 10 月 25 日</time><h2>匿名阅读与本地记录</h2><p>支持当前浏览器的收藏、浏览历史和首次封面记忆；直接打开文章或栏目地址可进入相应页面，并支持刷新、前进与后退。</p></section>
    </div>
  </article>;
}
