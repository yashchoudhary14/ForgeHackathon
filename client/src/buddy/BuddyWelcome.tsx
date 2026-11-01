import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { post, request } from "../api/client";
import { saveMode } from "../api/profile";
import type { Lang, ProfileData, ProfileOut } from "../api/types";
import { languages, useApp } from "../context";
import { Card } from "../ui";
import { useBuddy } from "./context";
import { profileFields } from "./actions";
import { buddyText } from "./strings";

export default function BuddyWelcome({
  profile = false,
}: {
  profile?: boolean;
}) {
  const { lang, setLang, mode, setMode, profileId, setProfileId } = useApp();
  const { setOnboarding, setOpen } = useBuddy();
  const [manual, setManual] = useState(profile);
  const [data, setData] = useState<ProfileData>({});
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const navigate = useNavigate();
  const ui = (key: Parameters<typeof buddyText>[1]) => buddyText(lang, key);
  useEffect(() => {
    if (!profileId) return;
    const abort = new AbortController();
    const load = () => {
      void request<ProfileOut>(`/profile/${encodeURIComponent(profileId)}`, {
        signal: abort.signal,
      })
        .then((out) => setData(out.data))
        .catch((e: Error) => {
          if (!abort.signal.aborted) setError(e.message);
        });
    };
    load();
    window.addEventListener("buddy:profile-changed", load);
    return () => {
      abort.abort();
      window.removeEventListener("buddy:profile-changed", load);
    };
  }, [profileId]);
  async function voice() {
    setBusy(true);
    setError("");
    try {
      setProfileId(await saveMode(profileId, "talk", lang));
      setMode("talk");
      setOnboarding(true);
      setOpen(true);
      navigate("/talk");
      window.dispatchEvent(new Event("buddy:onboard"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    setBusy(true);
    setError("");
    try {
      const payload = { data, language: lang, mode: mode || "manual" };
      const result = profileId
        ? await request<ProfileOut>(
            `/profile/${encodeURIComponent(profileId)}`,
            { method: "PUT", body: JSON.stringify(payload) },
          )
        : await post<ProfileOut>("/profile", payload);
      setProfileId(result.id);
      setMode(mode || "manual");
      setOnboarding(false);
      navigate("/schemes");
      window.dispatchEvent(new Event("buddy:profile-changed"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const options: Partial<Record<keyof ProfileData, [string, string][]>> = {
    gender: [
      [
        "male",
        lang === "hi"
          ? "पुरुष"
          : lang === "bn" || lang === "as"
            ? "পুরুষ"
            : "Male",
      ],
      [
        "female",
        lang === "hi"
          ? "महिला"
          : lang === "bn" || lang === "as"
            ? "মহিলা"
            : "Female",
      ],
      [
        "transgender",
        lang === "hi"
          ? "ट्रांसजेंडर"
          : lang === "bn" || lang === "as"
            ? "ট্রান্সজেন্ডার"
            : "Transgender",
      ],
    ],
    is_student: [
      ["true", ui("yes")],
      [
        "false",
        lang === "hi" ? "नहीं" : lang === "bn" || lang === "as" ? "না" : "No",
      ],
    ],
    caste: ["general", "obc", "sc", "st", "pvtg", "dnt"].map((value) => [
      value,
      value.toUpperCase(),
    ]),
    residence: [
      [
        "rural",
        lang === "hi"
          ? "गाँव"
          : lang === "bn" || lang === "as"
            ? "গ্রাম"
            : "Village",
      ],
      [
        "urban",
        lang === "hi" ? "शहर" : lang === "bn" || lang === "as" ? "শহর" : "City",
      ],
    ],
  };
  return (
    <div className="mx-auto flex max-w-xl flex-col gap-5 px-4 py-10">
      <h1>{ui("name")}</h1>
      <p>{ui("greeting")}</p>
      <label>
        Language
        <select value={lang} onChange={(e) => setLang(e.target.value as Lang)}>
          {Object.entries(languages).map(([code, label]) => (
            <option key={code} value={code}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {!manual ? (
        <div className="flex flex-wrap gap-3">
          <button disabled={busy} onClick={() => void voice()}>
            {ui("voice")}
          </button>
          <button
            disabled={busy}
            className="secondary"
            onClick={() => setManual(true)}
          >
            {ui("manual")}
          </button>
        </div>
      ) : (
        <Card>
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              void save();
            }}
          >
            {profileFields.map((field) => {
              const choices = options[field];
              const label = ui(field === "state" ? "state" : field);
              const value = data[field] == null ? "" : String(data[field]);
              return (
                <label key={field}>
                  {label}
                  {choices ? (
                    <select
                      required
                      value={value}
                      onChange={(e) =>
                        setData((old) => ({
                          ...old,
                          [field]:
                            field === "is_student"
                              ? e.target.value === "true"
                              : e.target.value,
                        }))
                      }
                    >
                      <option value="" disabled>
                        —
                      </option>
                      {choices.map(([key, title]) => (
                        <option key={key} value={key}>
                          {title}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      required
                      value={value}
                      type={
                        field === "age" || field === "annual_income"
                          ? "number"
                          : "text"
                      }
                      min={field === "age" ? 1 : 0}
                      max={field === "age" ? 120 : undefined}
                      step={1}
                      maxLength={100}
                      onChange={(e) =>
                        setData((old) => ({
                          ...old,
                          [field]:
                            e.target.value === ""
                              ? null
                              : field === "age" || field === "annual_income"
                                ? Number(e.target.value)
                                : e.target.value,
                        }))
                      }
                    />
                  )}
                </label>
              );
            })}
            <button disabled={busy}>
              {busy ? ui("thinking") : ui("save")}
            </button>
          </form>
        </Card>
      )}
      {!profile && (
        <button
          className="secondary self-start"
          disabled={busy}
          onClick={() => {
            setMode(mode || "manual");
            setOnboarding(false);
            setOpen(false);
            navigate("/");
          }}
        >
          {ui("skip")}
        </button>
      )}
      {error && (
        <p role="alert" className="text-bad">
          {error}
        </p>
      )}
    </div>
  );
}
