import { useEffect, useRef, useState } from "react";
import { assetUrl } from "../api/client";
import { applyTalkEvent, streamTalk } from "../api/talk";
import type { TalkMessage } from "../api/talk";
import { saveMode } from "../api/profile";
import { languages, useApp } from "../context";
import type { Lang } from "../api/types";
import { ChatBubble } from "../ui";
import type { OrbState } from "../ui";
import { tt } from "../ui-strings";
import { useRecorder } from "../useRecorder";
import CardView from "./TalkCards";
import TalkDock from "./TalkDock";
import TalkHeader from "./TalkHeader";

export default function Talk() {
  const { lang, setLang, profileId, setProfileId } = useApp();
  const [sessionLang, setSessionLang] = useState<string>(lang);
  const [detected, setDetected] = useState("");
  const [forced, setForced] = useState("");
  const [messages, setMessages] = useState<TalkMessage[]>([]);
  const [quick, setQuick] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState("");
  const abort = useRef<AbortController | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const counter = useRef(1);
  const bottom = useRef<HTMLDivElement>(null);
  const pid = useRef(profileId);
  const ui = (k: string) => tt(sessionLang, k);
  const recorder = useRecorder(
    (blob) => void turn({ audio: blob }),
    () => setError(ui("micDenied")),
  );
  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: "end" });
  }, [messages]);
  useEffect(
    () => () => {
      abort.current?.abort();
      audio.current?.pause();
    },
    [],
  );
  function play(url: string) {
    const src = assetUrl(url);
    if (!src) return;
    audio.current?.pause();
    const a = new Audio(src);
    audio.current = a;
    a.onplay = () => setSpeaking(true);
    a.onended = a.onpause = () => setSpeaking(false);
    void a.play().catch(() => setError(ui("audioFailed")));
  }
  async function turn(input: { text?: string; audio?: Blob }) {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setError("");
    setQuick([]);
    setBusy(true);
    const userId = counter.current++;
    const botId = counter.current++;
    setMessages((m) => [
      ...m,
      { id: userId, from: "user", text: input.text ?? "…", cards: [] },
      { id: botId, from: "bot", text: "", cards: [] },
    ]);
    try {
      if (!pid.current) {
        pid.current = await saveMode("", "talk", lang);
        setProfileId(pid.current);
      }
      await streamTalk(
        {
          profile_id: pid.current,
          ...input,
          ...(forced ? { lang: forced } : {}),
        },
        (event) => {
          if (controller.signal.aborted) return;
          if (event.type === "transcript") {
            setMessages((m) =>
              m.map((x) => (x.id === userId ? { ...x, text: event.text } : x)),
            );
            if (event.lang) {
              setDetected(event.lang);
              setSessionLang(event.lang);
            }
          } else if (event.type === "done") {
            setQuick(event.quick_replies ?? []);
            if (event.lang) setSessionLang(event.lang);
            if (event.audio_url) play(event.audio_url);
          }
          setMessages((m) => applyTalkEvent(m, event, botId));
        },
        controller.signal,
      );
    } catch (e) {
      if (!controller.signal.aborted) {
        setError((e as Error).message || ui("talkError"));
        setMessages((m) =>
          m.filter((x) => !(x.id === botId && !x.text && !x.cards.length)),
        );
      }
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  function pickLang(value: string) {
    setForced(value);
    setSessionLang(value);
    setDetected(value);
    if (value in languages) setLang(value as Lang);
  }
  const listening = recorder.recording;
  const orb: OrbState = listening
    ? "listening"
    : speaking
      ? "speaking"
      : "idle";
  const status = listening
    ? ui("listening")
    : busy
      ? ui("thinking")
      : speaking
        ? ui("speaking")
        : ui("holdToTalk");
  return (
    <div
      className="flex h-dvh flex-col overflow-hidden"
      lang={sessionLang}
      style={{
        background:
          "linear-gradient(180deg,#F7A35C 0%,#FFC994 30%,#FFE3EE 60%,#FBF6EE 100%)",
      }}
    >
      <TalkHeader lang={sessionLang} detected={detected} onPick={pickLang} />
      <div
        className="mx-auto flex w-full max-w-xl min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 pb-4"
        aria-live="polite"
      >
        {messages.length === 0 && (
          <p className="m-auto text-center text-lg text-ink-soft">
            {ui("talkEmpty")}
          </p>
        )}
        {messages.map((m) => (
          <div key={m.id} className="flex flex-col gap-2">
            {(m.text || m.from === "user") && (
              <ChatBubble from={m.from} lang={m.lang || sessionLang}>
                {m.text}
              </ChatBubble>
            )}
            {m.cards.map((c, i) => (
              <CardView
                key={i}
                card={c}
                lang={sessionLang}
                disabled={busy}
                onAnswer={(v) => void turn({ text: v })}
              />
            ))}
          </div>
        ))}
        {error && (
          <p role="alert" className="m-0 rounded-2xl bg-bad-soft p-3 text-bad">
            {error}
          </p>
        )}
        <div ref={bottom} />
      </div>
      <TalkDock
        lang={sessionLang}
        orb={orb}
        listening={listening}
        busy={busy}
        status={status}
        quick={quick}
        onHoldStart={() => {
          audio.current?.pause();
          void recorder.start();
        }}
        onHoldEnd={recorder.stop}
        onSend={(v) => void turn({ text: v.trim() })}
      />
    </div>
  );
}
