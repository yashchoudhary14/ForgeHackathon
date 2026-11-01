import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Bot, Bell, MapPin } from "lucide-react";
import { listCivicReports, statusMeta } from "../api/civic";
import type { CivicReportOut } from "../api/civic";
import { request } from "../api/client";
import type { Lang, NotificationOut, RunOut } from "../api/types";
import { ErrorBox, Loading } from "../components";
import { Text, useApp } from "../context";
import { translate } from "../i18n";
import { PillLink } from "../nav";
import { tt } from "../ui-strings";
import { Card, EmptyState, Eyebrow, StatTile } from "../ui";
import { AlertsPanel } from "./Alerts";

type Tab = "all" | "runs" | "civic" | "alerts";

export function ActivityView({
  runs,
  reports,
  tab = "all",
  lang = "en",
}: {
  runs: RunOut[];
  reports: CivicReportOut[];
  tab?: Tab;
  lang?: Lang;
}) {
  const showRuns = tab === "all" || tab === "runs";
  const showCivic = tab === "all" || tab === "civic";
  return (
    <div className="flex flex-col gap-5">
      {showRuns && (
        <section className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="m-0 flex items-center gap-2 font-serif text-2xl font-normal">
              <Bot size={20} aria-hidden="true" />
              <Text value="Assisted applications · योजना आवेदन" />
            </h2>
            <Link to="/schemes" className="text-sm font-semibold">Explore schemes →</Link>
          </div>
          {runs.length === 0 ? (
            <EmptyState title="No assisted applications yet" action={<PillLink to="/schemes">Browse schemes →</PillLink>}>
              Open a scheme to start a live browser agent application.
            </EmptyState>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {runs.map((r) => (
                <Card key={r.id} className="flex flex-col justify-between gap-2.5 !p-4">
                  <div className="flex flex-col gap-1">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className={`badge ${r.status}`}>{translate(r.status, lang)}</span>
                      {r.scheme_slug && <small className="font-mono text-xs">{r.scheme_slug}</small>}
                    </div>
                    <h3 className="m-0 font-serif text-xl font-normal">{r.goal}</h3>
                    {r.receipt?.reference_no && (
                      <p className="m-0 text-sm"><Text value="Receipt:" /> <strong className="font-mono">{r.receipt.reference_no}</strong></p>
                    )}
                  </div>
                  <Link to={"/runs/" + encodeURIComponent(r.id)} className="text-sm font-semibold"><Text value="Open session →" /></Link>
                </Card>
              ))}
            </div>
          )}
        </section>
      )}

      {showCivic && (
        <section className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="m-0 flex items-center gap-2 font-serif text-2xl font-normal">
              <MapPin size={20} aria-hidden="true" />
              <Text value="Civic reports · नागरिक शिकायतें" />
            </h2>
            <Link to="/civic/new" className="text-sm font-semibold">+ Report an issue →</Link>
          </div>
          {reports.length === 0 ? (
            <EmptyState title="No civic reports yet" action={<PillLink to="/civic/new">Report an issue →</PillLink>}>
              Report a local water, road, electricity or sanitation problem and track it to CPGRAMS.
            </EmptyState>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {reports.map((c) => {
                const meta = statusMeta(c.status);
                return (
                  <Card key={c.id} className="flex flex-col justify-between gap-2.5 !p-4">
                    <div className="flex flex-col gap-1">
                      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                        <span className="font-semibold uppercase text-ink-soft">{c.department || c.category}</span>
                        <span className="rounded-full bg-peach px-2.5 py-0.5 font-semibold text-saffron-text">{meta.label}</span>
                      </div>
                      <h3 className="m-0 font-serif text-xl font-normal">{c.title}</h3>
                      {(c.cpgrams_ref || c.receipt_no) && (
                        <small className="font-mono font-bold">CPGRAMS: {c.cpgrams_ref || c.receipt_no}</small>
                      )}
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-ink-soft">👍 {c.upvotes ?? 1}</span>
                      <Link to={"/civic/" + encodeURIComponent(String(c.id))} className="font-semibold">Track timeline →</Link>
                    </div>
                  </Card>
                );
              })}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

export default function Runs() {
  const { profileId, lang } = useApp();
  const [runs, setRuns] = useState<RunOut[] | null>(null);
  const [reports, setReports] = useState<CivicReportOut[]>([]);
  const [unread, setUnread] = useState(0);
  const [tab, setTab] = useState<Tab>("all");
  const [error, setError] = useState("");

  async function load(signal?: AbortSignal) {
    setError("");
    const q = profileId ? `?profile_id=${encodeURIComponent(profileId)}` : "";
    try {
      const [runList, civicList, notifList] = await Promise.all([
        request<RunOut[]>(`/agent/runs${q}`, { signal }),
        listCivicReports({}, signal).catch(() => [] as CivicReportOut[]),
        profileId ? request<NotificationOut[]>(`/notifications${q}`, { signal }).catch(() => []) : Promise.resolve([] as NotificationOut[]),
      ]);
      if (signal?.aborted) return;
      setRuns(Array.isArray(runList) ? runList : []);
      const mine = profileId ? civicList.filter((r) => !r.profile_id || r.profile_id === profileId) : civicList;
      setReports(mine.length > 0 ? mine : civicList);
      setUnread(Array.isArray(notifList) ? notifList.filter((n) => !n.read).length : 0);
    } catch (e) {
      if (!signal?.aborted) setError((e as Error).message);
    }
  }

  useEffect(() => {
    const c = new AbortController();
    void load(c.signal);
    return () => c.abort();
  }, [profileId]);

  const showAlerts = tab === "all" || tab === "alerts";

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <Eyebrow>{tt(lang, "navActivity")} · मेरी गतिविधि</Eyebrow>
        <h1><Text value="My activity · आवेदन, शिकायतें और सूचनाएँ" /></h1>
        <p className="m-0 text-ink-soft">
          <Text value="Track your assisted scheme applications, CPGRAMS civic grievances, and official notifications in one place." />
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <StatTile accent value={runs?.length ?? 0} label="Assisted applications · आवेदन" />
        <StatTile value={reports.length} label="Civic reports · नागरिक शिकायतें" />
        <StatTile value={unread} label="Unread alerts · नई सूचनाएँ" />
      </div>

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Activity sections">
        {(
          [
            ["all", "All activity"],
            ["runs", `Applications (${runs?.length ?? 0})`],
            ["civic", `Civic reports (${reports.length})`],
            ["alerts", `Notifications (${unread})`],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={tab === key ? "!min-h-10 !px-4 !py-1.5 text-sm" : "secondary !min-h-10 !px-4 !py-1.5 text-sm"}
          >
            {label}
          </button>
        ))}
      </div>

      {error && <ErrorBox error={error} retry={() => void load()} />}

      {!runs ? (
        <Loading message="Loading your applications, civic reports and alerts…" />
      ) : (
        <>
          <ActivityView runs={runs} reports={reports} tab={tab} lang={lang} />
          {showAlerts && (
            <section className="flex flex-col gap-3">
              <h2 className="m-0 flex items-center gap-2 font-serif text-2xl font-normal">
                <Bell size={20} aria-hidden="true" />
                <Text value="Notifications · सूचनाएँ" />
              </h2>
              <Card><AlertsPanel /></Card>
            </section>
          )}
        </>
      )}
    </div>
  );
}
