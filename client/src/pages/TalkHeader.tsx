import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { X } from "lucide-react";
import { languages } from "../context";
import { tt } from "../ui-strings";
import { TextSizeToggle } from "../ui";

// Assamese is not an interface language elsewhere but Talk mode supports it.
export const langNames: Record<string, string> = {
  ...languages,
  as: "অসমীয়া",
};

/** Close button, title and the detected-language pill with a change option. */
export default function TalkHeader({
  lang,
  detected,
  onPick,
}: {
  lang: string;
  detected: string;
  onPick: (lang: string) => void;
}) {
  const navigate = useNavigate();
  const [changing, setChanging] = useState(false);
  return (
    <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line/60 bg-paper/95 px-4 py-3 backdrop-blur">
      <div className="flex items-center gap-2">
        <strong className="font-serif text-2xl font-normal tracking-[-0.02em] text-ink">
          Buddy<span className="text-saffron">.</span>
        </strong>
        <span className="rounded-full border border-[#f3d2b8] bg-peach px-2.5 py-1 text-xs font-semibold text-saffron-text">
          {tt(lang, "voiceCompanion")}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <div className="hidden items-center rounded-full border border-line bg-white p-0.5 sm:flex">
          {(
            [
              ["en", "EN"],
              ["hi", "हिं"],
              ["bn", "বাং"],
              ["as", "অস"],
            ] as const
          ).map(([code, short]) => (
            <button
              key={code}
              type="button"
              onClick={() => onPick(code)}
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
        <span className="flex max-w-full flex-wrap items-center gap-1 rounded-full bg-white/90 py-0.5 pl-3 pr-0.5 text-sm font-semibold shadow-[inset_0_0_0_1px_#ede5da]">
          {changing ? (
            <select
              aria-label={tt(lang, "changeLang")}
              value={lang}
              onChange={(e) => {
                onPick(e.target.value);
                setChanging(false);
              }}
              className="!m-0 !min-h-11 !w-auto !rounded-full !py-0"
            >
              {Object.entries(langNames).map(([v, n]) => (
                <option key={v} value={v}>
                  {n}
                </option>
              ))}
            </select>
          ) : (
            <span>
              {langNames[detected || lang] || lang}
              {detected ? ` · ${tt(lang, "langDetected")}` : ""}
            </span>
          )}
          <button
            type="button"
            onClick={() => setChanging((c) => !c)}
            className="!min-h-11 !rounded-full !px-3 text-xs"
          >
            {tt(lang, "changeLang")}
          </button>
        </span>
        <TextSizeToggle />
        <button
          type="button"
          aria-label={tt(lang, "close")}
          onClick={() => navigate("/")}
          className="secondary !min-h-11 shrink-0 !rounded-full !bg-white/90 !px-3 !py-1.5 text-xs font-semibold !text-ink"
        >
          <X size={18} aria-hidden="true" />
          <span className="hidden sm:inline">{tt(lang, "exitTalk")}</span>
        </button>
      </div>
    </header>
  );
}
