import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  FileText,
  MapPin,
  Mic,
  Send,
  Sparkles,
  Volume2,
  X,
} from "lucide-react";
import { applyTalkEvent, streamTalk } from "../api/talk";
import { request } from "../api/client";
import { uploadForm } from "../api/locker";
import type { LockerItem } from "../api/locker";
import { saveMode } from "../api/profile";
import type { Human, Lang, SttOut } from "../api/types";
import { languages, useApp } from "../context";
import { Orb, TextSizeToggle } from "../ui";
import { tt } from "../ui-strings";
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
    const onPrompt = (e: Event) => {
      const custom = e as CustomEvent<{ text?: string }>;
      const promptText = custom.detail?.text?.trim();
      speech.unlock();
      setOpen(true);
      if (promptText) void submit({ text: promptText });
    };
    window.addEventListener("buddy:prompt", onPrompt);
    return () => window.removeEventListener("buddy:prompt", onPrompt);
  }, [lang, pathname]);
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
  const isTalkPage = pathname.replace(/\/+$/, "") === "/talk";
  const panelOpen = open || isTalkPage;
  const orbState = recorder.recording
    ? "listening"
    : speech.speaking
      ? "speaking"
      : "idle";
  const promptKey =
    pathname === "/"
      ? "dockPromptHome"
      : pathname === "/schemes"
        ? "dockPromptSchemes"
        : pathname.startsWith("/schemes/")
          ? "dockPromptSchemeDetail"
          : pathname.startsWith("/explain")
            ? "dockPromptExplain"
            : pathname.startsWith("/civic")
              ? "dockPromptCivic"
              : pathname.startsWith("/locker")
                ? "dockPromptLocker"
                : pathname.startsWith("/profile")
                  ? "dockPromptProfile"
                  : "dockPromptHome";
  const starterItems = [
    { key: "starterSchemes", Icon: Sparkles },
    { key: "starterNotice", Icon: FileText },
    { key: "starterCivic", Icon: MapPin },
  ] as const;
  const quickLangs: { code: Lang; short: string }[] = [
    { code: "en", short: "EN" },
    { code: "hi", short: "हिं" },
    { code: "bn", short: "বাং" },
    { code: "as", short: "অস" },
  ];

  function handleMicPointerDown(e: React.PointerEvent<HTMLButtonElement>) {
    if (e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    speech.unlock();
    held.current = false;
    suppressClick.current = false;
    holdTimer.current = setTimeout(() => {
      held.current = true;
      if (!recorder.isActive()) startMic();
    }, HOLD_MS);
  }
  function handleMicPointerUp() {
    clearTimeout(holdTimer.current);
    if (held.current) {
      recorder.stop();
      suppressClick.current = true;
    }
  }
  function handleMicPointerCancel() {
    clearTimeout(holdTimer.current);
    recorder.cancel();
    suppressClick.current = false;
  }
  function handleMicClick(e: React.MouseEvent<HTMLButtonElement>) {
    if (suppressClick.current && e.detail !== 0) {
      suppressClick.current = false;
      return;
    }
    suppressClick.current = false;
    if (micGesture(recorder.isActive(), 0) === "stop") recorder.stop();
    else startMic();
  }

  return (
    <>
      <div
        className={
          isTalkPage
            ? "fixed inset-0 z-40 flex flex-col bg-paper"
            : "fixed bottom-[4.75rem] left-1/2 z-30 flex w-[calc(100%-1.5rem)] max-w-md -translate-x-1/2 flex-col items-stretch gap-2.5 md:bottom-5 md:right-6 md:left-auto md:w-auto md:max-w-[calc(100vw-2rem)] md:translate-x-0 md:items-end"
        }
      >
        {panelOpen && (
          <section
            id="buddy-panel"
            aria-label={ui("name")}
            className={
              isTalkPage
                ? "flex h-full w-full flex-col overflow-hidden bg-paper"
                : "flex max-h-[min(68dvh,620px)] w-full flex-col overflow-hidden rounded-[28px] border border-[#e5dac8] bg-paper shadow-2xl md:w-[26rem]"
            }
          >
            <header className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-line bg-paper/95 px-4 py-2.5 backdrop-blur">
              <div className="flex items-center gap-2">
                <strong className="font-serif text-2xl font-normal tracking-[-0.02em] text-ink">
                  Buddy<span className="text-saffron">.</span>
                </strong>
                <span className="rounded-full border border-[#f3d2b8] bg-peach px-2.5 py-0.5 text-xs font-semibold text-saffron-text">
                  {tt(lang, "voiceCompanion")}
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <div className="hidden items-center rounded-full border border-line bg-white p-0.5 sm:flex">
                  {quickLangs.map(({ code, short }) => (
                    <button
                      key={code}
                      type="button"
                      onClick={() =>
                        void setLanguage(code).catch((err: Error) =>
                          setError(err.message),
                        )
                      }
                      className={
                        "!min-h-9 !min-w-9 !rounded-full !px-2.5 !py-1 text-xs font-semibold " +
                        (lang === code
                          ? "!bg-ink !text-paper"
                          : "!bg-transparent !text-ink-soft")
                      }
                    >
                      {short}
                    </button>
                  ))}
                </div>
                <select
                  aria-label="Language"
                  value={lang}
                  className="!m-0 !min-h-11 !w-auto !max-w-28 !rounded-full !px-2.5 !py-1 text-xs font-semibold"
                  onChange={(e) =>
                    void setLanguage(e.target.value as Lang).catch(
                      (err: Error) => setError(err.message),
                    )
                  }
                >
                  {Object.entries(languages).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                {isTalkPage && <TextSizeToggle />}
                <button
                  type="button"
                  aria-label={ui("close")}
                  onClick={() => {
                    setOpen(false);
                    if (isTalkPage) navigate("/");
                  }}
                  className="secondary !min-h-11 !rounded-full !px-3 !py-1.5 text-xs font-semibold"
                >
                  <X size={18} aria-hidden="true" />
                  {isTalkPage && (
                    <span className="hidden sm:inline">
                      {tt(lang, "exitTalk")}
                    </span>
                  )}
                </button>
              </div>
            </header>
            <div
              className={
                "flex min-h-20 flex-1 flex-col gap-3 overflow-y-auto p-4 " +
                (isTalkPage ? "mx-auto w-full max-w-2xl md:px-6" : "")
              }
              aria-live="polite"
              aria-relevant="additions text"
              role="log"
            >
              {messages.length === 0 && (
                <div className="my-auto flex flex-col items-center gap-4 py-4 text-center">
                  <div className="relative flex flex-col items-center justify-center rounded-full bg-[radial-gradient(circle_at_center,rgba(247,163,92,0.24)_0%,transparent_70%)] p-5">
                    <button
                      type="button"
                      disabled={busy}
                      aria-label={ui("tap")}
                      aria-pressed={recorder.recording}
                      onPointerDown={handleMicPointerDown}
                      onPointerUp={handleMicPointerUp}
                      onPointerCancel={handleMicPointerCancel}
                      onClick={handleMicClick}
                      onContextMenu={(e) => e.preventDefault()}
                      className="relative !h-[152px] !w-[152px] touch-none select-none !rounded-full !bg-transparent !p-0 shadow-2xl ring-4 ring-white"
                    >
                      <Orb size={152} state={orbState} />
                      <Mic
                        size={36}
                        aria-hidden="true"
                        className="absolute inset-0 m-auto text-ink"
                      />
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={handleMicClick}
                      className="-mt-4 z-10 !min-h-10 !rounded-full !bg-ink !px-4 !py-1.5 text-xs font-semibold !text-paper shadow-md"
                    >
                      {recorder.recording
                        ? tt(lang, "listening")
                        : tt(lang, "holdToTalk")}
                    </button>
                  </div>
                  <div className="flex flex-col gap-1">
                    <h1 className="m-0 font-serif text-3xl font-normal text-ink sm:text-4xl">
                      {onboarding ? ui("state") : tt(lang, "talkGreeting")}
                    </h1>
                    <p className="m-0 max-w-md text-sm text-ink-soft sm:text-base">
                      {onboarding ? ui("greeting") : tt(lang, "talkWelcome")}
                    </p>
                  </div>
                  {!onboarding && (
                    <div className="mt-1 flex w-full max-w-md flex-col gap-2">
                      {starterItems.map(({ key, Icon }) => {
                        const label = tt(lang, key);
                        return (
                          <button
                            key={key}
                            type="button"
                            disabled={busy}
                            onClick={() => {
                              speech.unlock();
                              void submit({ text: label });
                            }}
                            className="secondary flex !min-h-12 w-full items-center justify-between gap-3 !rounded-2xl border border-line !bg-white !px-4 !py-3 text-left text-sm font-medium !text-ink shadow-xs transition-colors hover:border-saffron"
                          >
                            <span className="flex items-center gap-3">
                              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-peach text-saffron-text">
                                <Icon size={16} aria-hidden="true" />
                              </span>
                              <span>{label}</span>
                            </span>
                            <span aria-hidden="true" className="text-saffron-text">
                              →
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
              {messages.slice(-12).map((message) => (
                <div
                  key={message.id}
                  className={
                    message.from === "user"
                      ? "ml-8 rounded-[22px_22px_6px_22px] bg-ink p-3.5 text-paper"
                      : "mr-2 rounded-[22px_22px_22px_6px] bg-white p-3.5 text-ink shadow-[inset_0_0_0_1px_#ede5da]"
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
                <p role="status" className="m-0 rounded-2xl bg-act-soft p-3 text-sm font-medium text-ink">
                  {notice}
                </p>
              )}
              {recorder.recording && draftTranscript && (
                <p role="status" className="m-0 rounded-2xl bg-peach p-3 text-sm">
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
            <div
              className={
                "flex shrink-0 flex-col gap-2.5 border-t border-line bg-paper p-3 " +
                (isTalkPage ? "mx-auto w-full max-w-2xl md:px-6 md:pb-5" : "")
              }
            >
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
              <div className="flex flex-wrap items-center justify-between gap-2">
                <button
                  type="button"
                  className="secondary !min-h-11 self-start !rounded-full !px-3.5 text-xs"
                  onClick={speech.replay}
                >
                  <Volume2 size={16} aria-hidden="true" />
                  {ui("replay")}
                </button>
                {messages.length > 0 && (
                  <button
                    type="button"
                    disabled={busy}
                    aria-label={ui("tap")}
                    aria-pressed={recorder.recording}
                    onPointerDown={handleMicPointerDown}
                    onPointerUp={handleMicPointerUp}
                    onPointerCancel={handleMicPointerCancel}
                    onClick={handleMicClick}
                    onContextMenu={(e) => e.preventDefault()}
                    className="inline-flex !min-h-11 items-center gap-2 !rounded-full !bg-saffron !px-4 !py-1.5 text-xs font-semibold !text-ink shadow-sm"
                  >
                    <Mic size={16} aria-hidden="true" />
                    {recorder.recording
                      ? tt(lang, "listening")
                      : tt(lang, "holdToTalk")}
                  </button>
                )}
              </div>
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
                  className="!m-0 min-w-0 flex-1 !rounded-full !px-4"
                />
                <button
                  aria-label={ui("send")}
                  disabled={busy || !text.trim()}
                  className="!h-12 !w-12 shrink-0 !rounded-full !p-0"
                >
                  <Send size={18} aria-hidden="true" />
                </button>
              </form>
              <p className="m-0 text-center text-xs text-ink-soft">
                {recorder.recording ? ui("listening") : ui("tap")}
              </p>
            </div>
          </section>
        )}
        {!isTalkPage && (
          <div className="flex w-full items-center justify-between gap-2.5 rounded-full border border-[#e5dac8] bg-white/95 px-2.5 py-1.5 shadow-lg backdrop-blur-md md:w-auto">
            <button
              type="button"
              disabled={busy}
              aria-label={ui("tap")}
              aria-pressed={recorder.recording}
              onPointerDown={handleMicPointerDown}
              onPointerUp={handleMicPointerUp}
              onPointerCancel={handleMicPointerCancel}
              onClick={handleMicClick}
              onContextMenu={(e) => e.preventDefault()}
              className="relative !h-11 !w-11 shrink-0 touch-none select-none !rounded-full !bg-transparent !p-0 shadow-sm ring-2 ring-peach"
            >
              <Orb size={44} state={orbState} />
              <Mic
                size={18}
                aria-hidden="true"
                className="absolute inset-0 m-auto text-ink"
              />
            </button>
            <button
              type="button"
              aria-label={`${ui("name")} ${open ? ui("close") : ui("continue")}`}
              aria-expanded={open}
              aria-controls="buddy-panel"
              onClick={() => {
                speech.unlock();
                setOpen(!open);
                if (!open && !messages.length && !onboarding)
                  narrate(ui("greeting"));
              }}
              className="flex !min-h-11 min-w-0 flex-1 flex-col items-start justify-center !rounded-2xl !bg-transparent !px-2 !py-1 text-left !text-ink shadow-none"
            >
              <span className="max-w-[230px] truncate text-xs font-semibold text-ink sm:max-w-[280px]">
                {recorder.recording
                  ? tt(lang, "listening")
                  : tt(lang, promptKey)}
              </span>
              <span className="max-w-[230px] truncate text-[11px] font-normal text-ink-soft sm:max-w-[280px]">
                {tt(lang, "dockSubtitle")}
              </span>
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={handleMicClick}
              className="inline-flex !min-h-11 shrink-0 items-center gap-1.5 !rounded-full !bg-saffron !px-3.5 !py-1.5 text-xs font-semibold !text-ink"
            >
              <Mic size={15} aria-hidden="true" />
              <span>{tt(lang, "speakBtn")}</span>
            </button>
          </div>
        )}
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
