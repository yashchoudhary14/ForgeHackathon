import { useState } from "react";
import { Mic, Send, Volume2 } from "lucide-react";
import { Orb } from "../ui";
import type { OrbState } from "../ui";
import { tt } from "../ui-strings";

/** Bottom area of Talk mode: quick replies, hold-to-talk orb, text fallback. */
export default function TalkDock({
  lang,
  orb,
  listening,
  busy,
  status,
  quick,
  onHoldStart,
  onHoldEnd,
  onSend,
}: {
  lang: string;
  orb: OrbState;
  listening: boolean;
  busy: boolean;
  status: string;
  quick: string[];
  onHoldStart: () => void;
  onHoldEnd: () => void;
  onSend: (text: string) => void;
}) {
  const [text, setText] = useState("");
  const submit = (v: string) => {
    if (!v.trim() || busy) return;
    setText("");
    onSend(v);
  };
  return (
    <div className="sticky bottom-0 flex shrink-0 flex-col items-center gap-3 bg-gradient-to-t from-paper via-paper/95 to-transparent px-4 pb-6 pt-3">
      {quick.length > 0 && (
        <div className="flex max-w-xl flex-wrap justify-center gap-2">
          {quick.map((q) => (
            <button
              key={q}
              type="button"
              disabled={busy}
              onClick={() => submit(q)}
              className="!bg-white !text-ink shadow-[inset_0_0_0_1px_#d9cfc0] transition-transform active:scale-[0.98] motion-reduce:transition-none"
            >
              {q}
            </button>
          ))}
        </div>
      )}
      <button
        type="button"
        aria-label={tt(lang, "holdToTalk")}
        aria-pressed={listening}
        disabled={busy}
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture?.(e.pointerId);
          onHoldStart();
        }}
        onPointerUp={onHoldEnd}
        onPointerCancel={onHoldEnd}
        onKeyDown={(e) => {
          if ((e.key === " " || e.key === "Enter") && !e.repeat) {
            e.preventDefault();
            onHoldStart();
          }
        }}
        onKeyUp={(e) => {
          if (e.key === " " || e.key === "Enter") onHoldEnd();
        }}
        onContextMenu={(e) => e.preventDefault()}
        className="relative !h-auto !rounded-full !bg-transparent !p-0 touch-none select-none ring-4 ring-white/60 transition-transform active:scale-95 motion-reduce:transition-none"
      >
        <Orb state={orb} size={listening ? 132 : 112} />
        {orb === "speaking" ? <Volume2 aria-hidden="true" className="absolute inset-0 m-auto text-ink" size={34} /> : <Mic
          aria-hidden="true"
          className="absolute inset-0 m-auto text-ink"
          size={34}
        />}
      </button>
      <span role="status" className="inline-flex items-center gap-2 rounded-full bg-white/90 px-4 py-1.5 text-sm font-semibold text-ink shadow-sm">
        <span aria-hidden="true" className={"h-2 w-2 shrink-0 rounded-full " + (listening ? "bg-saffron animate-pulse motion-reduce:animate-none" : orb === "speaking" ? "bg-act" : "bg-ink/40")} />
        {status}
      </span>
      <form
        className="flex w-full max-w-xl gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit(text);
        }}
      >
        <label htmlFor="talk-text" className="sr-only">
          {tt(lang, "typeInstead")}
        </label>
        <input
          id="talk-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={tt(lang, "typePlaceholder")}
          autoComplete="off"
          className="!m-0 min-w-0 flex-1 !rounded-full !px-5 !text-base"
        />
        <button
          type="submit"
          aria-label={tt(lang, "send")}
          disabled={!text.trim() || busy}
          className="!min-h-12 !w-12 shrink-0 !rounded-full !p-0"
        >
          <Send size={18} aria-hidden="true" />
        </button>
      </form>
    </div>
  );
}
