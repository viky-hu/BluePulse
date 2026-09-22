import type { ReportGeometry } from "./intro-config";
import styles from "./intro.module.css";

interface LatestReportTitleProps {
  geometry: ReportGeometry;
  upperClipId: string;
  lowerClipId: string;
  titleColor: string;
  subtitleColor: string;
}

export function LatestReportTitle({
  geometry,
  upperClipId,
  lowerClipId,
  titleColor,
  subtitleColor,
}: LatestReportTitleProps) {
  return (
    <g data-report-title-scene className={styles.reportScene}>
      <g clipPath={`url(#${upperClipId})`} data-report-title>
        <text
          data-report-title-upper
          className={styles.reportTitle}
          x={geometry.title.centerX}
          y={geometry.title.centerY}
          fontSize={geometry.title.fontSize}
          fill={titleColor}
          textAnchor="middle"
          dominantBaseline="middle"
        >
          Latest Report
        </text>
      </g>
      <g clipPath={`url(#${lowerClipId})`} data-report-title>
        <text
          data-report-title-lower
          className={styles.reportTitle}
          x={geometry.title.centerX}
          y={geometry.title.centerY}
          fontSize={geometry.title.fontSize}
          fill={titleColor}
          textAnchor="middle"
          dominantBaseline="middle"
        >
          Latest Report
        </text>
      </g>
      <text
        data-report-subtitle
        className={styles.reportSubtitle}
        x={geometry.subtitle.centerX}
        y={geometry.subtitle.y}
        fontSize={geometry.subtitle.fontSize}
        fill={subtitleColor}
        textAnchor="middle"
        dominantBaseline="middle"
      >
        基于大模型智能分析推送最新资讯
      </text>
    </g>
  );
}
