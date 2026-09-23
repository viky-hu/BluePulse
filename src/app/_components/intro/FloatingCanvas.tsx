import type { ReactNode } from "react";
import type { PanelGeometry } from "./intro-config";
import styles from "./intro.module.css";

interface FloatingCanvasProps {
  geometry: PanelGeometry;
  curtainClipId: string;
  shadowFilterId: string;
  lightFill: string;
  darkFill: string;
  children?: ReactNode;
}

export function FloatingCanvas({
  geometry,
  curtainClipId,
  shadowFilterId,
  lightFill,
  darkFill,
  children,
}: FloatingCanvasProps) {
  const rectangle = {
    x: geometry.x,
    y: geometry.y,
    width: geometry.width,
    height: geometry.height,
  };
  const bleed = 2;
  const darkRectangle = {
    x: geometry.x - bleed,
    y: geometry.y - bleed,
    width: geometry.width + bleed * 2,
    height: geometry.height + bleed * 2,
  };

  return (
    <g className={styles.panelGroup} data-intro-panel>
      <rect {...rectangle} fill={lightFill} filter={`url(#${shadowFilterId})`} />
      {children}
      <rect {...darkRectangle} fill={darkFill} clipPath={`url(#${curtainClipId})`} />
    </g>
  );
}
