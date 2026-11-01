import { useTranslation, Text, useApp } from "./context";
import { Component, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { AlertTriangle, ArrowRight, History, Loader2, Mic, Square, Volume2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { assetUrl, request } from "./api/client";
import type {
  Citation,
  DocumentChange,
  ExplainedClaim,
  ExplainOut,
  SttOut,
} from "./api/types";
import { friendlyError } from "./api/errors";
import { Card, EmptyState, PillButton, SourceLink } from "./ui";
export function ErrorBox({
  error,
  retry,
}: {
  error: string;
  retry?: () => void;
}) {
  const { t } = useApp();
  return (
    <div className="my-4 flex flex-col justify-between gap-4 rounded-card border border-[#f2c4bf] border-l-[6px] border-l-bad bg-bad-soft p-5 text-bad sm:flex-row sm:items-center" role="alert">
      <div className="flex min-w-0 items-start gap-3">
        <AlertTriangle size={24} strokeWidth={1.75} aria-hidden="true" className="shrink-0" />
        <div>
          <strong className="font-serif text-lg font-semibold leading-tight"><Text value="Let’s try that again" /></strong>
          <p className="m-0 mt-1 max-w-[65ch] text-ink">
            <Text value={friendlyError(error)} />
          </p>
        </div>
      </div>
      {retry && (
        <PillButton tone="light" className="self-start shrink-0" onClick={() => retry()}>
          {t.retry}
        </PillButton>
      )}
    </div>
  );
}
export function Loading({ message }: { message?: string } = {}) {
  const { t } = useApp();
  return (
    <div role="status" aria-live="polite" className="my-4">
      <Card className="flex flex-col gap-4">
        <p className="m-0 inline-flex min-h-11 items-center gap-2 self-start rounded-full border border-[#c3cbf0] bg-act-soft px-3.5 py-2 text-sm font-semibold text-act">
          <Loader2 size={18} aria-hidden="true" className="shrink-0 animate-spin motion-reduce:animate-none" />
          {message ? <Text value={message} /> : t.loading}
        </p>
        <div aria-hidden="true" className="flex flex-col gap-3 animate-pulse motion-reduce:animate-none">
          <span className="h-6 w-2/3 rounded-[8px] bg-line" />
          <span className="h-4 w-full rounded-[8px] bg-line/70" />
          <span className="h-4 w-4/5 rounded-[8px] bg-line/70" />
        </div>
      </Card>
    </div>
  );
}
export function Empty({ children }: { children: ReactNode }) {
  return <EmptyState>{children}</EmptyState>;
}
export function Markdown({ text }: { text: string }) {
  const tr = useTranslation();
  return (
    <div className="prose">
      <ReactMarkdown
        components={{
          a: ({ href, children }) => (
            <SourceLink url={href}>{children}</SourceLink>
          ),
        }}
      >
        {text.replace(/<br\s*\/?>/gi, "\n\n") ||
          tr("No information has been published for this section.")}
      </ReactMarkdown>
    </div>
  );
}
export function Citations({ items }: { items: Citation[] }) {
  return (
    <ol className="citations m-0 flex flex-col gap-1 marker:font-bold marker:text-act">
      {items.map((c, i) => (
        <li key={i}>
          <Quote citation={c} />
        </li>
      ))}
    </ol>
  );
}
export function Quote({ citation }: { citation: Citation }) {
  return (
    <blockquote className="m-0 mt-2 rounded-[8px] border border-line border-l-4 border-l-saffron bg-paper px-3.5 py-2.5 text-sm text-ink-soft">
      <p className="m-0 text-ink">“{citation.quote}”</p>
      <footer className="mt-2 flex flex-wrap items-center gap-2">
        <SourceLink url={citation.source_url}>
          {[citation.title, citation.section].filter(Boolean).join(" · ") || undefined}
        </SourceLink>
      </footer>
    </blockquote>
  );
}
const claimGroups: [keyof ExplainOut, string][] = [
  ["rights", "Your rights"],
  ["duties", "Your duties"],
  ["restrictions", "Restrictions"],
  ["deadline_details", "Deadlines"],
  ["how_to_apply", "How to apply"],
  ["document_details", "Documents"],
];
/** Explainer sections where every claim carries its verified quote. */
export function ClaimSections({ data }: { data: ExplainOut }) {
  const groups = claimGroups
    .map(([key, title]) => [title, (data[key] as ExplainedClaim[] | undefined) ?? []] as const)
    .filter(([, items]) => items.length > 0);
  if (!groups.length) return null;
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {groups.map(([title, items]) => (
        <section key={title} className="flex min-w-0 flex-col gap-2 rounded-3xl bg-card p-5 shadow-[inset_0_0_0_1px_#dce1ec]">
          <h3 className="m-0 font-serif text-xl font-normal"><Text value={title} /></h3>
          <ul className="m-0 flex flex-col gap-3 pl-5 text-sm">
            {items.map((c, i) => (
              <li key={i} className="break-words">
                {c.text}
                <Quote citation={c.citation} />
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
/** Compare mode: what changed between the old and new document, both sides quoted. */
export function ChangeList({ changes }: { changes: DocumentChange[] }) {
  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-card p-5 shadow-[inset_0_0_0_1px_#dce1ec]">
      <span className="eyebrow"> <Text value="What changed" /> </span>
      {changes.map((c, i) => (
        <article key={i} className="flex min-w-0 flex-col gap-2 border-t border-line pt-3 first:border-0 first:pt-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="m-0 font-serif text-xl font-normal">{c.title}</h3>
            {c.affects_profile === true && (
              <span className="rounded-full bg-warn-soft px-2.5 py-0.5 text-xs font-semibold text-warn"> <Text value="Affects you" /> </span>
            )}
          </div>
          <p className="m-0 text-sm">{c.description}</p>
          {c.impact && <p className="m-0 text-sm text-ink-soft">{c.impact}</p>}
          <div className="grid gap-2 md:grid-cols-2">
            <div className="min-w-0 rounded-2xl border border-[#f2c4bf] bg-bad-soft/60 p-3 text-bad">
              <span className="inline-flex items-center gap-1.5 text-xs font-bold"><History size={16} aria-hidden="true" className="shrink-0" /> <Text value="Before" /> </span>
              <Quote citation={c.old_citation} />
            </div>
            <div className="min-w-0 rounded-2xl border border-[#b7e0cb] bg-ok-soft/60 p-3 text-ok">
              <span className="inline-flex items-center gap-1.5 text-xs font-bold"><ArrowRight size={16} aria-hidden="true" className="shrink-0" /> <Text value="Now" /> </span>
              <Quote citation={c.new_citation} />
            </div>
          </div>
        </article>
      ))}
    </section>
  );
}
export function Explanation({ data }: { data: ExplainOut }) {
  const tr = useTranslation();
  return (
    <div lang={data.language} className="explanation grid items-start gap-5 lg:grid-cols-[1.2fr_1fr]">
      <div className="flex flex-col gap-4">
        <article className="rounded-3xl bg-card p-6 shadow-[0_10px_30px_rgba(23,20,15,0.06),0_1px_0_rgba(23,20,15,0.05)] flex flex-col gap-4">
          <span className="eyebrow">
            <Text value={"In plain language"} />
          </span>
          <h2 className="m-0 font-serif text-3xl font-normal">{data.title}</h2>
          {data.audio_url && (
            <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-[#f5dd9e] bg-peach p-3 text-saffron-text">
              <span className="inline-flex items-center gap-1.5 text-sm font-semibold">
                <Volume2 size={18} aria-hidden="true" />
                <Text value={"Listen"} />
              </span>
              <audio
                controls
                preload="none"
                src={assetUrl(data.audio_url)}
                aria-label={tr("Listen to this explanation")}
                className="!m-0 h-12 min-w-0 basis-48 flex-1"
              />
            </div>
          )}
          <p className="m-0 text-base leading-relaxed">{data.summary}</p>
          <div className="grid gap-3 md:grid-cols-2">
            {[
              ["Key points", data.key_points],
              ["Your rights", data.your_rights],
              ["Deadlines", data.deadlines],
              ["Documents you need", data.documents_needed],
            ].map(
              ([title, items]) =>
                (items as string[]).length > 0 && (
                  <section
                    key={title as string}
                    className="rounded-2xl bg-paper p-4"
                  >
                    <h3 className="m-0 mb-2 font-serif text-xl font-normal">
                      <Text value={title as string} />
                    </h3>
                    <ul className="m-0 pl-5 text-sm leading-relaxed">
                      {(items as string[]).map((s, i) => (
                        <li key={i}>{s}</li>
                      ))}
                    </ul>
                  </section>
                ),
            )}
          </div>
        </article>

        <ClaimSections data={data} />
        {!!data.changes?.length && <ChangeList changes={data.changes} />}
      </div>

      <aside className="flex flex-col gap-4">
        <section className="rounded-3xl bg-peach p-6 flex flex-col gap-2">
          <span className="eyebrow">
             <Text value="What this means for you" /> </span>
          <h3 className="m-0 font-serif text-2xl font-normal">
            <Text value={"What this means for you"} />
          </h3>
          <p className="m-0 text-sm leading-relaxed">
            {data.what_it_means_for_you ||
              tr("Add your profile details on the home page or Talk mode to get personalized impact notes for your household.")}
          </p>
          {!!data.personal_impacts?.length && (
            <ul className="m-0 flex flex-col gap-2 pl-5 text-sm">
              {data.personal_impacts.map((c, i) => (
                <li key={i} className="break-words">
                  {c.text}
                  <Quote citation={c.citation} />
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="rounded-3xl bg-card p-6 shadow-[0_10px_30px_rgba(23,20,15,0.06),0_1px_0_rgba(23,20,15,0.05)] flex flex-col gap-3">
          <span className="eyebrow">
             <Text value="Every line is backed by a quote" /> </span>
          <Citations items={data.citations} />
        </section>
      </aside>
    </div>
  );
}
export function MicButton({
  onText,
  disabled = false,
}: {
  onText: (text: string) => void;
  disabled?: boolean;
}) {
  const { lang, t } = useApp();
  const [recording, setRecording] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const recorder = useRef<MediaRecorder | null>(null),
    stream = useRef<MediaStream | null>(null),
    alive = useRef(true),
    timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined),
    controller = useRef<AbortController | null>(null);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      clearTimeout(timer.current);
      controller.current?.abort();
      if (recorder.current?.state === "recording") recorder.current.stop();
      stream.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);
  async function start() {
    setError("");
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError(
        "Voice recording is unavailable in this browser. Please type your message.",
      );
      return;
    }
    try {
      setBusy(true);
      const media = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!alive.current) {
        media.getTracks().forEach((t) => t.stop());
        return;
      }
      stream.current = media;
      const rec = new MediaRecorder(media);
      recorder.current = rec;
      const chunks: BlobPart[] = [];
      rec.ondataavailable = (e) => {
        if (e.data.size) chunks.push(e.data);
      };
      rec.onstop = async () => {
        clearTimeout(timer.current);
        media.getTracks().forEach((t) => t.stop());
        if (!alive.current) return;
        setRecording(false);
        setBusy(true);
        try {
          const form = new FormData();
          const extension = rec.mimeType.includes("mp4")
            ? "m4a"
            : rec.mimeType.includes("ogg")
              ? "ogg"
              : "webm";
          form.append(
            "audio",
            new Blob(chunks, { type: rec.mimeType }),
            `recording.${extension}`,
          );
          form.append("language", lang);
          controller.current = new AbortController();
          const out = await request<SttOut>("/voice/stt", {
            method: "POST",
            body: form,
            signal: controller.current.signal,
          });
          if (alive.current) onText(out.text);
        } catch (e) {
          if (alive.current)
            setError(e instanceof Error ? e.message : "Transcription failed.");
        } finally {
          if (alive.current) setBusy(false);
        }
      };
      rec.start();
      setRecording(true);
      timer.current = setTimeout(() => {
        if (rec.state === "recording") rec.stop();
      }, 29000);
    } catch (e) {
      stream.current?.getTracks().forEach((t) => t.stop());
      setError(
        e instanceof DOMException && e.name === "NotAllowedError"
          ? "Microphone permission was denied. Allow microphone access in your browser or type below."
          : "Could not access the microphone. Please type below.",
      );
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  return (
    <div>
      <button
        type="button"
        className={`mic ${recording ? "recording" : ""}`}
        disabled={disabled || busy}
        onClick={() => (recording ? recorder.current?.stop() : void start())}
        aria-pressed={recording}
      >
        {recording ? <Square size={24} aria-hidden="true" className="shrink-0" /> : <Mic size={24} aria-hidden="true" className="shrink-0" />}
        {busy ? (
          <Text value="Preparing your voice message…" />
        ) : recording ? (
          t.stop
        ) : (
          t.mic
        )}
      </button>
      {recording && (
        <p role="status">
          <Text
            value={"Recording… tap stop when finished. Maximum 29 seconds."}
          />
        </p>
      )}
      {error && <ErrorBox error={error} retry={() => void start()} />}
    </div>
  );
}
export class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: boolean }
> {
  state = { error: false };
  static getDerivedStateFromError() {
    return { error: true };
  }
  render() {
    return this.state.error ? (
      <main className="panel">
        <h1>
          <Text value={"Something went wrong"} />
        </h1>
        <p>
          <Text value={"Please reload this page to continue."} />
        </p>
        <button onClick={() => location.reload()}>
          <Text value={"Reload"} />
        </button>
      </main>
    ) : (
      this.props.children
    );
  }
}
