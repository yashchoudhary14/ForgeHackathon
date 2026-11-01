import { Text } from "../context";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  GraduationCap,
  HeartHandshake,
  Landmark,
  Mic,
  Search,
  Sparkles,
  Sprout,
  UserCheck,
} from "lucide-react";
import { post, request, streamMatches } from "../api/client";
import { applyMatchEvent } from "../api/match-state";
import type { MatchResult, ProfileData, ProfileOut, SearchOut } from "../api/types";
import { useApp } from "../context";
import { Empty, ErrorBox, Loading } from "../components";
import { MatchCards, MatchStats } from "./SchemeCards";
import { AlertsPanel } from "./Alerts";
import { Card, EmptyState, Eyebrow, PillButton } from "../ui";
import { PillLink } from "../nav";
import { tt } from "../ui-strings";

const QUICK_STATES = [
  "",
  "Bihar",
  "Assam",
  "West Bengal",
  "Uttar Pradesh",
  "Madhya Pradesh",
  "Maharashtra",
  "Odisha",
  "Rajasthan",
  "Jharkhand",
];

export default function Schemes() {
  const { profileId, setProfileId, t, lang } = useApp();
  const [searchParams] = useSearchParams();
  const initialQuery = searchParams.get("q") || "";
  const [matches, setMatches] = useState<MatchResult[]>([]),
    [results, setResults] = useState<SearchOut | null>(null),
    [keyword, setKeyword] = useState(initialQuery),
    [state, setState] = useState(""),
    [offset, setOffset] = useState(0),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [mode, setMode] = useState<"match" | "search">(
      initialQuery ? "search" : "match",
    );
  const [quickState, setQuickState] = useState("");
  const [quickRole, setQuickRole] = useState<
    "farmer" | "student" | "woman" | "senior" | "worker"
  >("farmer");
  const [quickAge, setQuickAge] = useState("");
  const [quickCategory, setQuickCategory] = useState<
    "general" | "obc" | "sc" | "st" | "bpl"
  >("general");
  const activeMatch = useRef<AbortController | null>(null);
  const [progress, setProgress] = useState("");

  async function load(overrideProfileId?: string) {
    activeMatch.current?.abort();
    const pid = overrideProfileId ?? profileId;
    if (!pid) {
      setMatches([]);
      setProgress("");
      setBusy(false);
      return;
    }
    const controller = new AbortController();
    activeMatch.current = controller;
    setBusy(true);
    setError("");
    setMatches([]);
    setProgress("Checking your profile against official scheme rules…");
    setMode("match");
    try {
      await streamMatches(
        { profile_id: pid, limit: 8 },
        (event) => {
          if (controller.signal.aborted) return;
          if (event.type === "progress") setProgress(event.message);
          setMatches((current) => applyMatchEvent(current, event));
        },
        controller.signal,
      );
    } catch (e) {
      if (!controller.signal.aborted) setError((e as Error).message);
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  async function search(from = 0, qOverride?: string, stateOverride?: string) {
    activeMatch.current?.abort();
    setProgress("");
    setBusy(true);
    setError("");
    setMode("search");
    setOffset(from);
    const q = qOverride ?? keyword;
    const st = stateOverride ?? state;
    try {
      setResults(
        await request<SearchOut>(
          "/schemes/search?" +
            new URLSearchParams({
              keyword: q,
              state: st,
              offset: String(from),
              size: "10",
            }),
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (initialQuery) {
      setKeyword(initialQuery);
      void search(0, initialQuery, state);
      return () => activeMatch.current?.abort();
    }
    if (profileId) {
      void load(profileId);
    } else {
      void search(0, "", "");
    }
    return () => activeMatch.current?.abort();
  }, [profileId, initialQuery]);

  async function createQuickProfile(data: Partial<ProfileData>) {
    setBusy(true);
    setError("");
    try {
      const out = await post<ProfileOut>("/profile", {
        data,
        language: lang,
        mode: "manual",
      });
      setProfileId(out.id);
      await load(out.id);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  function handleQuickMatch() {
    if (!quickState || !quickAge.trim()) return;
    const age = Number(quickAge);
    if (!Number.isInteger(age) || age < 0 || age > 120) {
      setError("Please enter a valid age.");
      return;
    }
    const patch: Partial<ProfileData> = {
      state: quickState || undefined,
      occupation:
        quickRole === "farmer"
          ? "farmer"
          : quickRole === "worker"
            ? "worker"
            : undefined,
      is_student: quickRole === "student" ? true : undefined,
      gender: quickRole === "woman" ? "female" : undefined,
      age,
      caste:
        quickCategory !== "bpl"
          ? quickCategory
          : undefined,
      is_bpl: quickCategory === "bpl" ? true : undefined,
    };
    void createQuickProfile(patch);
  }

  const presetChips = [
    { label: "Farmer · किसान", Icon: Sprout, role: "farmer" },
    { label: "Student · छात्र", Icon: GraduationCap, role: "student" },
    { label: "Woman · महिला", Icon: HeartHandshake, role: "woman" },
    { label: "Senior Citizen · वरिष्ठ", Icon: UserCheck, role: "senior" },
  ] as const;

  return (
    <>
      <div className="mb-6 flex flex-col gap-2">
        <Eyebrow>{t.schemes}</Eyebrow>
        <h1>{t.schemes}</h1>
        <p className="muted m-0">
          <Text
            value={
              "Find support for your next step, with reasons from official sources."
            }
          />
        </p>
      </div>

      {!profileId && matches.length === 0 ? (
        <section className="mb-6 rounded-[28px] border border-[#f3d2b8] bg-peach p-6">
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <span className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-saffron-text">
                  <Sparkles size={14} aria-hidden="true" />
                  {tt(lang, "matcherEyebrow")}
                </span>
                <h2 className="m-0 mt-1 font-serif text-2xl font-normal text-ink sm:text-3xl">
                  {tt(lang, "matcherTitle")}
                </h2>
              </div>
              <PillLink to="/talk" tone="light" className="!min-h-11 !px-4 text-xs">
                <Mic size={16} aria-hidden="true" className="text-saffron-text" />
                {tt(lang, "talkMode")}
              </PillLink>
            </div>

            <div className="grid gap-3 rounded-2xl bg-white/85 p-4 sm:grid-cols-3 lg:grid-cols-[1fr_1.4fr_1fr_auto] lg:items-end">
              <label className="m-0 text-xs font-semibold text-ink-soft">
                State · राज्य
                <select
                  value={quickState}
                  onChange={(e) => setQuickState(e.target.value)}
                  className="!mb-0 !mt-1 !min-h-11 !rounded-xl text-sm"
                >
                  <option value="">Choose your state</option>
                  {QUICK_STATES.filter(Boolean).map((st) => (
                    <option key={st} value={st}>
                      {st}
                    </option>
                  ))}
                </select>
              </label>

              <div className="flex flex-col gap-1">
                <span className="text-xs font-semibold text-ink-soft">
                  Citizen Role · भूमिका
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {(
                    [
                      ["farmer", "Farmer"],
                      ["student", "Student"],
                      ["woman", "Woman"],
                      ["senior", "Senior"],
                      ["worker", "Worker"],
                    ] as const
                  ).map(([val, label]) => (
                    <button
                      key={val}
                      type="button"
                      onClick={() => setQuickRole(val)}
                      className={
                        "!min-h-10 !rounded-full !px-3 !py-1 text-xs font-semibold " +
                        (quickRole === val
                          ? "!bg-ink !text-paper"
                          : "secondary !bg-paper !text-ink")
                      }
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              <label className="m-0 text-xs font-semibold text-ink-soft">
                Category · वर्ग
                <select
                  value={quickCategory}
                  onChange={(e) =>
                    setQuickCategory(
                      e.target.value as
                        | "general"
                        | "obc"
                        | "sc"
                        | "st"
                        | "bpl",
                    )
                  }
                  className="!mb-0 !mt-1 !min-h-11 !rounded-xl text-sm"
                >
                  <option value="general">General</option>
                  <option value="obc">OBC</option>
                  <option value="sc">SC</option>
                  <option value="st">ST</option>
                  <option value="bpl">BPL Household</option>
                </select>
              </label>

              <label className="m-0 text-xs font-semibold text-ink-soft">
                Age
                <input
                  type="number"
                  min={0}
                  max={120}
                  step={1}
                  value={quickAge}
                  onChange={(e) => setQuickAge(e.target.value)}
                  className="!mb-0 !mt-1 !min-h-11 !rounded-xl text-sm"
                />
              </label>

              <PillButton
                tone="saffron"
                disabled={busy || !quickState || !quickAge.trim()}
                onClick={handleQuickMatch}
                className="w-full lg:w-auto"
              >
                Match my schemes →
              </PillButton>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold text-ink-soft">
                Or choose your role:
              </span>
              {presetChips.map(({ label, Icon, role }) => (
                <button
                  key={label}
                  type="button"
                  disabled={busy}
                  onClick={() => setQuickRole(role)}
                  className="secondary inline-flex !min-h-11 items-center gap-1.5 !rounded-full border border-[#f3d2b8] !bg-white !px-3.5 !py-1.5 text-xs font-semibold !text-ink hover:border-saffron"
                >
                  <Icon
                    size={15}
                    aria-hidden="true"
                    className="text-saffron-text"
                  />
                  <span>{label}</span>
                </button>
              ))}
            </div>
          </div>
        </section>
      ) : (
        <div className="mb-6 grid items-start gap-4 lg:grid-cols-[1fr_340px]">
          <MatchStats matches={matches} />
          <Card>
            <h2 className="mb-2">{tt(lang, "alertsTitle")}</h2>
            <AlertsPanel compact />
          </Card>
        </div>
      )}

      <section className="panel">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void search();
          }}
        >
          <div className="grid gap-x-3 md:grid-cols-[minmax(0,1fr)_11rem_auto] md:items-end">
            <label htmlFor="search">
              <Text value={"Search all government schemes"} />
              <input
                id="search"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder={
                  lang === "hi"
                    ? "ज़रूरत या योजना का नाम"
                    : "Search by need or scheme name"
                }
              />
            </label>
            <label>
              <Text value={"State"} />
              <input
                value={state}
                onChange={(e) => setState(e.target.value)}
                placeholder={lang === "hi" ? "कोई भी राज्य" : "Any state"}
              />
            </label>
            <button disabled={busy} className="mb-4 justify-self-start">
              <Search size={18} />
              <Text value={"Search"} />
            </button>
          </div>
        </form>
        {profileId && (
          <button
            className="secondary"
            disabled={busy}
            onClick={() => void load()}
          >
            <Text value={"Show my matches"} />
          </button>
        )}
      </section>
      {error && (
        <ErrorBox
          error={error}
          retry={() => void (mode === "search" ? search(offset) : load())}
        />
      )}{" "}
      {busy && mode === "search" ? (
        <Loading message="Searching official government schemes…" />
      ) : mode === "match" ? (
        <MatchResults
          matches={matches}
          profileId={profileId}
          busy={busy}
          error={error}
          progress={progress}
        />
      ) : (
        <>
          {results && (
            <p className="muted mb-3">
              {results.total} <Text value={"schemes found"} />
            </p>
          )}
          {!results?.items.length && !error ? (
            <Empty>
              <Text value={"No schemes found. Try a different search."} />
            </Empty>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {results?.items.map((s) => {
                const slug = encodeURIComponent(s.slug);
                const visibleTags = s.tags.slice(0, 4);
                const extraTags = Math.max(0, s.tags.length - 4);
                return (
                  <Card
                    as="article"
                    key={s.slug}
                    className="flex flex-col gap-3"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-paper px-3 py-1 text-xs font-semibold text-ink-soft">
                        <Landmark
                          size={14}
                          aria-hidden="true"
                          className="shrink-0 text-saffron-text"
                        />
                        <span className="line-clamp-1">
                          {s.ministry || s.state || "Government of India"}
                        </span>
                      </span>
                      <span className="rounded-full bg-peach px-2.5 py-0.5 text-[11px] font-semibold text-saffron-text">
                        {s.state ? s.state : "Central"}
                      </span>
                    </div>
                    <h2 className="m-0 font-serif text-2xl font-normal leading-snug">
                      <Link
                        to={"/schemes/" + slug}
                        style={{ color: "inherit", textDecoration: "none" }}
                        className="hover:underline"
                      >
                        {s.name}
                      </Link>
                    </h2>
                    {s.brief && (
                      <p className="m-0 line-clamp-2 text-sm leading-relaxed text-ink-soft">
                        {s.brief}
                      </p>
                    )}
                    {visibleTags.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {visibleTags.map((tag) => (
                          <span
                            className="rounded-full border border-line bg-paper px-3 py-1 text-xs font-medium text-ink-soft"
                            key={tag}
                          >
                            {tag}
                          </span>
                        ))}
                        {extraTags > 0 && (
                          <span className="rounded-full bg-peach px-2.5 py-1 text-xs font-semibold text-saffron-text">
                            +{extraTags} more
                          </span>
                        )}
                      </div>
                    )}
                    <div className="mt-auto flex flex-wrap gap-2 pt-2">
                      <PillLink to={"/schemes/" + slug} tone="dark">
                        Check eligibility & apply →
                      </PillLink>
                      <PillLink to={"/explain?scheme=" + slug} tone="light">
                        Explain
                      </PillLink>
                    </div>
                  </Card>
                );
              })}
            </div>
          )}
          {results && (
            <div className="actions mt-5">
              <button
                className="secondary"
                disabled={offset === 0}
                onClick={() => void search(Math.max(0, offset - 10))}
              >
                <Text value={"Previous"} />
              </button>
              <button
                disabled={offset + results.items.length >= results.total}
                onClick={() => void search(offset + 10)}
              >
                <Text value={"Next"} />
              </button>
            </div>
          )}
        </>
      )}
    </>
  );
}

export function MatchResults({
  matches,
  profileId,
  busy,
  error,
  progress,
}: {
  matches: MatchResult[];
  profileId: string;
  busy: boolean;
  error: string;
  progress: string;
}) {
  const { lang } = useApp();
  return (
    <section aria-label="Scheme matches" aria-busy={busy}>
      {progress && (
        <p className="muted" role="status" aria-live="polite">
          {progress}
        </p>
      )}
      {!profileId ? (
        <EmptyState title={<Text value="See schemes matched to you" />} action={<PillLink to="/welcome" tone="saffron">
            <Text value={"Create your profile →"} />
          </PillLink>}>
          {tt(lang, "needProfile")}
        </EmptyState>
      ) : matches.length === 0 && !error && !busy ? (
        <Empty>
          <Text
            value={
              "No matching schemes were returned. Update your profile or search above."
            }
          />
        </Empty>
      ) : (
        <MatchCards matches={matches} />
      )}
    </section>
  );
}
