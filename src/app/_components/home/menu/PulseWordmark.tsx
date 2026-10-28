import Image from "next/image";
import styles from "./sidebar.module.css";

/** Original qlxf geometry paired with the selected C / Wave path-based wordmark. */
export function PulseWordmark() {
  return (
    <span className={styles.wordmark} aria-hidden="true">
      <Image className={styles.brandMark} src="/logo.svg" alt="" width={3621} height={4252} loading="eager" unoptimized />
      <Image className={styles.brandLettering} src="/pulse-wordmark.svg" alt="" width={528} height={144} loading="eager" unoptimized />
    </span>
  );
}
