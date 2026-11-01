import { useEffect, useState } from "react";
import { FileText, MapPin, Mic, Bot } from "lucide-react";
import { useApp } from "../context";
import { request } from "../api/client";
import type { ProfileOut } from "../api/types";
import { Card, Eyebrow, PillButton } from "../ui";
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
  const { lang, profileId } = useApp();
  const jobs = [
    {
      title: "homeUnderstand",
      text: "homeUnderstandText",
      to: "/explain",
      Icon: FileText,
      tint: "",
    },
    {
      title: "homeAct",
      text: "homeActText",
      to: "/schemes",
      Icon: Bot,
      tint: "bg-act-soft",
    },
    {
      title: "homeCivic",
      text: "homeCivicText",
      to: "/civic",
      Icon: MapPin,
      tint: "bg-[#f2f8e1]",
    },
  ];
  return (
    <div className="-mx-4 -mt-5 md:-mx-8">
      <section
        className="px-5 pb-16 pt-14 text-center md:pt-20"
        style={{
          background:
            "linear-gradient(180deg,#F7A35C 0%,#FFC994 38%,#FBE6D2 70%,#FBF6EE 100%)",
        }}
      >
        <div className="mx-auto flex max-w-3xl flex-col items-center gap-5">
          <Eyebrow>{tt(lang, "brandName")}</Eyebrow>
          <span className="rounded-full bg-[#ffe7d3] px-4 py-2 text-sm font-semibold text-saffron-text">
            {tt(lang, "homeEyebrow")}
          </span>
          <h1 className="home-display mx-auto">
            {tt(lang, "homeTitle")}
            <br />
            <em>{tt(lang, "homeAccent")}</em>
          </h1>
          <p className="m-0 max-w-xl text-xl text-ink-soft">
            {tt(lang, "homeDescription")}
          </p>
          <div className="mt-2 flex flex-wrap justify-center gap-3">
            <PillLink to="/talk" className="!min-h-14 !px-7 text-base">
              <Mic size={20} aria-hidden="true" />
              {tt(lang, "chooseTalk")}
            </PillLink>
            <PillLink to="/schemes" tone="light" className="!min-h-14">
              {tt(lang, "navSchemes")} →
            </PillLink>
          </div>
        </div>
      </section>
      <section className="mx-auto flex max-w-6xl flex-col gap-6 px-4 pb-10 md:px-8">
        {profileId && <PersonalSummary key={profileId} />}
        <div className="grid gap-4 md:grid-cols-3">
          {jobs.map(({ title, text, to, Icon, tint }) => (
            <Card key={title} className={`flex flex-col gap-3 ${tint}`}>
              <Icon aria-hidden="true" />
              <h2 className="m-0 font-serif text-3xl">{tt(lang, title)}</h2>
              <p className="m-0 flex-1 text-ink-soft">{tt(lang, text)}</p>
              <PillLink to={to} tone="light">
                {tt(lang, "open")} →
              </PillLink>
            </Card>
          ))}
        </div>
        {!profileId && (
          <Card>
            <h2>{tt(lang, "profileTitle")}</h2>
            <p className="text-ink-soft">{tt(lang, "profileSummaryEmpty")}</p>
            <PillLink to="/profile">{tt(lang, "profileCreate")} →</PillLink>
          </Card>
        )}
      </section>
    </div>
  );
}
