import {
  getWhitePaperHeadlineLines,
  type WhitePaperLayout,
} from "./white-paper-config";
import type { WhitePaperArticle } from "./white-paper-data";
import styles from "./intro.module.css";

interface WhitePaperProps {
  article: WhitePaperArticle;
  layout: WhitePaperLayout;
  shadowFilterId?: string;
  paperFill?: string;
  animated?: boolean;
  renderSurface?: boolean;
}

const BODY_LINE_LENGTHS = [0.9, 0.62, 0.78, 0.5];

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

export function WhitePaper({
  article,
  layout,
  shadowFilterId,
  paperFill = "#FDFDFD",
  animated = true,
  renderSurface = true,
}: WhitePaperProps) {
  const padding = clamp(layout.width * 0.1, 4, 18);
  const dateFontSize = clamp(layout.width * 0.032, 7, 14);
  const headlineFontSize = clamp(layout.width * 0.085, 9, 24);
  const headlineLineHeight = headlineFontSize * 1.03;
  const headlineLines = getWhitePaperHeadlineLines(
    article.title,
    Math.max(layout.width - padding * 2, headlineFontSize * 2),
    headlineFontSize,
  );
  const dateY = layout.height * 0.12;
  const headlineY = layout.height * 0.2;
  const bodyLineGap = layout.height * 0.03;
  const bodyStartY = Math.min(
    layout.height * 0.38,
    headlineY + headlineLineHeight * headlineLines.length + layout.height * 0.04,
  );
  const bodyStrokeWidth = clamp(layout.width * 0.008, 1.5, 3.8);
  const stapleLength = clamp(layout.width * 0.08, 5, 10);
  const stapleRise = stapleLength * Math.sin((40 * Math.PI) / 180);
  const stapleRun = stapleLength * Math.cos((40 * Math.PI) / 180);
  const stapleStartX = padding * 0.75;
  const stapleStartY = padding * 0.95;
  const contentClassName = styles.paperContent;

  return (
    <g
      className={`${styles.paperMotionLayer}${animated ? ` ${styles.paperMotionLayerAnimated}` : ""}`}
      data-white-paper={article.id}
      data-white-paper-secondary={animated ? article.id : undefined}
      data-entry-x={layout.entryX}
    >
      <g
        className={styles.paperGroup}
        transform={`translate(${layout.x} ${layout.y}) rotate(${layout.rotation})`}
      >
        {renderSurface ? (
          <rect
            className={styles.paperSurface}
            data-white-paper-surface={article.id}
            x="0"
            y="0"
            width={layout.width}
            height={layout.height}
            fill={paperFill}
            filter={shadowFilterId ? `url(#${shadowFilterId})` : undefined}
          />
        ) : null}

        <g
          className={styles.paperStaple}
          data-white-paper-staple={article.id}
          aria-hidden="true"
        >
          <line
            x1={stapleStartX}
            y1={stapleStartY}
            x2={stapleStartX + stapleRun}
            y2={stapleStartY - stapleRise}
          />
        </g>

        <g
          className={contentClassName}
          data-white-paper-content={article.id}
          data-content-entry-x={layout.contentEntryX}
        >
          <text
            className={styles.paperDate}
            data-white-paper-date={article.id}
            x={padding}
            y={dateY}
            fontSize={dateFontSize}
          >
            {`Date：${article.date}`}
          </text>
          <g
            className={styles.paperHeadline}
            data-white-paper-headline={article.id}
          >
            {headlineLines.map((line, index) => (
              <text
                key={`${article.id}-headline-${index}`}
                x={padding}
                y={headlineY + index * headlineLineHeight}
                fontSize={headlineFontSize}
              >
                {line}
              </text>
            ))}
          </g>
          <g
            className={styles.paperBody}
            data-white-paper-body={article.id}
            aria-hidden="true"
          >
            {BODY_LINE_LENGTHS.map((length, index) => {
              const y = bodyStartY + index * bodyLineGap;
              return (
                <line
                  className={styles.paperBodyLine}
                  data-white-paper-body-line={article.id}
                  key={`${article.id}-body-${index}`}
                  x1={padding}
                  x2={layout.width - padding * (1 + (1 - length) * 0.8)}
                  y1={y}
                  y2={y}
                  strokeWidth={bodyStrokeWidth}
                />
              );
            })}
          </g>
        </g>
      </g>
    </g>
  );
}
