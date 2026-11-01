import { useRef, useState } from "react";
import type { ReactNode, KeyboardEvent } from "react";
import { ChevronRight, Volume2 } from "lucide-react";
import { assetUrl } from "./api/client";
import { tt } from "./ui-strings";
import { useApp } from "./context";
import { cx } from "./ui";

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
      className="flex flex-col gap-3 rounded-[22px] bg-act-soft p-4"
    >
      <div className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-act font-bold text-white"
        >
          !
        </span>
        <strong className="flex-1">{title}</strong>
        {src && (
          <>
            <button
              type="button"
              aria-label={tt(lang || uiLang, "playAudio")}
              onClick={() => void audio.current?.play().catch(() => {})}
              className="!min-h-11 grid h-11 w-11 place-items-center rounded-full !bg-white !p-0 !text-act"
            >
              <Volume2 size={20} />
            </button>
            <audio ref={audio} src={src} preload="none" />
          </>
        )}
      </div>
      {crop && (
        <img
          alt={tt(uiLang, "cropAlt")}
          src={`data:image/jpeg;base64,${crop}`}
          className="max-h-40 w-full rounded-[14px] bg-white object-contain"
        />
      )}
      {steps.length > 0 && (
        <ol className="m-0 list-decimal pl-5 text-[16px]">
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
    if (done) return;
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
      className={cx(
        "relative h-16 select-none overflow-hidden rounded-full bg-ink",
        disabled && "opacity-50",
      )}
    >
      <span className="absolute inset-0 grid place-items-center pl-12 text-[15px] font-semibold text-paper">
        {label}
      </span>
      <div
        role="slider"
        tabIndex={disabled ? -1 : 0}
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={done ? 100 : Math.round((x / (max() || 1)) * 100)}
        aria-disabled={disabled}
        onKeyDown={onKey}
        onPointerDown={(e) => {
          if (disabled || done) return;
          e.currentTarget.setPointerCapture(e.pointerId);
          start.current = e.clientX - x;
          setDragging(true);
        }}
        onPointerMove={(e) => {
          if (!dragging) return;
          setX(Math.min(max(), Math.max(0, e.clientX - start.current)));
        }}
        onPointerUp={() => {
          if (!dragging) return;
          setDragging(false);
          if (x >= max() * 0.85) finish();
          else setX(0);
        }}
        onPointerCancel={() => {
          setDragging(false);
          setX(0);
        }}
        className="swipe-handle absolute left-1 top-1 grid h-14 w-14 cursor-grab place-items-center rounded-full bg-lime text-ink"
        style={{
          transform: `translateX(${x}px)`,
          transition: dragging ? "none" : "transform .2s",
        }}
      >
        <ChevronRight aria-hidden="true" />
      </div>
    </div>
  );
}
