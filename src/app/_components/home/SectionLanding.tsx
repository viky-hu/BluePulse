import { RouteReady } from "./MainShell";
import { SECTION_PAGES, type SectionPath } from "./navigation-config";
import styles from "./section-page.module.css";

export function SectionLanding({ path }: { path: SectionPath }) {
  const page = SECTION_PAGES[path];
  return <div className={styles.page}>
    <RouteReady />
    <header className={styles.header}><h1>{page.title}</h1><p>{page.description}</p></header>
    <p className={styles.status} role="status">{page.status}</p>
  </div>;
}
