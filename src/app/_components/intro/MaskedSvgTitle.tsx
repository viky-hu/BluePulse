import type { PanelGeometry } from "./intro-config";
import { getTitleLayout } from "./intro-config";
import styles from "./intro.module.css";

interface MaskedSvgTitleProps {
  curtainClipId: string;
  title: string;
  subtitle: string;
  geometry: PanelGeometry;
  lightAreaFill: string;
  darkAreaFill: string;
}

function CharacterRow({ value, kind }: { value: string; kind: "title" | "subtitle" }) {
  return Array.from(value).map((character, index) => (
    <tspan
      key={`${kind}-${index}`}
      data-title-char={kind === "title" ? "" : undefined}
      data-subtitle-char={kind === "subtitle" ? "" : undefined}
      data-char-index={index}
    >
      {character === " " ? "\u00A0" : character}
    </tspan>
  ));
}

function TextLayer({
  title,
  subtitle,
  geometry,
  fill,
  clipped = false,
}: Omit<MaskedSvgTitleProps, "curtainClipId" | "lightAreaFill" | "darkAreaFill"> & {
  fill: string;
  clipped?: boolean;
}) {
  const layout = getTitleLayout(geometry);

  return (
    <g data-title-layer={clipped ? "curtain" : "page"}>
      <text
        className={styles.mainTitle}
        x={layout.centerX}
        y={layout.titleY}
        fill={fill}
        textAnchor="middle"
        dominantBaseline="middle"
      >
        <CharacterRow value={title} kind="title" />
      </text>
      <text
        className={styles.subtitle}
        x={layout.centerX}
        y={layout.subtitleY}
        fill={fill}
        textAnchor="middle"
        dominantBaseline="middle"
      >
        <CharacterRow value={subtitle} kind="subtitle" />
      </text>
    </g>
  );
}

export function MaskedSvgTitle({
  curtainClipId,
  title,
  subtitle,
  geometry,
  lightAreaFill,
  darkAreaFill,
}: MaskedSvgTitleProps) {
  return (
    <g className={styles.titleScene} data-intro-title>
      <TextLayer title={title} subtitle={subtitle} geometry={geometry} fill={lightAreaFill} />
      <g clipPath={`url(#${curtainClipId})`}>
        <TextLayer
          title={title}
          subtitle={subtitle}
          geometry={geometry}
          fill={darkAreaFill}
          clipped
        />
      </g>
    </g>
  );
}
