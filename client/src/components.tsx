import { Text } from "./context";
import { Component, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Mic, Square, Volume2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { assetUrl, request, safeUrl } from "./api/client";
import type { Citation, ExplainOut, SttOut } from "./api/types";
import { useApp } from "./context";
import { friendlyError } from "./api/errors";
export function ErrorBox({
  error,
  retry,
}: {
  error: string;
  retry?: () => void;
}) {
  const { t } = useApp();
  return (
    <div className="error" role="alert">
      <strong>
        <Text value="Let’s try that again" />
      </strong>
      <p>
        <Text value={friendlyError(error)} />
      </p>
      {retry && (
        <button className="secondary" onClick={() => retry()}>
          {t.retry}
        </button>
      )}
    </div>
  );
}
export function Loading({ message }: { message?: string } = {}) {
  const { t } = useApp();
  return (
    <div role="status" className="skeletons">
      <span />
      <span />
      <span />
      <p>{message ? <Text value={message} /> : t.loading}</p>
    </div>
  );
}
export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}
export function Markdown({ text }: { text: string }) {
  const { lang } = useApp();
  return (
    <div className="prose">
      <ReactMarkdown
        components={{
          a: ({ href, children }) => (
            <a href={safeUrl(href)} target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {text.replace(/<br\s*\/?>/gi, "\n\n") ||
          (lang === "hi"
            ? "इस भाग की जानकारी अभी उपलब्ध नहीं है।"
            : "No information has been published for this section.")}
      </ReactMarkdown>
    </div>
  );
}
export function Citations({ items }: { items: Citation[] }) {
  return (
    <ol className="citations">
      {items.map((c, i) => (
        <li key={i}>
          <blockquote>“{c.quote}”</blockquote>
          <a href={safeUrl(c.source_url)} target="_blank" rel="noreferrer">
            {c.title || "Official source"} ↗
          </a>
          {c.section && <small> · {c.section}</small>}
        </li>
      ))}
    </ol>
  );
}
export function Explanation({
  data,
  compare,
}: {
  data: ExplainOut;
  compare?: ExplainOut | null;
}) {
  return (
    <div className="explanation grid items-start gap-5 lg:grid-cols-[1.2fr_1fr]">
      <div className="flex flex-col gap-4">
        <article className="rounded-3xl bg-card p-6 shadow-[0_10px_30px_rgba(23,20,15,0.06),0_1px_0_rgba(23,20,15,0.05)] flex flex-col gap-4">
          <span className="eyebrow">
            <Text value={"In plain language"} /> · इन आसान शब्दों में
          </span>
          <h2 className="m-0 font-serif text-3xl font-normal">{data.title}</h2>
          {data.audio_url && (
            <div className="flex flex-wrap items-center gap-3 rounded-2xl bg-[#FFE7D3] p-3 text-saffron-text">
              <span className="inline-flex items-center gap-1.5 text-sm font-semibold">
                <Volume2 size={18} aria-hidden="true" />
                <Text value={"Listen"} /> · सुनें
              </span>
              <audio
                controls
                preload="none"
                src={assetUrl(data.audio_url)}
                className="h-10 flex-1"
              />
            </div>
          )}
          <p className="m-0 text-[17px] leading-relaxed">{data.summary}</p>
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

        {compare && (
          <section className="rounded-3xl bg-card p-6 shadow-[0_10px_30px_rgba(23,20,15,0.06),0_1px_0_rgba(23,20,15,0.05)] flex flex-col gap-3">
            <span className="eyebrow">
              What changed · पुराने सर्कुलर से तुलना
            </span>
            <h3 className="m-0 font-serif text-2xl font-normal">
              {compare.title} → {data.title}
            </h3>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-2xl bg-[#FDE4E0] p-4 text-[#8D1F17]">
                <span className="block text-xs font-bold uppercase tracking-wider">
                  Before · पहले ({compare.title})
                </span>
                <p className="m-0 mt-1.5 text-sm">{compare.summary}</p>
                {compare.key_points.length > 0 && (
                  <ul className="m-0 mt-2 pl-4 text-xs">
                    {compare.key_points.slice(0, 3).map((pt, i) => (
                      <li key={i}>{pt}</li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="rounded-2xl bg-[#DDF3E9] p-4 text-[#155C42]">
                <span className="block text-xs font-bold uppercase tracking-wider">
                  Now · अब ({data.title})
                </span>
                <p className="m-0 mt-1.5 text-sm">{data.summary}</p>
                {data.key_points.length > 0 && (
                  <ul className="m-0 mt-2 pl-4 text-xs">
                    {data.key_points.slice(0, 3).map((pt, i) => (
                      <li key={i}>{pt}</li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </section>
        )}
      </div>

      <aside className="flex flex-col gap-4">
        <section className="rounded-3xl bg-peach p-6 flex flex-col gap-2">
          <span className="eyebrow">
            What this means for you · आपके लिए क्या बदला
          </span>
          <h3 className="m-0 font-serif text-2xl font-normal">
            <Text value={"What this means for you"} />
          </h3>
          <p className="m-0 text-sm leading-relaxed">
            {data.what_it_means_for_you ||
              "Add your profile details on the home page or Talk mode to get personalized impact notes for your household."}
          </p>
        </section>
        <section className="rounded-3xl bg-card p-6 shadow-[0_10px_30px_rgba(23,20,15,0.06),0_1px_0_rgba(23,20,15,0.05)] flex flex-col gap-3">
          <span className="eyebrow">
            Every line is backed by a quote · आधिकारिक प्रमाण
          </span>
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
        {recording ? <Square /> : <Mic />}
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
