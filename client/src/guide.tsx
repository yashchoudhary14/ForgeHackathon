import { useTranslation, useApp } from "./context";
import { useRef, useState } from "react";
import type { ReactNode, KeyboardEvent } from "react";
import { ChevronRight, ChevronsRight, ShieldAlert, Volume2 } from "lucide-react";
import { assetUrl } from "./api/client";
import { tt } from "./ui-strings";

export function GuideCard({
  title,
  steps = [],
  crop,
  audioUrl,
  children,
  lang,
}: {
  title: string;
  steps?: string[];
  crop?: string | null;
  audioUrl?: string | null;
  children?: ReactNode;
  lang?: string;
}) {
  const { lang: uiLang } = useApp();
  const audio = useRef<HTMLAudioElement>(null);
  const src = audioUrl ? assetUrl(audioUrl) : undefined;
  return (
    <div
      lang={lang}
      className="flex flex-col gap-4 rounded-card border-2 border-act bg-card p-4 shadow-[0_0_0_4px_var(--color-act-soft)] sm:p-5"
    >
      <div className="-mx-4 -mt-4 flex items-center gap-3 rounded-t-[16px] bg-act px-4 py-3 text-white sm:-mx-5 sm:-mt-5 sm:px-5">
        <span
          aria-hidden="true"
          className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-saffron text-ink"
        >
          <ShieldAlert size={20} aria-hidden="true" className="shrink-0" />
        </span>
        <strong className="flex-1 font-serif text-xl font-bold leading-tight">{title}</strong>
        {src && (
          <>
            <button
              type="button"
              aria-label={tt(uiLang, "playAudio")}
              onClick={() => void audio.current?.play().catch(() => {})}
              className="!min-h-12 grid h-12 w-12 shrink-0 place-items-center rounded-full !bg-white !p-0 !text-act ring-2 ring-white/40 ring-offset-2 ring-offset-act"
            >
              <Volume2 size={20} aria-hidden="true" />
            </button>
            <audio ref={audio} src={src} preload="none" />
          </>
        )}
      </div>
      {crop && (
        <div className="rounded-tile border-2 border-dashed border-act/50 bg-paper p-3"><img
          alt={tt(uiLang, "cropAlt")}
          src={`data:image/jpeg;base64,${crop}`}
          className="max-h-72 min-h-28 w-full rounded-[8px] bg-white object-contain [image-rendering:auto]"
        /></div>
      )}
      {steps.length > 0 && (
        <ol className="m-0 flex list-none flex-col gap-2 p-0 text-base leading-snug">
          {steps.map((s, i) => (
            <li key={i} className="flex items-start gap-3"><span aria-hidden="true" className="grid h-8 w-8 shrink-0 place-items-center rounded-full border-2 border-act font-serif text-base font-bold text-act">{i + 1}</span><span className="pt-1">{s}</span></li>
          ))}
        </ol>
      )}
      {children}
    </div>
  );
}

/** Real drag on touch and mouse (pointer events); Enter/Space/ArrowRight also confirm. */
export function SwipeToConfirm({
  label,
  onConfirm,
  disabled,
}: {
  label: string;
  onConfirm: () => void;
  disabled?: boolean;
}) {
  const tr = useTranslation();
  const track = useRef<HTMLDivElement>(null);
  const [x, setX] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [done, setDone] = useState(false);
  const start = useRef(0);
  const HANDLE = 56;
  const max = () =>
    Math.max(0, (track.current?.clientWidth ?? 280) - HANDLE - 8);
  const finish = () => {
    if (done || disabled) return;
    setDone(true);
    setX(max());
    onConfirm();
  };
  const onKey = (e: KeyboardEvent) => {
    if (disabled || done) return;
    if (["Enter", " ", "ArrowRight"].includes(e.key)) {
      e.preventDefault();
      finish();
    }
  };
  return (
    <div
      ref={track}
      className="swipe-track relative min-h-16 select-none overflow-hidden rounded-full border-2 border-ok bg-ok-soft data-[disabled=true]:border-line data-[disabled=true]:bg-paper data-[disabled=true]:opacity-70"
      data-disabled={disabled ? "true" : "false"}
    >
      <span aria-hidden="true" className="pointer-events-none absolute inset-y-0 left-0 rounded-full bg-ok/20" style={{ width: x + HANDLE }} />
      <span className="swipe-label relative flex min-h-16 items-center justify-center py-3 pl-16 pr-10 text-center text-base font-semibold text-ok">
        {label}
      </span>
      <ChevronsRight size={22} aria-hidden="true" className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-ok" />
      <div
        role="slider"
        tabIndex={disabled || done ? -1 : 0}
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={done ? 100 : Math.round((x / (max() || 1)) * 100)}
        aria-disabled={disabled || done}
        aria-valuetext={done ? tr("Confirmed") : label}
        onKeyDown={onKey}
        onPointerDown={(e) => {
          if (disabled || done) return;
          e.currentTarget.setPointerCapture(e.pointerId);
          start.current = e.clientX - x;
          setDragging(true);
        }}
        onPointerMove={(e) => {
          if (!dragging || disabled || done) return;
          setX(Math.min(max(), Math.max(0, e.clientX - start.current)));
        }}
        onPointerUp={() => {
          if (!dragging || disabled || done) { setDragging(false); setX(0); return; }
          setDragging(false);
          if (x >= max() * 0.85) finish();
          else setX(0);
        }}
        onPointerCancel={() => {
          setDragging(false);
          setX(0);
        }}
        className="swipe-handle absolute grid cursor-grab touch-none place-items-center rounded-full bg-ok text-white shadow-[0_2px_6px_rgba(20,27,52,0.25)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-act active:cursor-grabbing"
        style={{
          width: HANDLE,
          height: HANDLE,
          left: 4,
          top: "50%",
          transform: `translate(${x}px, -50%)`,
          transition: dragging ? "none" : "transform .2s",
        }}
      >
        <ChevronRight size={24} aria-hidden="true" className="shrink-0" />
      </div>
    </div>
  );
}
