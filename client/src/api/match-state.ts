import type { MatchEvent, MatchResult } from "./types";
const order = { eligible: 0, likely: 1, unknown: 2, not_eligible: 3 };
export function applyMatchEvent(
  matches: MatchResult[],
  event: MatchEvent,
): MatchResult[] {
  if (event.type === "done") return event.results;
  if (event.type !== "result") return matches;
  return [
    ...matches.filter((m) => m.scheme.slug !== event.result.scheme.slug),
    event.result,
  ].sort(
    (a, b) =>
      order[a.verdict] - order[b.verdict] || b.confidence - a.confidence,
  );
}
