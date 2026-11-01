import { Text, languages } from "../context";
import { useNavigate } from "react-router-dom";
import { X } from "lucide-react";
import { tt } from "../ui-strings";
import { TextSizeToggle } from "../ui";

// Native language names make the selector recognizable in every UI language.
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
  return (
    <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line/60 bg-paper/95 px-4 py-3 backdrop-blur">
      <div className="flex items-center gap-2">
        <strong className="font-serif text-2xl font-normal tracking-[-0.02em] text-ink">
           <Text value="Buddy" /> <span className="text-saffron">.</span>
        </strong>
        <span className="rounded-full border border-[#f3d2b8] bg-peach px-2.5 py-1 text-xs font-semibold text-saffron-text">
          {tt(lang, "voiceCompanion")}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <select aria-label={tt(lang, "profileLanguage")} value={lang} onChange={(e) => onPick(e.target.value)} className="!m-0 !min-h-11 !w-auto !max-w-32 !rounded-full !px-3 !py-1 text-sm">
          {Object.entries(langNames).map(([value, name]) => <option key={value} value={value}>{name}</option>)}
        </select>
        {detected && <span className="text-xs">{tt(lang, "langDetected")}: {langNames[detected] || detected}</span>}
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
