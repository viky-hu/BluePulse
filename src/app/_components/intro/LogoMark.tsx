import styles from "./intro.module.css";
import { INTRO_COLORS } from "./intro-config";

export function LogoMark() {
  return (
    <svg
      className={styles.logoCanvas}
      data-intro-logo
      viewBox="0 0 3621 4252"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
    >
      <path
        className={styles.logoPath}
        data-logo-path
        d="M129.156 797C686.083 1753.5 760.504 2257.73 483.474 3096C158.262 2219.5 78.0898 1716.42 129.156 797Z"
        fill="none"
        stroke={INTRO_COLORS.gold}
        vectorEffect="non-scaling-stroke"
      />
      <path
        className={styles.logoPath}
        data-logo-path
        d="M936 2315L1375.5 2155C1532.5 3023.5 1780.09 3365.09 2302.5 3809.5C2134.68 3942.3 2026.14 4032.32 1809.5 4140C1289.72 3910.25 1030.05 3733.97 633.5 3320C854.956 2965.66 928.973 2748.49 936 2315Z"
        fill="none"
        stroke={INTRO_COLORS.gold}
        vectorEffect="non-scaling-stroke"
      />
      <path
        className={styles.logoPath}
        data-logo-path
        d="M1764 67L345 633.5C730.697 1156.26 866.075 1474.73 947.5 2093L1382 1927C1420.89 1644.4 1471.56 1457 1616.5 1068L1843 1155.35C1424 2346.5 1738.5 2820.5 2545.5 3668.85L2865.5 3425.5C2734.06 3348.97 2669.28 3302.87 2568 3215.5C2448.2 3088.11 2389.05 3019.55 2299.5 2903C2198.66 2753.03 2152.92 2666.72 2094.5 2508C2050.31 2340.64 2032.9 2244.79 2021.5 2068.5C2020.36 1897.58 2029.77 1803.49 2065.5 1639C2112.57 1455.68 2148.92 1363.97 2231 1219.5C2324.85 1074.56 2381.92 1006.09 2490 902C2596.39 806.152 2660.25 755.863 2782.5 673V1024C2692.96 1088.28 2648.6 1131.76 2577.5 1219.5C2491.23 1325.17 2453.84 1390.27 2407 1517C2340.67 1695.09 2318.03 1784.2 2299.5 1927C2277.02 2125.46 2290.56 2235.55 2368 2429.5C2446.36 2617.41 2509.61 2721.16 2660.5 2903C2784.78 3039.39 2869.34 3101.2 3046.5 3186C3183.76 2859.52 3244.14 2686.73 3324.5 2395.5C3399.26 2037.94 3420.41 1847.13 3446.5 1517C3491.84 1014.15 3483.33 828.828 3388 726.5L3178 633.5L1764 67Z"
        fill="none"
        stroke={INTRO_COLORS.gold}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
