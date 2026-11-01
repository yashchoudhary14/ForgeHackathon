import { Text, useTranslation, useApp } from "../context";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Bot,
  FileText,
  GraduationCap,
  HeartHandshake,
  MapPin,
  Mic,
  Sprout,
  UserCheck,
  Volume2,
} from "lucide-react";
import { request } from "../api/client";
import type { ProfileOut } from "../api/types";
import { Card, Eyebrow, Orb, PillButton, ProfileRequiredCard } from "../ui";
import { PersonIcon, PillLink } from "../nav";
import { tt } from "../ui-strings";

function PersonalSummary() {
  const { lang, profileId } = useApp();
  const [profile, setProfile] = useState<ProfileOut | null>(null);
  const [failed, setFailed] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const c = new AbortController();
    setProfile(null);
    setFailed(false);
    request<ProfileOut>(`/profile/${encodeURIComponent(profileId)}`, {
      signal: c.signal,
    })
      .then((out) => {
        if (!c.signal.aborted) setProfile(out);
      })
      .catch(() => {
        if (!c.signal.aborted) setFailed(true);
      });
    return () => c.abort();
  }, [profileId, revision]);
  const details = profile
    ? [
        profile.data.age != null
          ? `${tt(lang, "field_age")}: ${profile.data.age}`
          : "",
        profile.data.district,
        profile.data.state,
        profile.data.occupation,
      ]
        .filter(Boolean)
        .join(" · ")
    : "";
  return (
    <Card className="flex flex-wrap items-center justify-between gap-4">
      <div>
        <h2 className="flex items-center gap-2">
          <PersonIcon />
          {profile?.sensitive?.full_name || tt(lang, "profileSummary")}
        </h2>
        <p className="m-0 text-ink-soft" role="status">
          {failed
            ? tt(lang, "profileLoadError")
            : !profile
              ? tt(lang, "loading")
              : details || tt(lang, "profileSummaryEmpty")}
        </p>
      </div>
      <div className="flex flex-wrap gap-3">
        {failed && (
          <PillButton tone="light" onClick={() => setRevision((v) => v + 1)}>
            {tt(lang, "tryAgain")}
          </PillButton>
        )}
        <PillLink to="/profile">{tt(lang, "profileEdit")} →</PillLink>
      </div>
    </Card>
  );
}

/** Dawn home introduces the app; saved details are edited on /profile. */
export default function Home() {
  const tr = useTranslation();
  const { lang, profileId } = useApp();
  const navigate = useNavigate();
  const jobs = [
    {
      title: "homeUnderstand",
      text: "homeUnderstandText",
      to: "/explain",
      cta: "Explain a notice or GO",
      Icon: FileText,
      tint: "",
      iconBg: "bg-peach text-saffron-text",
      rule: "bg-saffron",
    },
    {
      title: "homeAct",
      text: "homeActText",
      to: "/schemes",
      cta: "Find & apply to schemes",
      Icon: Bot,
      tint: "",
      iconBg: "bg-act-soft text-act",
      rule: "bg-act",
    },
    {
      title: "homeCivic",
      text: "homeCivicText",
      to: "/civic",
      cta: "Report a civic issue",
      Icon: MapPin,
      tint: "",
      iconBg: "bg-ok-soft text-ok",
      rule: "bg-ok",
    },
  ];
  const roleChips = [
    {
      key: "roleFarmer",
      query: "farmer",
      Icon: Sprout,
    },
    {
      key: "roleStudent",
      query: "scholarship",
      Icon: GraduationCap,
    },
    {
      key: "roleWomen",
      query: "women",
      Icon: HeartHandshake,
    },
    {
      key: "roleSenior",
      query: "pension",
      Icon: UserCheck,
    },
  ] as const;

  function askSample(promptText: string) {
    window.dispatchEvent(
      new CustomEvent("buddy:prompt", { detail: { text: promptText } }),
    );
  }

  return (
    <div className="-mx-4 -mt-5 md:-mx-8">
      <section className="on-ink relative overflow-hidden bg-dawn px-5 pb-10 pt-8 text-white md:rounded-b-card md:px-8 md:pb-16 md:pt-14">
        <span
          aria-hidden="true"
          className="pointer-events-none absolute -right-16 -top-16 h-64 w-64 rotate-[-8deg] rounded-full border-[6px] border-double border-white/10 md:h-96 md:w-96"
        />
        <div className="relative mx-auto grid max-w-6xl items-center gap-8 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="flex flex-col items-start gap-4 text-left">
            <div className="flex flex-wrap items-center gap-2 [&_.eyebrow]:!text-[#c9cff0]">
              <Eyebrow>{tt(lang, "brandName")}</Eyebrow>
              <span className="stamp text-sm !text-lime">
                {tt(lang, "homeEyebrow")}
              </span>
            </div>
            <h1 className="home-display m-0 !text-white">
              {tt(lang, "homeTitle")}
              <br />
              <em className="not-italic text-[#c9cff0]">{tt(lang, "homeAccent")}</em>
            </h1>
            <p className="m-0 max-w-xl text-lg text-[#dfe3f7] sm:text-xl">
              {tt(lang, "homeDescription")}
            </p>
            <div className="mt-3 flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center">
              <PillLink to="/talk" tone="saffron" className="!min-h-[60px] !px-8 !text-lg !font-bold shadow-[0_6px_0_#b87900] active:translate-y-[3px] active:!shadow-[0_3px_0_#b87900]">
                <span aria-hidden="true" className="grid h-9 w-9 place-items-center rounded-full bg-ink text-lime">
                  <Mic size={20} />
                </span>
                {tt(lang, "chooseTalk")}
              </PillLink>
              <PillLink to="/profile" tone="inverse" className="!min-h-14 !px-6">
                {tt(lang, "chooseManual")} →
              </PillLink>
            </div>
          </div>

          <div className="flex flex-col gap-4 rounded-card border border-line bg-card p-5 text-left text-ink shadow-[0_18px_40px_rgb(8_12_40/0.35)]">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="relative shrink-0">
                  <Orb size={44} state="idle" />
                  <Mic
                    size={18}
                    aria-hidden="true"
                    className="absolute inset-0 m-auto text-ink"
                  />
                </div>
                <div>
                  <span className="text-xs font-semibold tracking-wide text-act">
                     <Text value="TRY BUDDY RIGHT NOW" /> </span>
                  <h2 className="m-0 font-serif text-xl font-semibold leading-tight text-ink">
                     <Text value="Speak or tap a citizen starter" /> </h2>
                </div>
              </div>
              <button
                type="button"
                onClick={() =>
                  askSample(
                    tr("Tell me about PM-KISAN and schemes for my family"),
                  )
                }
                className="secondary !min-h-11 shrink-0 !rounded-full !px-3.5 !py-1.5 text-xs font-semibold"
              >
                <Volume2 size={15} aria-hidden="true" />
                {tt(lang, "askBuddy")}
              </button>
            </div>

            <div className="flex flex-col gap-0 rounded-tile border border-line bg-paper text-sm [&>button+button]:border-t [&>button+button]:border-dashed [&>button+button]:border-[#c3cad9]">
              <button
                type="button"
                onClick={() =>
                  askSample(tr("Tell me about PM-KISAN"))
                }
                className="secondary flex !min-h-12 w-full items-center justify-between gap-2 !rounded-none !border-0 !bg-transparent !px-3.5 !py-2 text-left text-sm font-semibold !text-ink hover:!bg-act-soft"
              >
                <span> <Text value="“Tell me about PM-KISAN”" /> </span>
                <ArrowRight size={16} aria-hidden="true" className="shrink-0 text-act" />
              </button>
              <button
                type="button"
                onClick={() =>
                  askSample(tr("What schemes can a student in Bihar get?"))
                }
                className="secondary flex !min-h-12 w-full items-center justify-between gap-2 !rounded-none !border-0 !bg-transparent !px-3.5 !py-2 text-left text-sm font-semibold !text-ink hover:!bg-act-soft"
              >
                <span> <Text value="“What schemes can a student in Bihar get?”" /> </span>
                <ArrowRight size={16} aria-hidden="true" className="shrink-0 text-act" />
              </button>
            </div>

            <div className="flex flex-col gap-2">
              <span className="text-sm font-semibold text-ink-soft">
                 <Text value="Explore schemes by citizen role:" /> </span>
              <div className="grid grid-cols-2 gap-2">
                {roleChips.map(({ key, query, Icon }) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() =>
                      navigate(`/schemes?q=${encodeURIComponent(query)}`)
                    }
                    className="secondary flex !min-h-11 items-center justify-start gap-2 !rounded-full !border !border-[#b9c1d4] !bg-white !px-3.5 !py-2 text-left text-sm font-semibold !text-ink hover:!border-act"
                  >
                    <Icon
                      size={15}
                      aria-hidden="true"
                      className="shrink-0 text-act"
                    />
                    <span>{tt(lang, key)}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto flex max-w-6xl flex-col gap-6 px-4 pb-10 pt-6 md:px-8 md:pt-8">
        {profileId ? (
          <PersonalSummary key={profileId} />
        ) : (
          <ProfileRequiredCard context="activity" />
        )}
        <div className="flex flex-col gap-2 pt-2">
          <Eyebrow> <Text value="ONE ASSISTANT, THREE JOBS" /> </Eyebrow>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          {jobs.map(({ title, text, to, cta, Icon, tint, iconBg, rule }) => (
            <Card key={title} className={`relative flex flex-col gap-3 overflow-hidden pt-6 ${tint}`}>
              <span aria-hidden="true" className={`absolute inset-x-0 top-0 h-1.5 ${rule}`} />
              <span
                aria-hidden="true"
                className={`grid h-12 w-12 place-items-center rounded-tile ${iconBg}`}
              >
                <Icon size={22} />
              </span>
              <h2 className="m-0 font-serif text-[1.75rem] font-bold leading-tight">{tt(lang, title)}</h2>
              <p className="m-0 flex-1 text-ink-soft">{tt(lang, text)}</p>
              <Link
                to={to}
                style={{ color: "#2b3fb5" }}
                className="mt-auto inline-flex min-h-11 items-center gap-1.5 pt-2 text-base font-semibold no-underline underline-offset-4 hover:underline"
              >
                <span><Text value={cta} /></span>
                <ArrowRight size={16} aria-hidden="true" />
              </Link>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
}
