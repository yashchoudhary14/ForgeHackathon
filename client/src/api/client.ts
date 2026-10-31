import type { ChatEvent, ChatIn, MatchEvent, MatchIn } from "./types";
import { createSseParser } from "./sse";
import { responseError } from "./errors";
export const BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000")
  .trim()
  .replace(/\/+$/, "");
export function websocketUrl(path: string): string {
  const url = new URL(BASE + "/api" + path);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.href;
}
export const assetUrl = (url: string) => safeUrl(url);
export function safeUrl(url?: string | null): string | undefined {
  if (!url) return;
  try {
    const u = new URL(url, BASE + "/");
    return ["https:", "http:"].includes(u.protocol) ? u.href : undefined;
  } catch {
    return;
  }
}
export async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const controller = new AbortController();
  const slowRoute = /^\/(schemes\/match|explain|documents)(?:[/?]|$)/.test(
    path,
  );
  const timer = setTimeout(
    () => controller.abort(),
    slowRoute ? 150000 : 60000,
  );
  try {
    const res = await fetch(BASE + "/api" + path, {
      credentials: "include",
      ...init,
      headers: {
        ...(!(init.body instanceof FormData) && init.body
          ? { "Content-Type": "application/json" }
          : {}),
        ...init.headers,
      },
      signal: init.signal
        ? AbortSignal.any([init.signal, controller.signal])
        : controller.signal,
    });
    if (!res.ok) {
      throw new Error(responseError(res.status));
    }
    return (await res.json()) as T;
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError")
      throw new Error(
        "The request timed out or was cancelled. Please try again.",
      );
    if (e instanceof TypeError)
      throw new Error(
        "Could not connect to the service. Check your connection and try again.",
      );
    throw e;
  } finally {
    clearTimeout(timer);
  }
}
export const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });
export const streamChat = (
  input: ChatIn,
  onEvent: (event: ChatEvent) => void,
  signal: AbortSignal,
) => streamEvents("/chat", input, onEvent, signal);
export const streamMatches = (
  input: MatchIn,
  onEvent: (event: MatchEvent) => void,
  signal: AbortSignal,
) => streamEvents("/schemes/match/stream", input, onEvent, signal);
async function streamEvents<T extends ChatEvent | MatchEvent>(
  path: string,
  input: unknown,
  onEvent: (event: T) => void,
  signal: AbortSignal,
) {
  const res = await fetch(BASE + "/api" + path, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(input),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(responseError(res.status));
  const reader = res.body.getReader(),
    decoder = new TextDecoder();
  let doneEvent = false;
  const parser = createSseParser((data: string) => {
    if (!data) return;
    if (data === "[DONE]") {
      doneEvent = true;
      return;
    }
    const event = JSON.parse(data) as T;
    if (event.type === "error") throw new Error(event.message);
    if (event.type === "done") doneEvent = true;
    onEvent(event);
  });
  try {
    while (true) {
      const { value, done } = await reader.read();
      parser.push(
        done ? decoder.decode() : decoder.decode(value, { stream: true }),
      );
      if (done) {
        parser.finish();
        break;
      }
      if (doneEvent) break;
    }
    if (!doneEvent)
      throw new Error(
        "The connection ended before the answer was complete. Please retry.",
      );
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
