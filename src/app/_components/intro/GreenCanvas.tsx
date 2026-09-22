import type { ReportGeometry } from "./intro-config";

interface GreenCanvasProps {
  geometry: ReportGeometry;
  fill: string;
}

export function GreenCanvas({ geometry, fill }: GreenCanvasProps) {
  const safeProgress = 0;
  const topDistance = geometry.green.centerY - geometry.green.top;
  const bottomDistance = geometry.green.bottom - geometry.green.centerY;

  return (
    <rect
      data-report-green
      x={geometry.green.x}
      y={geometry.green.centerY - topDistance * safeProgress}
      width={geometry.green.width}
      height={(topDistance + bottomDistance) * safeProgress}
      fill={fill}
      pointerEvents="none"
    />
  );
}
