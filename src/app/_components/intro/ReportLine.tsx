import type { ReportGeometry } from "./intro-config";

interface ReportLineProps {
  geometry: ReportGeometry;
  color: string;
}

export function ReportLine({ geometry, color }: ReportLineProps) {
  return (
    <line
      data-report-line
      x1={geometry.line.x1}
      y1={geometry.line.centerY}
      x2={geometry.line.x2}
      y2={geometry.line.centerY}
      stroke={color}
      strokeWidth={geometry.line.strokeWidth}
      strokeLinecap="butt"
      fill="none"
      vectorEffect="non-scaling-stroke"
      pointerEvents="none"
    />
  );
}
