import { useRef, useState } from "react";
import type { ReactNode, KeyboardEvent } from "react";
import { ChevronRight, ChevronsRight, ShieldAlert, Volume2 } from "lucide-react";
import { assetUrl } from "./api/client";
import { tt } from "./ui-strings";
import { useApp } from "./context";

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
      className="flex flex-col gap-4 rounded-[22px] border-2 border-act/30 bg-act-soft p-4 shadow-md sm:p-5"
    >
      <div className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[#2a5fc4] text-white"
        >
          <ShieldAlert size={20} aria-hidden="true" className="shrink-0" />
        </span>
        <strong className="flex-1">{title}</strong>
        {src && (
          <>
            <button
              type="button"
              aria-label={tt(lang || uiLang, "playAudio")}
              onClick={() => void audio.current?.play().catch(() => {})}
              className="!min-h-12 grid h-12 w-12 place-items-center rounded-full !bg-white !p-0 !text-[#1f4fa8]"
            >
              <Volume2 size={20} aria-hidden="true" />
            </button>
            <audio ref={audio} src={src} preload="none" />
          </>
        )}
      </div>
      {crop && (
        <div className="rounded-2xl border border-line bg-white p-3"><img
          alt={tt(uiLang, "cropAlt")}
          src={`data:image/jpeg;base64,${crop}`}
          className="max-h-56 min-h-24 w-full rounded-xl object-contain"
        /></div>
      )}
      {steps.length > 0 && (
        <ol className="m-0 list-decimal pl-5 text-base">
          {steps.map((s, i) => (
            <li key={i}>{s}</li>
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
      className="swipe-track relative min-h-16 select-none overflow-hidden rounded-full bg-ink"
      data-disabled={disabled ? "true" : "false"}
    >
      <span aria-hidden="true" className="pointer-events-none absolute inset-y-0 left-0 rounded-full bg-lime/25" style={{ width: x + HANDLE }} />
      <span className="swipe-label relative flex min-h-16 items-center justify-center py-3 pl-16 pr-10 text-center text-sm font-semibold text-paper">
        {label}
      </span>
      <ChevronsRight size={22} aria-hidden="true" className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-lime animate-pulse motion-reduce:animate-none" />
      <div
        role="slider"
        tabIndex={disabled || done ? -1 : 0}
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={done ? 100 : Math.round((x / (max() || 1)) * 100)}
        aria-disabled={disabled || done}
        aria-valuetext={done ? "Confirmed" : label}
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
        className="swipe-handle absolute grid cursor-grab place-items-center rounded-full bg-lime text-ink"
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
