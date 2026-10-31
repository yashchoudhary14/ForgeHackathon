import { Text } from "../context";
import { useEffect, useState, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  ShieldCheck,
  BookOpen,
  ListChecks,
  MousePointer2,
} from "lucide-react";
import { useApp } from "../context";
import { post, request } from "../api/client";
import type {
  ProfileData,
  ProfileExtractOut,
  ProfileOut,
  SensitiveData,
} from "../api/types";
import { ErrorBox, Loading, MicButton } from "../components";
const fields: (keyof ProfileData)[] = [
  "age",
  "gender",
  "state",
  "district",
  "residence",
  "caste",
  "annual_income",
  "occupation",
  "is_student",
  "education_level",
  "disability_percent",
  "marital_status",
  "is_bpl",
  "land_acres",
  "is_minority",
];
const choices: Partial<Record<keyof ProfileData, string[]>> = {
  gender: ["male", "female", "transgender"],
  residence: ["urban", "rural"],
  caste: ["general", "obc", "sc", "st", "pvtg", "dnt"],
  is_student: ["true", "false"],
  is_bpl: ["true", "false"],
  is_minority: ["true", "false"],
};
const numeric = ["age", "annual_income", "disability_percent", "land_acres"];
const sensitiveFields: (keyof SensitiveData)[] = [
  "full_name",
  "phone",
  "email",
  "dob",
  "address",
  "father_name",
  "bank_ifsc",
];
export default function Intake() {
  const { lang, t, profileId, setProfileId } = useApp(),
    navigate = useNavigate();
  const [text, setText] = useState(""),
    [profile, setProfile] = useState<ProfileOut | null>(null),
    [question, setQuestion] = useState(""),
    [missing, setMissing] = useState<string[]>([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false);
  const [operation, setOperation] = useState("");
  const retryAction = useRef<() => void>(() => {});
  async function load(signal?: AbortSignal) {
    if (!profileId || profile?.id === profileId) return;
    retryAction.current = () => void load();
    setLoading(true);
    setError("");
    try {
      setProfile(
        await request<ProfileOut>(`/profile/${encodeURIComponent(profileId)}`, {
          signal,
        }),
      );
    } catch (e) {
      if (!signal?.aborted) setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [profileId]);
  async function extract(value = text) {
    if (!value.trim()) return;
    retryAction.current = () => void extract(value);
    setBusy(true);
    setOperation("Understanding your details and building your profile…");
    setError("");
    try {
      const out = await post<ProfileExtractOut>("/profile/extract", {
        text: value,
        language: lang,
        profile_id: profileId || null,
      });
      setProfile(out.profile);
      setProfileId(out.profile.id);
      setQuestion(out.follow_up_question || "");
      setMissing(out.missing_fields);
      setText("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function save(find = false) {
    retryAction.current = () => void save(find);
    if (profile) {
      for (const key of numeric) {
        const value = profile.data[key as keyof ProfileData];
        if (
          typeof value === "number" &&
          (!Number.isFinite(value) ||
            value < 0 ||
            (key !== "land_acres" && !Number.isInteger(value)) ||
            (key === "age" && value > 120) ||
            (key === "disability_percent" && value > 100))
        ) {
          setError(`Please enter a valid ${key.replaceAll("_", " ")}.`);
          return;
        }
      }
    }
    setBusy(true);
    setOperation("Saving your profile securely…");
    setError("");
    try {
      const body = {
        data: profile?.data || {},
        sensitive: profile?.sensitive || {},
        language: lang,
      };
      const result = profile
        ? await request<ProfileOut>(
            `/profile/${encodeURIComponent(profile.id)}`,
            { method: "PUT", body: JSON.stringify(body) },
          )
        : await post<ProfileOut>("/profile", body);
      setProfile(result);
      setProfileId(result.id);
      if (find) navigate("/schemes");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function edit(key: keyof ProfileData, value: string) {
    if (!profile) return;
    const parsed =
      value === ""
        ? null
        : numeric.includes(key)
          ? Number(value)
          : choices[key]?.includes("true")
            ? value === "true"
            : value;
    setProfile({ ...profile, data: { ...profile.data, [key]: parsed } });
  }
  return (
    <>
      <section className="hero">
        <span className="eyebrow">
          <Text value={"ADHIKAAR · अधिकार"} />
        </span>
        <h1>{t.intro}</h1>
        <p>{t.subtitle}</p>
        <div className="actions hero-actions">
          <button
            className="start-button"
            onClick={() => {
              document.getElementById("intake-text")?.focus();
              document
                .getElementById("get-started")
                ?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}
          >
            <Text value="Start" />
            <ArrowRight size={22} />
          </button>
          <Link to="/explain">
            <Text value="Have a notice? Understand it first →" />
          </Link>
        </div>
        <div className="trust">
          <ShieldCheck size={18} />
          <Text
            value={"Official sources. Clear reasons. You stay in control."}
          />
        </div>
      </section>
      <ol
        className="story-steps"
        aria-label={lang === "hi" ? "यह कैसे काम करता है" : "How it works"}
      >
        {[
          [
            "01",
            "Understand",
            "Explain any scheme or notice in your language.",
            BookOpen,
          ],
          [
            "02",
            "Decide",
            "Find schemes you qualify for, with quotes from official sources.",
            ListChecks,
          ],
          [
            "03",
            "Act",
            "Watch the agent fill the portal. You approve before submit.",
            MousePointer2,
          ],
        ].map(([number, title, description, Icon]) => {
          const StepIcon = Icon as typeof BookOpen;
          return (
            <li key={number as string}>
              <div className="story-number">
                <span>{number as string}</span>
                <StepIcon size={22} />
              </div>
              <h2>
                <Text value={title as string} />
              </h2>
              <p>
                <Text value={description as string} />
              </p>
            </li>
          );
        })}
      </ol>
      <div className="intake-grid" id="get-started">
        <section className="panel">
          <span className="step-label">
            <Text value={"01 / ABOUT YOU"} />
          </span>
          <h2>{t.start}</h2>
          <p className="muted">{t.hint}</p>
          <MicButton
            onText={(v) => {
              setText(v);
              void extract(v);
            }}
            disabled={busy || loading}
          />
          {!profile && (
            <button
              className="secondary"
              disabled={busy || loading}
              onClick={() => void save()}
            >
              <Text value="Fill in details instead" />
            </button>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void extract();
            }}
          >
            <label htmlFor="intake-text">{t.start}</label>
            <textarea
              id="intake-text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={4}
              placeholder={
                lang === "hi"
                  ? "मेरे बारे में…"
                  : "My age, where I live, and what I do…"
              }
              required
              disabled={busy}
            />
            <button disabled={busy || !text.trim()}>
              {busy ? <Text value={operation} /> : t.send}
              <ArrowRight size={18} />
            </button>
          </form>
          {question && (
            <div className="bubble" aria-live="polite">
              {question}
            </div>
          )}
          {missing.length > 0 && (
            <p className="muted">
              <Text value={"To help us match:"} />{" "}
              {missing.map((s, i) => (
                <span key={s}>
                  {i > 0 ? ", " : ""}
                  <Text value={s.replaceAll("_", " ")} />
                </span>
              ))}
            </p>
          )}
          {profile && missing.length === 0 && !question && (
            <p className="success">
              <Text
                value={
                  "Your profile is ready. Review it and find your schemes."
                }
              />
            </p>
          )}
          {error && (
            <ErrorBox error={error} retry={() => retryAction.current()} />
          )}
          {busy && <Loading message={operation} />}
        </section>
        <section className="panel">
          <span className="step-label">
            <Text value={"02 / YOUR PROFILE"} />
          </span>
          <h2>
            <Text
              value={lang === "hi" ? "आपकी जानकारी" : "A little about you"}
            />
          </h2>
          <p className="muted">
            <Text
              value={
                "Review and edit before finding schemes. Share only what you are comfortable sharing."
              }
            />
          </p>
          {loading ? (
            <Loading message="Loading your saved profile…" />
          ) : profile ? (
            <div className="fields">
              {fields.map((key) => (
                <label key={key}>
                  <Text value={key.replaceAll("_", " ")} />
                  {choices[key] ? (
                    <select
                      value={String(profile.data[key] ?? "")}
                      onChange={(e) => edit(key, e.target.value)}
                      disabled={busy}
                    >
                      <option value="">
                        <Text value={"Not provided"} />
                      </option>
                      {choices[key]!.map((v) => (
                        <option key={v} value={v}>
                          <Text
                            value={
                              v === "true" ? "Yes" : v === "false" ? "No" : v
                            }
                          />
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      value={String(profile.data[key] ?? "")}
                      disabled={busy}
                      type={numeric.includes(key) ? "number" : "text"}
                      min={numeric.includes(key) ? 0 : undefined}
                      max={
                        key === "age"
                          ? 120
                          : key === "disability_percent"
                            ? 100
                            : undefined
                      }
                      step={key === "land_acres" ? "any" : undefined}
                      onChange={(e) => edit(key, e.target.value)}
                    />
                  )}
                </label>
              ))}
            </div>
          ) : (
            <div className="empty">
              <Text
                value={
                  "Your profile will appear here after you tell us about yourself."
                }
              />
            </div>
          )}
          {profile && (
            <details>
              <summary>
                <Text value="Contact and application details" />
              </summary>
              <div className="fields">
                {sensitiveFields.map((key) => (
                  <label key={key}>
                    <Text value={key.replaceAll("_", " ")} />
                    <input
                      disabled={busy || loading}
                      type={
                        key === "dob"
                          ? "date"
                          : key === "email"
                            ? "email"
                            : key === "phone"
                              ? "tel"
                              : "text"
                      }
                      autoComplete="off"
                      value={profile.sensitive[key] || ""}
                      onChange={(e) =>
                        setProfile({
                          ...profile,
                          sensitive: {
                            ...profile.sensitive,
                            [key]: e.target.value || null,
                          },
                        })
                      }
                    />
                  </label>
                ))}
              </div>
            </details>
          )}
          <div className="actions">
            {profile && (
              <button
                className="secondary"
                disabled={busy || loading}
                onClick={() => void save()}
              >
                {t.save}
              </button>
            )}
            <button
              disabled={busy || loading || !profile}
              onClick={() => void save(true)}
            >
              {t.find}
              <ArrowRight size={18} />
            </button>
          </div>
        </section>
      </div>
    </>
  );
}
