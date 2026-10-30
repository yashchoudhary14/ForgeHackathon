import type { RunOut, RunStatus, ServerMessage } from "./types";

export const isTerminal = (status: RunStatus) =>
  status === "done" || status === "failed" || status === "aborted";

export function applyRunEvent(run: RunOut, message: ServerMessage): RunOut {
  switch (message.type) {
    case "step":
      return {
        ...run,
        steps: [
          ...run.steps.filter((step) => step.idx !== message.step.idx),
          message.step,
        ].sort((a, b) => a.idx - b.idx),
      };
    case "status":
      return { ...run, status: message.status };
    case "needs_human":
      return {
        ...run,
        status:
          message.kind === "confirm_submit"
            ? "awaiting_approval"
            : "needs_human",
      };
    case "done":
      return { ...run, status: "done", receipt: message.receipt };
    default:
      return run;
  }
}

export function mergeRunSnapshot(
  snapshot: RunOut,
  current: RunOut | null,
  liveSteps: ReadonlySet<number>,
  preserveLiveStatus: boolean,
): RunOut {
  if (!current) return snapshot;
  return {
    ...snapshot,
    ...(preserveLiveStatus
      ? {
          status: current.status,
          receipt: current.receipt ?? snapshot.receipt,
          error: current.error ?? snapshot.error,
        }
      : {}),
    steps: [
      ...new Map([
        ...snapshot.steps.map((step) => [step.idx, step] as const),
        ...current.steps
          .filter((step) => liveSteps.has(step.idx))
          .map((step) => [step.idx, step] as const),
      ]).values(),
    ].sort((a, b) => a.idx - b.idx),
  };
}
