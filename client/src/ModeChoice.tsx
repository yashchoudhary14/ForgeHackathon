import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Mic, MousePointerClick } from "lucide-react";
import { saveMode } from "./api/profile";
import type { UiMode } from "./api/profile";
import { languages, useApp } from "./context";
import type { Lang } from "./api/types";
import { tt } from "./ui-strings";
import { Card, Eyebrow, TextSizeToggle } from "./ui";

/** First visit: choose Talk or Manual. The choice is saved on the profile. */
export default function ModeChoice() {
  const { lang, setLang, profileId, setProfileId, setMode } = useApp();
  const navigate = useNavigate();
  const [busy, setBusy] = useState<UiMode | "">("");
  const [error, setError] = useState("");
  async function choose(mode: UiMode) {
    setBusy(mode);
    setError("");
    setMode(mode);
    try {
      setProfileId(await saveMode(profileId, mode, lang));
    } catch (e) {
      // The choice is still kept locally; it is synced on the next profile save.
      setError((e as Error).message);
    } finally {
      setBusy("");
      navigate(mode === "talk" ? "/talk" : "/", { replace: true });
    }
  }
  const options: [UiMode, string, string, typeof Mic][] = [
    ["talk", "chooseTalk", "chooseTalkSub", Mic],
    ["manual", "chooseManual", "chooseManualSub", MousePointerClick],
  ];
  return (
    <div className="mx-auto flex min-h-[80vh] max-w-2xl flex-col justify-center gap-6 px-4 py-10">
      <div className="flex flex-col gap-2">
        <Eyebrow>Adhikaar · अधिकार</Eyebrow>
        <h1>{tt(lang, "chooseTitle")}</h1>
        <p className="m-0 text-ink-soft">{tt(lang, "chooseSub")}</p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
      <label className="flex items-center gap-3 text-sm">
        <span>Language</span>
        <select
          aria-label="Language"
          value={lang}
          onChange={(e) => setLang(e.target.value as Lang)}
          className="!m-0 !w-auto"
        >
          {Object.entries(languages).map(([v, n]) => (
            <option key={v} value={v}>
              {n}
            </option>
          ))}
        </select>
      </label>
      <TextSizeToggle />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {options.map(([mode, title, sub, Icon]) => (
          <Card key={mode} tint={mode === "talk" ? "peach" : undefined}>
            <button
              type="button"
              disabled={busy !== ""}
              onClick={() => void choose(mode)}
              className="!flex !h-auto w-full !flex-col !items-start !gap-3 !rounded-none !bg-transparent !p-0 text-left !text-ink"
            >
              <span className="grid h-12 w-12 place-items-center rounded-full bg-ink text-paper">
                <Icon aria-hidden="true" />
              </span>
              <span className="font-serif text-2xl font-normal">
                {tt(lang, title)}
              </span>
              <span className="font-normal text-ink-soft">
                {tt(lang, sub)}
              </span>
            </button>
          </Card>
        ))}
      </div>
      {error && (
        <p role="alert" className="m-0 text-bad">
          {error}
        </p>
      )}
    </div>
  );
}
