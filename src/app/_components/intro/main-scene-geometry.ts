import type { MainSceneRefs } from "../home/MainScene";
import type { PanelRect } from "./intro-config";

/** Read only when geometry changes; the CSS scene owns the final layout. */
export function readMainSceneGeometry(scene: SVGSVGElement, targets: MainSceneRefs) {
  const matrix = scene.getScreenCTM();
  const green = targets.green.current, paper = targets.paper.current;
  if (!matrix || !green || !paper) return null;
  const inverse = matrix.inverse();
  const toSceneRect = (element: SVGSVGElement): PanelRect => {
    const rect = element.getBoundingClientRect();
    const start = new DOMPoint(rect.left, rect.top).matrixTransform(inverse);
    const end = new DOMPoint(rect.right, rect.bottom).matrixTransform(inverse);
    return { x: start.x, y: start.y, width: end.x - start.x, height: end.y - start.y };
  };
  return { green: toSceneRect(green), paper: toSceneRect(paper) };
}
