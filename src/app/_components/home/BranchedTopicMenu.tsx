"use client";

import { useMemo } from "react";
import type { Topic } from "../../_lib/home-data";
import styles from "./home.module.css";

import { buildTopicMenuGroups, TOPIC_MENU_LABELS } from "./topic-menu-config";

const PAD = 6;
const ROW_HEIGHT = 36;
const INDENT = 40;
const TRUNK = 14;
const RADIUS = 10;
const LINE_WIDTH = 1.5;
const END_X = INDENT - 8;

function rowY(index: number) {
  return PAD + index * ROW_HEIGHT + ROW_HEIGHT / 2;
}

function branchPath(index: number) {
  const y = rowY(index);
  return `M ${TRUNK} ${y - RADIUS} A ${RADIUS} ${RADIUS} 0 0 0 ${TRUNK + RADIUS} ${y} H ${END_X}`;
}

function reachPath(index: number) {
  const y = rowY(index);
  return `M ${TRUNK} 0 V ${y - RADIUS} A ${RADIUS} ${RADIUS} 0 0 0 ${TRUNK + RADIUS} ${y} H ${END_X}`;
}

function trunkPath(count: number) {
  return `M ${TRUNK} 0 V ${rowY(Math.max(0, count - 1)) - RADIUS}`;
}

export function BranchedTopicMenu({
  topics,
  activeSlug,
  status,
  onSelect,
}: {
  topics: Topic[];
  activeSlug: string;
  status: "loading" | "ready" | "empty" | "error";
  onSelect: (topic: Topic) => void;
}) {
  const groups = useMemo(() => buildTopicMenuGroups(topics), [topics]);
  const availableCount = groups.reduce((count, group) => count + group.topics.filter((entry) => entry.available).length, 0);
  const showGroups = status === "ready" || status === "empty";

  return (
    <nav className={styles.topicTree} aria-label="主题分类">
      <div className={styles.treeHeading}><span>主题分类</span>{showGroups ? <span>{availableCount}</span> : null}</div>
      {showGroups ? (
        <div className={styles.treeGroups}>
          {groups.map((group) => {
            const activeIndex = group.topics.findIndex((entry) => entry.slug === activeSlug && entry.available);
            const bodyHeight = PAD * 2 + group.topics.length * ROW_HEIGHT;
            return (
              <section className={styles.treeGroup} key={group.id}>
                <div className={styles.treeGroupHeading} role="heading" aria-level={3}>
                  <span className={`${styles.treeGroupMarker} ${activeIndex >= 0 ? styles.treeGroupMarkerActive : ""}`} aria-hidden="true" />
                  <span>{group.label}</span>
                </div>
                <div className={styles.treeGroupBody} style={{ height: bodyHeight }}>
                  <svg className={styles.treeSvg} width={INDENT + 12} height={bodyHeight} viewBox={`0 0 ${INDENT + 12} ${bodyHeight}`} aria-hidden="true">
                    <path className={styles.treeTrunk} strokeWidth={LINE_WIDTH} d={trunkPath(group.topics.length)} />
                    {group.topics.map((entry, index) => (
                      <path key={entry.slug} className={styles.treeBranch} strokeWidth={LINE_WIDTH} d={branchPath(index)} />
                    ))}
                    {activeIndex >= 0 ? (
                      <path className={styles.treeReach} strokeWidth={LINE_WIDTH + 0.3} d={reachPath(activeIndex)} />
                    ) : null}
                  </svg>
                  {group.topics.map((entry) => {
                    const isActive = entry.slug === activeSlug && entry.available;
                    const topic = entry.topic;
                    const label = topic?.name_zh ?? TOPIC_MENU_LABELS[entry.slug] ?? entry.slug;
                    return (
                      <div className={styles.treeRow} key={entry.slug}>
                        <button
                          type="button"
                          className={`${styles.topicButton} ${isActive ? styles.topicButtonActive : ""}`}
                          aria-current={isActive ? "page" : undefined}
                          disabled={!topic}
                          onClick={() => topic && onSelect(topic)}
                        >
                          <span>{label}</span>
                        </button>
                      </div>
                    );
                  })}
                </div>
              </section>
            );
          })}
        </div>
      ) : <p className={styles.treeMessage}>{status === "loading" ? "载入中" : status === "error" ? "暂不可用" : "暂无分类"}</p>}
    </nav>
  );
}
