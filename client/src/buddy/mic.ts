/** Tap toggles; a hold starts once and release sends once. Keyboard click toggles. */
export const HOLD_MS = 300;
export function micGesture(
  listening: boolean,
  heldMs: number,
): "start" | "stop" {
  return heldMs >= HOLD_MS ? "stop" : listening ? "stop" : "start";
}

export function silenceExpired(
  level: number,
  now: number,
  lastSound: number,
  threshold = 0.015,
) {
  return level < threshold && now - lastSound >= 2000;
}
