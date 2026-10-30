import type { ChatEvent, ChatIn } from "./types";
import { createSseParser } from "./sse";
export const BASE = (
  import.meta.env.VITE_API_URL || "http://localhost:8000"
).replace(/\/$/, "");
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
  const timer = setTimeout(() => controller.abort(), 60000);
  try {
    const res = await fetch(BASE + "/api" + path, {
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
      const body = await res.json().catch(() => null);
      throw new Error(
        typeof body?.detail === "string"
          ? body.detail
          : `Request failed (${res.status}). Please try again.`,
      );
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
export async function streamChat(
  input: ChatIn,
  onEvent: (event: ChatEvent) => void,
  signal: AbortSignal,
) {
  const res = await fetch(BASE + "/api/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(input),
    signal,
  });
  if (!res.ok || !res.body)
    throw new Error(`Chat unavailable (${res.status}). Please retry.`);
  const reader = res.body.getReader(),
    decoder = new TextDecoder();
  let doneEvent = false;
  const parser = createSseParser((data: string) => {
    if (!data) return;
    if (data === "[DONE]") {
      doneEvent = true;
      return;
    }
    const event = JSON.parse(data) as ChatEvent;
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
