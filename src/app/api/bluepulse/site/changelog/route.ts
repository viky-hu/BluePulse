import { changelog } from "../../../../_lib/site-changelog";
import { siteJson } from "../../../../_lib/site-json";
export function GET(request: Request) { return siteJson(request, changelog, 300); }
