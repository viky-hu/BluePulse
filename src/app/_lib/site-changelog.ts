import source from "../../../site/changelog.json";
import { parseChangelog } from "../changelog/_data";
// One versioned source feeds SSR, the sidebar marker and HTTP endpoints. No runtime Git or model calls.
export const changelog = parseChangelog(source);
