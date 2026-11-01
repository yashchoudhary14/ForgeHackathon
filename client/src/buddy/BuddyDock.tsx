import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Mic, Send, Volume2, X } from "lucide-react";
import { applyTalkEvent, streamTalk } from "../api/talk";
import { request } from "../api/client";
import { uploadForm } from "../api/locker";
import type { LockerItem } from "../api/locker";
import { saveMode } from "../api/profile";
import type { Human, Lang, SttOut } from "../api/types";
import { languages, useApp } from "../context";
import { Orb } from "../ui";
import { useRecorder } from "../useRecorder";
import CameraCapture from "../pages/CameraCapture";
import CardView from "../pages/TalkCards";
import {
  confirmationIntent,
  dispatchAction,
  normaliseAnswer,
  profileComplete,
} from "./actions";
import { useBuddy } from "./context";
import { HOLD_MS, micGesture } from "./mic";
import { buddyText, documentFix } from "./strings";
import { useBuddyRun } from "./useBuddyRun";
import { useBuddyAudio } from "./useBuddyAudio";

interface Capture {
  docType: string;
  reason: string;
  runId?: string;
  requestId?: string;
}
interface Confirmation {
  value: string;
  requestId?: string;
  kind: string;
}

export default function BuddyDock() {
  const { lang, setLang, profileId, setProfileId, mode, setMode } = useApp();
  const {
    messages,
    setMessages,
    open,
    setOpen,
    runId,
    setRunId,
    onboarding,
    setOnboarding,
  } = useBuddy();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const ui = (key: Parameters<typeof buddyText>[1]) => buddyText(lang, key);
  const [busy, setBusy] = useState(false),
    [text, setText] = useState(""),
    [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [draftTranscript, setDraftTranscript] = useState("");
  const draftRequest = useRef<AbortController | null>(null);
  const draftBusy = useRef(false),
    draftEpoch = useRef(0);
  const [quick, setQuick] = useState<string[]>([]);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [capture, setCapture] = useState<Capture | null>(null);
  const [camera, setCamera] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const id = useRef(Date.now());
  const currentProfile = useRef(profileId);
  currentProfile.current = profileId;
  const creation = useRef<Promise<string> | null>(null);
  const sending = useRef(false);
  const pendingUpload = useRef<File | null>(null);
  const speech = useBuddyAudio(() => setError(ui("audioError")));
  const captureRef = useRef(capture);
  captureRef.current = capture;
  const confirmationRef = useRef(confirmation);
  confirmationRef.current = confirmation;
  const voiceTarget = useRef<{
    runId: string;
    requestId?: string;
    kind: string;
  } | null>(null);
  const holdTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const held = useRef(false),
    suppressClick = useRef(false);
  const tail = useRef<HTMLDivElement>(null);

  function narrate(value: string) {
    setNotice(value);
    void speech.say(value, lang);
  }
  function openCamera(docType: string, reason: string, human?: Human) {
    recorder.cancel();
    setOpen(true);
    setCapture({
      docType,
      reason,
      ...(human ? { runId, requestId: human.request_id } : {}),
    });
    setCamera(true);
    narrate(reason + " " + ui("camera"));
  }
  const live = useBuddyRun(
    (human) => {
      abort.current?.abort();
      recorder.cancel();
      setOpen(true);
      setConfirmation(null);
      setText("");
      setQuick([]);
      const instructions = [
        human.guide?.title,
        ...(human.guide?.steps || []),
        human.message,
        human.kind === "otp"
          ? ui("otp")
          : human.kind === "captcha"
            ? ui("captcha")
            : "",
      ]
        .filter(Boolean)
        .join(" ");
      setNotice(instructions);
      speech.begin();
      if (human.capture_required && human.doc_type)
        openCamera(human.doc_type, ui("camera"), human);
      else if (human.audio_url) {
        speech.enqueue(human.audio_url);
        // Server guidance audio covers guide.steps. Speak the actual missing-field
        // question separately without ever sending its answer to the conversation.
        if (human.kind === "missing_field" && human.message)
          void appendQuestion(human.message, human.request_id);
      } else void speech.say(instructions, human.guide?.lang || lang);
    },
    () => {
      if (confirmationRef.current) speech.stop();
      setConfirmation(null);
      setText("");
      setNotice("");
    },
    (message) => setError(message),
  );

  async function appendQuestion(question: string, requestId?: string) {
    // A private TTS blob stays in memory; no public audio file or Gemini call.
    const response = await fetchTts(question);
    if (
      response &&
      live.pending.current?.kind === "missing_field" &&
      live.pending.current.request_id === requestId
    )
      speech.enqueue(response);
  }
  const privateAudio = useRef<string[]>([]);
  async function fetchTts(value: string) {
    try {
      const { BASE } = await import("../api/client");
      const response = await fetch(BASE + "/api/voice/tts", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: value, language: lang }),
      });
      if (!response.ok) return;
      const url = URL.createObjectURL(await response.blob());
      privateAudio.current.push(url);
      return url;
    } catch {
      setError(ui("audioError"));
    }
  }
  const recorder = useRecorder(
    (blob) => void submit({ audio: blob }),
    () => setError(ui("micError")),
    (blob) => void previewTranscript(blob),
  );
  async function previewTranscript(blob: Blob) {
    if (draftBusy.current) return;
    const epoch = draftEpoch.current;
    const controller = new AbortController();
    draftRequest.current = controller;
    draftBusy.current = true;
    try {
      const result = await transcribe(blob, controller.signal);
      if (
        !controller.signal.aborted &&
        epoch === draftEpoch.current &&
        recorder.isActive()
      )
        setDraftTranscript((old) =>
          [old, result.text].filter(Boolean).join(" "),
        );
    } catch {
      /* Final STT reports actionable failures; drafts are best effort. */
    } finally {
      if (draftRequest.current === controller) draftBusy.current = false;
    }
  }

  useEffect(() => {
    tail.current?.scrollIntoView({ block: "nearest" });
  }, [messages, notice, confirmation]);
  useEffect(() => {
    if (!busy && pendingUpload.current) {
      const file = pendingUpload.current;
      pendingUpload.current = null;
      void upload(file);
    }
  }, [busy]);
  useEffect(() => {
    if (pathname === "/talk" || onboarding) setOpen(true);
  }, [pathname, onboarding, setOpen]);
  useEffect(() => {
    return () => {
      abort.current?.abort();
      clearTimeout(holdTimer.current);
      draftRequest.current?.abort();
      privateAudio.current.forEach((url) => URL.revokeObjectURL(url));
    };
  }, []);
  useEffect(() => {
    const unlock = () => speech.unlock();
    window.addEventListener("pointerdown", unlock, { once: true });
    window.addEventListener("keydown", unlock, { once: true });
    return () => {
      window.removeEventListener("pointerdown", unlock);
      window.removeEventListener("keydown", unlock);
    };
  }, []);
  useEffect(() => {
    const start = () => {
      setOpen(true);
      narrate(ui("state"));
    };
    window.addEventListener("buddy:onboard", start);
    return () => window.removeEventListener("buddy:onboard", start);
  }, [lang]);
  useEffect(() => {
    const reopen = () => {
      const human = live.pending.current;
      if (human?.capture_required && human.doc_type)
        openCamera(human.doc_type, ui("camera"), human);
    };
    window.addEventListener("buddy:capture", reopen);
    return () => window.removeEventListener("buddy:capture", reopen);
  }, [runId, lang]);

  async function ensureProfile() {
    if (!mode) setMode("talk");
    if (currentProfile.current) return currentProfile.current;
    if (!creation.current) creation.current = saveMode("", "talk", lang);
    try {
      const value = await creation.current;
      currentProfile.current = value;
      setProfileId(value);
      return value;
    } finally {
      creation.current = null;
    }
  }
  async function setLanguage(value: Lang) {
    const pid = await ensureProfile();
    await request(`/profile/${encodeURIComponent(pid)}`, {
      method: "PUT",
      body: JSON.stringify({ language: value }),
    });
    setLang(value);
  }
  async function execute(action: unknown) {
    await dispatchAction(action, {
      navigate,
      activateRun: setRunId,
      openCamera: (docType, reason) => openCamera(docType, reason),
      setLanguage,
      profileChanged: () =>
        window.dispatchEvent(new Event("buddy:profile-changed")),
    });
  }
  function confirmAnswer() {
    const answer = confirmationRef.current;
    if (!answer) return;
    if (
      !live.send({ type: "human_input", value: answer.value }, answer.requestId)
    ) {
      setError(ui("disconnected"));
      return;
    }
    setConfirmation(null);
    setNotice("");
    speech.stop();
  }
  async function humanAnswer(value: string, human: Human, spoken: boolean) {
    if (!["otp", "captcha", "missing_field"].includes(human.kind)) {
      narrate(ui("privateStep"));
      return;
    }
    if (confirmationRef.current) {
      const intent = confirmationIntent(value);
      if (intent === "yes") {
        confirmAnswer();
        return;
      }
      if (intent === "no") {
        setConfirmation(null);
        narrate(ui("retry"));
        return;
      }
    }
    const answer = normaliseAnswer(value, human.kind, spoken);
    if (!answer) return;
    if (human.kind === "otp" && !/^\d{6}$/.test(answer)) {
      narrate(ui("six"));
      return;
    }
    setConfirmation({
      value: answer,
      requestId: human.request_id,
      kind: human.kind,
    });
    narrate(
      ui("heard").replace(
        "{value}",
        human.kind === "otp" || human.kind === "captcha"
          ? [...answer].join(" ")
          : answer,
      ),
    );
  }
  async function transcribe(blob: Blob, signal: AbortSignal) {
    const form = new FormData();
    form.set(
      "audio",
      blob,
      "answer." + (blob.type.includes("mp4") ? "m4a" : "webm"),
    );
    form.set("language", lang);
    return request<SttOut>("/voice/stt", {
      method: "POST",
      body: form,
      signal,
    });
  }
  async function submit(input: { text?: string; audio?: Blob }) {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setError("");
    setText("");
    setOpen(true);
    draftEpoch.current++;
    draftRequest.current?.abort();
    setDraftTranscript("");
    speech.begin();
    const controller = new AbortController();
    abort.current?.abort();
    abort.current = controller;
    try {
      const human = live.pending.current;
      // Voice started on a human step is never rerouted to Talk if that step ends.
      const target = voiceTarget.current;
      voiceTarget.current = null;
      if (human || (input.audio && target)) {
        if (
          !human ||
          (input.audio &&
            target &&
            (target.runId !== runId || target.requestId !== human.request_id))
        )
          return;
        const requestId = human.request_id;
        const value = input.audio
          ? (await transcribe(input.audio, controller.signal)).text
          : input.text || "";
        if (
          controller.signal.aborted ||
          live.pending.current?.request_id !== requestId
        )
          return;
        await humanAnswer(value, human, !!input.audio);
        return;
      }
      const pid = await ensureProfile();
      const userId = ++id.current,
        botId = ++id.current;
      setQuick([]);
      setNotice("");
      setMessages((all) =>
        [
          ...all,
          {
            id: userId,
            from: "user" as const,
            text: input.text || "…",
            cards: [],
          },
          { id: botId, from: "bot" as const, text: "", cards: [] },
        ].slice(-40),
      );
      await streamTalk(
        {
          profile_id: pid,
          ...input,
          lang,
          stream_audio: true,
          context: {
            page: pathname,
            run_id: runId || null,
            pending_step: live.pending.current?.kind || null,
            onboarding,
          },
        },
        (event) => {
          if (controller.signal.aborted) return;
          if (event.type === "transcript") {
            setMessages((all) =>
              all.map((message) =>
                message.id === userId
                  ? { ...message, text: event.text }
                  : message,
              ),
            );
            if (event.lang && event.lang in languages)
              setLang(event.lang as Lang);
          }
          if (event.type === "progress") {
            setNotice(
              event.stage === "finding_schemes"
                ? ui("finding")
                : ui("thinking"),
            );
          }
          if (event.type === "action")
            void execute(event.action).catch((e: Error) => setError(e.message));
          if (event.type === "audio") speech.enqueue(event.audio_url);
          if (event.type === "done") {
            setNotice("");
            setQuick(event.quick_replies || []);
            if (event.audio_url) speech.enqueue(event.audio_url);
            if (onboarding && event.profile && profileComplete(event.profile)) {
              setOnboarding(false);
              navigate("/schemes");
            }
          }
          setMessages((all) => applyTalkEvent(all, event, botId));
        },
        controller.signal,
      );
    } catch (e) {
      if (!controller.signal.aborted) setError((e as Error).message);
    } finally {
      sending.current = false;
      setBusy(false);
    }
  }
  function startMic() {
    speech.unlock();
    speech.stop();
    setOpen(true);
    setError("");
    draftEpoch.current++;
    draftRequest.current?.abort();
    setDraftTranscript("");
    const human = live.pending.current;
    voiceTarget.current = human
      ? { runId, requestId: human.request_id, kind: human.kind }
      : null;
    void recorder.start();
  }
  async function upload(file: File) {
    const current = captureRef.current;
    if (!current) return;
    if (sending.current) {
      pendingUpload.current = file;
      setCamera(false);
      setNotice(ui("reading"));
      return;
    }
    setCamera(false);
    setBusy(true);
    sending.current = true;
    setError("");
    setNotice(ui("reading"));
    try {
      const pid = await ensureProfile();
      const item = await request<LockerItem>("/locker", {
        method: "POST",
        body: uploadForm(pid, file, file.name, current.docType),
      });
      const wrongType =
        item.meta.detected_doc_type &&
        item.meta.detected_doc_type !== current.docType;
      if (item.meta.readable !== true || wrongType) {
        const fix = wrongType
          ? ui("wrongDocument")
          : documentFix(lang, item.meta.issues || []);
        setCapture({ ...current, reason: fix });
        narrate(fix);
        setCamera(true);
        return;
      }
      setCapture(null);
      narrate(ui("ready"));
      if (current.runId) {
        navigate(`/runs/${encodeURIComponent(current.runId)}`);
        if (!live.send({ type: "resume" }, current.requestId))
          setError(ui("disconnected"));
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      sending.current = false;
      setBusy(false);
    }
  }
  const human = live.human;
  return (
    <>
      <div className="fixed bottom-24 right-3 z-50 flex max-w-[calc(100vw-1.5rem)] flex-col items-end gap-3 md:bottom-5 md:right-5">
        {open && (
          <section
            id="buddy-panel"
            aria-label={ui("name")}
            className="flex max-h-[min(70dvh,650px)] w-[min(25rem,calc(100vw-1.5rem))] flex-col overflow-hidden rounded-[28px] border border-line bg-paper shadow-2xl"
          >
            <header className="flex shrink-0 items-center justify-between gap-2 border-b border-line px-4 py-2">
              <strong className="font-serif text-2xl">{ui("name")}</strong>
              <select
                aria-label="Language"
                value={lang}
                className="!m-0 !min-h-11 !w-auto !max-w-32"
                onChange={(e) =>
                  void setLanguage(e.target.value as Lang).catch((err: Error) =>
                    setError(err.message),
                  )
                }
              >
                {Object.entries(languages).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <button
                aria-label={ui("close")}
                onClick={() => setOpen(false)}
                className="!h-11 !w-11 !rounded-full !p-0"
              >
                <X size={20} />
              </button>
            </header>
            <div
              className="flex min-h-20 flex-1 flex-col gap-3 overflow-y-auto p-4"
              aria-live="polite"
              aria-relevant="additions text"
              role="log"
            >
              {messages.length === 0 && (
                <p>{onboarding ? ui("state") : ui("greeting")}</p>
              )}
              {messages.slice(-12).map((message) => (
                <div
                  key={message.id}
                  className={
                    message.from === "user"
                      ? "ml-8 rounded-2xl bg-peach p-3"
                      : "mr-2 rounded-2xl bg-white p-3"
                  }
                  lang={message.lang}
                >
                  <p className="m-0 whitespace-pre-wrap">{message.text}</p>
                  {message.cards.map((card, index) => (
                    <CardView
                      key={index}
                      card={card}
                      lang={lang}
                      disabled={busy}
                      onAnswer={(value) => void submit({ text: value })}
                      onCapture={(docType, reason) =>
                        openCamera(docType, reason)
                      }
                    />
                  ))}
                </div>
              ))}
              {notice && (
                <p role="status" className="m-0 rounded-2xl bg-act-soft p-3">
                  {notice}
                </p>
              )}
              {recorder.recording && draftTranscript && (
                <p role="status" className="m-0 rounded-2xl bg-peach p-3">
                  {draftTranscript}
                </p>
              )}
              {human?.crop && (
                <img
                  src={`data:image/jpeg;base64,${human.crop}`}
                  alt={ui("captcha")}
                  className="max-h-48 w-full rounded-xl object-contain"
                />
              )}
              {confirmation && (
                <div className="flex flex-wrap gap-2">
                  <button onClick={confirmAnswer}>{ui("yes")}</button>
                  <button
                    onClick={() => {
                      setConfirmation(null);
                      narrate(ui("retry"));
                    }}
                  >
                    {ui("no")}
                  </button>
                </div>
              )}
              {capture && !camera && (
                <button
                  disabled={busy}
                  onClick={() => {
                    speech.unlock();
                    setCamera(true);
                    narrate(capture.reason + " " + ui("camera"));
                  }}
                >
                  {ui("retryCamera")}
                </button>
              )}
              {error && (
                <p role="alert" className="m-0 text-bad">
                  {error}
                </p>
              )}
              <div ref={tail} />
            </div>
            <div className="flex shrink-0 flex-col gap-2 border-t border-line p-3">
              {quick.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {quick.map((value) => (
                    <button
                      key={value}
                      disabled={busy}
                      onClick={() => {
                        speech.unlock();
                        void submit({ text: value });
                      }}
                    >
                      {value}
                    </button>
                  ))}
                </div>
              )}
              <button className="secondary self-start" onClick={speech.replay}>
                <Volume2 size={18} />
                {ui("replay")}
              </button>
              <form
                className="flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  speech.unlock();
                  void submit({ text });
                }}
              >
                <input
                  aria-label={ui("type")}
                  placeholder={ui("type")}
                  autoComplete="off"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  className="!m-0 min-w-0 flex-1"
                />
                <button
                  aria-label={ui("send")}
                  disabled={busy || !text.trim()}
                  className="!h-12 !w-12 !p-0"
                >
                  <Send size={20} />
                </button>
              </form>
              <p className="m-0 text-xs text-ink-soft">
                {recorder.recording ? ui("listening") : ui("tap")}
              </p>
            </div>
          </section>
        )}
        <div className="flex items-center gap-2">
          <button
            aria-label={`${ui("name")} ${open ? ui("close") : ui("continue")}`}
            aria-expanded={open}
            aria-controls="buddy-panel"
            onClick={() => {
              speech.unlock();
              setOpen(!open);
              if (!open && !messages.length && !onboarding)
                narrate(ui("greeting"));
            }}
            className="!min-h-11 !rounded-full !bg-white !text-ink shadow-lg"
          >
            {ui("name")}
          </button>
          <button
            type="button"
            disabled={busy}
            aria-label={ui("tap")}
            aria-pressed={recorder.recording}
            onPointerDown={(e) => {
              if (e.button !== 0) return;
              e.currentTarget.setPointerCapture(e.pointerId);
              speech.unlock();
              held.current = false;
              suppressClick.current = false;
              holdTimer.current = setTimeout(() => {
                held.current = true;
                if (!recorder.isActive()) startMic();
              }, HOLD_MS);
            }}
            onPointerUp={() => {
              clearTimeout(holdTimer.current);
              if (held.current) {
                recorder.stop();
                suppressClick.current = true;
              }
            }}
            onPointerCancel={() => {
              clearTimeout(holdTimer.current);
              recorder.cancel();
              suppressClick.current = false;
            }}
            onClick={(e) => {
              if (suppressClick.current && e.detail !== 0) {
                suppressClick.current = false;
                return;
              }
              suppressClick.current = false;
              if (micGesture(recorder.isActive(), 0) === "stop")
                recorder.stop();
              else startMic();
            }}
            onContextMenu={(e) => e.preventDefault()}
            className="relative !h-16 !w-16 touch-none select-none !rounded-full !bg-transparent !p-0 shadow-xl ring-4 ring-white"
          >
            <Orb
              size={64}
              state={
                recorder.recording
                  ? "listening"
                  : speech.speaking
                    ? "speaking"
                    : "idle"
              }
            />
            <Mic
              size={24}
              aria-hidden="true"
              className="absolute inset-0 m-auto text-ink"
            />
          </button>
        </div>
      </div>
      {camera && capture && (
        <CameraCapture
          labels={{
            close: ui("close"),
            capture: ui("capture"),
            choose: ui("choose"),
          }}
          guidance={capture.reason + " " + ui("camera")}
          onCapture={(file) => void upload(file)}
          onClose={() => setCamera(false)}
        />
      )}
    </>
  );
}
