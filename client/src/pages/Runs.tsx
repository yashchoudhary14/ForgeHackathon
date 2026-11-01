import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Bell, Bot, MapPin, ThumbsUp } from "lucide-react";
import { getActivity } from "../api/alerts";
import { listReports, statusMeta } from "../api/civic";
import type { ReportOut } from "../api/civic";
import { request, withOwner } from "../api/client";
import type { ActivityItem, Lang, RunOut } from "../api/types";
import { ErrorBox, Loading } from "../components";
import { Text, useApp } from "../context";
import { translate } from "../i18n";
import { PillLink } from "../nav";
import { tt } from "../ui-strings";
import { Card, EmptyState, Eyebrow, StatTile } from "../ui";
import { AlertsPanel, OpenLink } from "./Alerts";

type Tab = "all" | "runs" | "civic" | "alerts";
const icons = { run: Bot, report: MapPin, notification: Bell };

/** The merged GET /activity timeline: one row per run, report or alert, newest first. */
export function ActivityTimeline({ items, lang = "en" }: { items: ActivityItem[]; lang?: string }) {
  if (items.length === 0)
    return (
      <EmptyState title={tt(lang, "activityEmptyTitle")} action={<PillLink to="/talk">{tt(lang, "talkMode")} →</PillLink>}>
        {tt(lang, "activityEmpty")}
      </EmptyState>
    );
  return (
    <ol className="m-0 flex list-none flex-col gap-2 p-0">
      {items.map((item) => {
        const Icon = icons[item.type];
        return (
          <li key={item.type + item.id} className="flex flex-wrap items-start gap-3 rounded-[22px] bg-white p-4 shadow-[inset_0_0_0_1px_#ede5da]">
            <span aria-hidden="true" className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-peach text-saffron-text">
              <Icon size={18} />
            </span>
            <div className="flex min-w-0 flex-1 basis-48 flex-col gap-1">
              <strong className="break-words">{item.title}</strong>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-soft">
                <span className="capitalize">{translate(item.status.replaceAll("_", " "), lang as Lang)}</span>
                {item.official && (
                  <span className="rounded-full bg-warn-soft px-2 py-0.5 text-xs font-semibold text-warn">
                    {tt(lang, "official")}
                  </span>
                )}
                <time dateTime={item.updated_at}>{new Date(item.updated_at).toLocaleString()}</time>
              </div>
            </div>
            <OpenLink link={item.link} lang={lang} />
          </li>
        );
      })}
    </ol>
  );
}

function RunCards({ runs, lang }: { runs: RunOut[]; lang: Lang }) {
  if (runs.length === 0)
    return (
      <EmptyState title="No assisted applications yet" action={<PillLink to="/schemes">Browse schemes →</PillLink>}>
        Open a scheme to start a live browser agent application.
      </EmptyState>
    );
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {runs.map((r) => (
        <Card key={r.id} className="flex flex-col justify-between gap-2.5 !p-4">
          <div className="flex flex-col gap-1">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className={`badge ${r.status}`}>{translate(r.status.replaceAll("_", " "), lang)}</span>
              {r.kind && r.kind !== "application" && <small className="capitalize">{r.kind.replaceAll("_", " ")}</small>}
            </div>
            <h3 className="m-0 break-words font-serif text-xl font-normal">{r.goal}</h3>
            {r.receipt?.reference_no && (
              <p className="m-0 break-all text-sm"><Text value="Receipt:" /> <strong className="font-mono">{r.receipt.reference_no}</strong></p>
            )}
          </div>
          <Link to={"/runs/" + encodeURIComponent(r.id)} className="inline-flex min-h-11 items-center text-sm font-semibold"><Text value="Open session →" /></Link>
        </Card>
      ))}
    </div>
  );
}

function ReportCards({ reports }: { reports: ReportOut[] }) {
  if (reports.length === 0)
    return (
      <EmptyState title="No civic reports yet" action={<PillLink to="/civic/new">Report an issue →</PillLink>}>
        Report a local water, road, electricity or sanitation problem and track it to CPGRAMS.
      </EmptyState>
    );
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {reports.map((c) => (
        <Card key={c.id} className="flex flex-col justify-between gap-2.5 !p-4">
          <div className="flex flex-col gap-1">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
              <span className="min-w-0 break-words font-semibold uppercase text-ink-soft">{c.department}</span>
              <span className="rounded-full bg-peach px-2.5 py-0.5 font-semibold text-saffron-text">{statusMeta(c.status).label}</span>
            </div>
            <h3 className="m-0 break-words font-serif text-xl font-normal">{c.title}</h3>
            {c.official_ref && <small className="break-all font-mono font-bold">CPGRAMS: {c.official_ref}</small>}
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="inline-flex items-center gap-1.5 text-ink-soft"><ThumbsUp size={15} aria-hidden="true" className="shrink-0" />{c.supporters}</span>
            <Link to={"/civic/" + encodeURIComponent(c.id)} className="inline-flex min-h-11 items-center font-semibold">Track timeline →</Link>
          </div>
        </Card>
      ))}
    </div>
  );
}

export default function Runs() {
  const { profileId, lang } = useApp();
  const [activity, setActivity] = useState<ActivityItem[] | null>(null);
  const [runs, setRuns] = useState<RunOut[]>([]);
  const [reports, setReports] = useState<ReportOut[]>([]);
  const [unread, setUnread] = useState(0);
  const [tab, setTab] = useState<Tab>("all");
  const [error, setError] = useState("");

  async function load(signal?: AbortSignal) {
    setError("");
    if (!profileId) return setActivity([]);
    try {
      const [items, runList, mine] = await Promise.all([
        getActivity(profileId, signal),
        request<RunOut[]>(withOwner("/agent/runs", profileId), { signal }),
        listReports({ profile_id: profileId }, signal),
      ]);
      if (signal?.aborted) return;
      setActivity(items);
      setRuns(runList);
      setReports(mine);
      setUnread(items.filter((i) => i.type === "notification" && i.status === "unread").length);
    } catch (e) {
      if (!signal?.aborted) {
        setActivity((a) => a ?? []);
        setError((e as Error).message);
      }
    }
  }

  useEffect(() => {
    setActivity(null);
    const c = new AbortController();
    void load(c.signal);
    return () => c.abort();
  }, [profileId]);

  const tabs: [Tab, string][] = [
    ["all", tt(lang, "tabAll")],
    ["runs", `${tt(lang, "navApplications")} (${runs.length})`],
    ["civic", `${tt(lang, "navCivic")} (${reports.length})`],
    ["alerts", `${tt(lang, "navAlerts")} (${unread})`],
  ];

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <Eyebrow>{tt(lang, "navActivity")}</Eyebrow>
        <h1>{tt(lang, "activityTitle")}</h1>
        <p className="m-0 text-ink-soft">
          <Text value="Track your assisted scheme applications, CPGRAMS civic grievances, and official notifications in one place." />
        </p>
      </div>

      {!profileId ? (
        <EmptyState title={tt(lang, "needProfileTitle")} action={<PillLink to="/talk">{tt(lang, "talkMode")} →</PillLink>}>
          {tt(lang, "needProfile")}
        </EmptyState>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-3">
            <StatTile accent value={runs.length} label={tt(lang, "navApplications")} />
            <StatTile value={reports.length} label={tt(lang, "navCivic")} />
            <StatTile value={unread} label={tt(lang, "unreadAlerts")} />
          </div>

          <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1" role="tablist" aria-label={tt(lang, "navActivity")}>
            {tabs.map(([key, label]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={tab === key}
                onClick={() => setTab(key)}
                className={(tab === key ? "" : "secondary ") + "!min-h-11 shrink-0 !rounded-full !px-4 !py-1.5 text-sm"}
              >
                {label}
              </button>
            ))}
          </div>

          {error && <ErrorBox error={error} retry={() => void load()} />}

          {!activity ? (
            <Loading message="Loading your applications, civic reports and alerts…" />
          ) : tab === "all" ? (
            <ActivityTimeline items={activity} lang={lang} />
          ) : tab === "runs" ? (
            <RunCards runs={runs} lang={lang} />
          ) : tab === "civic" ? (
            <ReportCards reports={reports} />
          ) : (
            <Card>
              <AlertsPanel onUnread={setUnread} />
            </Card>
          )}
        </>
      )}
    </div>
  );
}

