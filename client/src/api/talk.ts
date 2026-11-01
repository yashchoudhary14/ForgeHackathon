import { BASE } from "./client";
import { createSseParser } from "./sse";
import { responseError } from "./errors";
import type { Citation, ProfileData } from "./types";
import type { BuddyAction } from "../buddy/actions";

/** Languages POST /talk accepts as `lang` (server schemas.Lang). */
export const talkLangs = [
  "en",
  "hi",
  "bn",
  "as",
  "ta",
  "te",
  "mr",
  "gu",
  "kn",
  "ml",
  "pa",
  "od",
];

export type TalkCard =
  | {
      kind: "service";
      service_id: string;
      service: string;
      official_portal_url: string | null;
      steps: string[];
      documents: string[];
      fees: string | null;
      time: string | null;
      notes: string[];
      sources: { url: string; title: string }[];
    }
  | { kind: "sources"; sources: { url: string; title: string }[] }
  | {
      kind: "scheme";
      slug: string;
      name: string;
      verdict: string;
      summary?: string;
      citations?: Citation[];
    }
  | { kind: "run"; run_id: string; title?: string }
  // report_id is null when Buddy suggests opening the report flow (nothing filed yet).
  | { kind: "report"; report_id: string | null; title?: string }
  | { kind: "question"; field: string; options: string[]; label?: string }
  | { kind: "document_request"; doc_type: string; reason?: string };

export type TalkStage =
  | "planning"
  | "saving_profile"
  | "finding_schemes"
  | "finding_service"
  | "searching_sources"
  | "preparing_reply"
  | "preparing_audio";

export type TalkEvent =
  | { type: "action"; action: BuddyAction }
  | { type: "audio"; audio_url: string }
  | { type: "transcript"; text: string; lang?: string }
  | { type: "progress"; stage: TalkStage }
  | { type: "delta"; text: string }
  | { type: "card"; card: TalkCard }
  | {
      type: "done";
      text?: string;
      lang?: string;
      audio_url?: string | null;
      quick_replies?: string[];
      profile?: ProfileData;
    }
  | { type: "error"; message: string };

export interface TalkInput {
  profile_id: string;
  text?: string;
  audio?: Blob;
  lang?: string;
  context?: {
    page: string;
    run_id: string | null;
    pending_step: string | null;
    onboarding?: boolean;
  };
  stream_audio?: boolean;
}

/** Builds the request body: multipart when audio is present, JSON otherwise. */
export function talkBody(input: TalkInput): {
  body: BodyInit;
  headers: Record<string, string>;
} {
  // Unknown language codes are omitted so speech detection can choose safely.
  const lang =
    input.lang && talkLangs.includes(input.lang) ? input.lang : undefined;
  if (input.audio) {
    const form = new FormData();
    form.set("profile_id", input.profile_id);
    const ext = input.audio.type.includes("ogg")
      ? "ogg"
      : input.audio.type.includes("mp4")
        ? "m4a"
        : "webm";
    form.set("audio", input.audio, "speech." + ext);
    if (lang) form.set("lang", lang);
    if (input.context) form.set("context", JSON.stringify(input.context));
    if (input.stream_audio) form.set("stream_audio", "true");
    return { body: form, headers: {} };
  }
  return {
    body: JSON.stringify({
      profile_id: input.profile_id,
      text: input.text ?? "",
      ...(lang ? { lang } : {}),
      ...(input.context ? { context: input.context } : {}),
      ...(input.stream_audio ? { stream_audio: true } : {}),
    }),
    headers: { "Content-Type": "application/json" },
  };
}

export async function streamTalk(
  input: TalkInput,
  onEvent: (event: TalkEvent) => void,
  signal: AbortSignal,
) {
  const { body, headers } = talkBody(input);
  const res = await fetch(BASE + "/api/talk", {
    method: "POST",
    credentials: "include",
    headers: { Accept: "text/event-stream", ...headers },
    body,
    signal,
  });
  if (!res.ok || !res.body) throw new Error(responseError(res.status));
  const reader = res.body.getReader(),
    decoder = new TextDecoder();
  let finished = false;
  const parser = createSseParser((data: string) => {
    if (!data) return;
    if (data === "[DONE]") {
      finished = true;
      return;
    }
    const event = JSON.parse(data) as TalkEvent;
    if (event.type === "error") throw new Error(event.message);
    if (event.type === "done") finished = true;
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
      if (finished) break;
    }
    if (!finished)
      throw new Error("The connection ended before the answer was complete.");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export interface TalkMessage {
  id: number;
  from: "user" | "bot";
  text: string;
  lang?: string;
  cards: TalkCard[];
  audioUrl?: string | null;
}

/** Pure reducer for a turn: keeps the UI logic testable. */
export function applyTalkEvent(
  messages: TalkMessage[],
  event: TalkEvent,
  botId: number,
): TalkMessage[] {
  const updateBot = (fn: (m: TalkMessage) => TalkMessage) =>
    messages.map((m) => (m.id === botId ? fn(m) : m));
  switch (event.type) {
    case "delta":
      return updateBot((m) => ({ ...m, text: m.text + event.text }));
    case "card":
      return updateBot((m) => ({ ...m, cards: [...m.cards, event.card] }));
    case "done":
      return updateBot((m) => ({
        ...m,
        text: event.text || m.text,
        lang: event.lang || m.lang,
        audioUrl: event.audio_url ?? m.audioUrl,
      }));
    default:
      return messages;
  }
}
