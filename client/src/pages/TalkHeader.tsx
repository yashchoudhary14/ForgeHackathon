import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { X } from "lucide-react";
import { languages } from "../context";
import { tt } from "../ui-strings";

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
    <header className="flex items-center justify-between gap-2 px-4 py-3">
      <button
        type="button"
        aria-label="Close"
        onClick={() => navigate("/")}
        className="!min-h-11 !w-11 !rounded-full !bg-white/80 !p-0 !text-ink"
      >
        <X size={20} />
      </button>
      <strong className="font-serif text-2xl font-normal">
        {tt(lang, "talkTitle")}
      </strong>
      <span className="flex items-center gap-1 rounded-full bg-white/90 py-0.5 pl-3 pr-0.5 text-sm font-semibold">
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
    </header>
  );
}
