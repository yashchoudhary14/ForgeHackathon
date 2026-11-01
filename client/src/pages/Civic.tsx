import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus, ThumbsUp } from "lucide-react";
import { categories, getReportStats, listReports, statusMeta, voteReport } from "../api/civic";
import type { ReportOut, ReportStats } from "../api/civic";
import { ErrorBox, Loading } from "../components";
import { useApp } from "../context";
import { PillLink } from "../nav";
import { Card, EmptyState, Eyebrow, StatTile } from "../ui";
import CivicMap from "./CivicMap";

const statusTabs: [string, string][] = [
  ["", "All"],
  ["open", "Open"],
  ["filed", "Filed on CPGRAMS"],
  ["in_progress", "In progress"],
  ["resolved", "Resolved"],
];
const toneClass: Record<string, string> = {
  ok: "bg-ok-soft text-ok",
  warn: "bg-warn-soft text-warn",
  bad: "bg-bad-soft text-bad",
  act: "bg-act-soft text-[#1f4fa8]",
  neutral: "bg-[#efe8dc] text-ink-soft",
};

export default function Civic() {
  const { profileId } = useApp();
  const navigate = useNavigate();
  const [reports, setReports] = useState<ReportOut[] | null>(null);
  const [stats, setStats] = useState<ReportStats | null>(null);
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [near, setNear] = useState<{ lat: number; lng: number } | null>(null);
  const [error, setError] = useState("");
  const [votingId, setVotingId] = useState<string | null>(null);

  async function load(signal?: AbortSignal) {
    setError("");
    try {
      const [list, s] = await Promise.all([
        listReports({ status, category, ...(near ? { lat: near.lat, lng: near.lng, radius_km: 25 } : {}) }, signal),
        getReportStats(signal).catch(() => null),
      ]);
      if (signal?.aborted) return;
      setReports(list);
      setStats(s);
    } catch (e) {
      if (!signal?.aborted) {
        setReports((r) => r ?? []);
        setError((e as Error).message);
      }
    }
  }

  useEffect(() => {
    setReports(null);
    const c = new AbortController();
    void load(c.signal);
    return () => c.abort();
  }, [status, category, near]);

  async function support(reportId: string) {
    if (!profileId) return navigate("/talk");
    setVotingId(reportId);
    try {
      const updated = await voteReport(reportId, profileId, "support");
      setReports((list) => list?.map((r) => (r.id === reportId ? { ...r, supporters: updated.supporters } : r)) ?? list);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setVotingId(null);
    }
  }

  const onSelect = useCallback((r: ReportOut) => navigate("/civic/" + encodeURIComponent(r.id)), [navigate]);
  const onNearMe = useCallback((lat: number, lng: number) => setNear({ lat, lng }), []);
  const openByDept = Object.entries(stats?.open_by_department ?? {}).sort((a, b) => b[1] - a[1]);
  const byStatus = stats?.by_status ?? {};

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <Eyebrow>Public accountability · नागरिक नक्शा</Eyebrow>
        <h1>Civic map &amp; local issues</h1>
      </div>

      {stats && stats.total === 0 && (reports?.length ?? 0) === 0 ? (
        <Card
          tint="peach"
          className="flex flex-col justify-between gap-4 md:flex-row md:items-center"
        >
          <div className="flex flex-col gap-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-saffron-text">
              NEIGHBOURHOOD ACCOUNTABILITY · जन-सुनवाई
            </span>
            <strong className="font-serif text-2xl font-normal text-ink">
              Be the first in your neighbourhood to report a street, water, or
              electricity issue
            </strong>
            <p className="m-0 text-sm text-ink-soft">
              सड़क, पानी, बिजली या सफ़ाई — फ़ोटो लें या बोलकर बताएँ, Buddy विभाग
              की पहचान कर CPGRAMS अर्ज़ी तैयार करेगा।
            </p>
          </div>
          <PillLink to="/civic/new" className="self-start md:shrink-0">
            <Plus size={18} aria-hidden="true" />
            Report an issue · शिकायत दर्ज करें
          </PillLink>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-3">
          <StatTile
            accent
            value={stats?.total ?? "—"}
            label={`${byStatus.open ?? 0} open · ${byStatus.filed ?? 0} filed · ${(byStatus.resolved ?? 0) + (byStatus.closed ?? 0)} resolved`}
          />
          <StatTile
            value={stats ? stats.official_number : "—"}
            label={`with an official CPGRAMS number · ${stats?.confirmed_by_others ?? 0} confirmed by neighbours`}
          />
          <Card tint="peach" className="flex flex-col justify-between gap-3">
            <div>
              <strong className="font-serif text-2xl font-normal">
                See a problem on your street?
              </strong>
              <p className="m-0 text-sm text-ink-soft">
                सड़क, पानी, बिजली या सफ़ाई — फ़ोटो लें या बोलकर बताएँ
              </p>
            </div>
            <PillLink to="/civic/new" className="self-start">
              <Plus size={18} aria-hidden="true" />
              Report an issue · शिकायत दर्ज करें
            </PillLink>
          </Card>
        </div>
      )}

      <Card className="flex flex-col gap-3 !p-4">
        <div
          className="flex gap-2 overflow-x-auto pb-1"
          role="group"
          aria-label="Filter by status"
        >
          {statusTabs.map(([val, lbl]) => (
            <button
              key={val}
              type="button"
              aria-pressed={status === val}
              onClick={() => setStatus(val)}
              className={(status === val ? "" : "secondary ") + "!min-h-11 shrink-0 !rounded-full !px-4 !py-1.5 text-sm"}
            >
              {lbl}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <select aria-label="Category" value={category} onChange={(e) => setCategory(e.target.value)} className="!m-0 !min-h-11 !w-auto min-w-0 flex-1 capitalize">
            <option value="">All categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          {near && (
            <button type="button" className="secondary !min-h-11 text-sm" onClick={() => setNear(null)}>
              Showing 25 km around you · Show all
            </button>
          )}
        </div>
      </Card>

      {error && <ErrorBox error={error} retry={() => void load()} />}

      <div className="grid items-start gap-5 lg:grid-cols-[1.35fr_1fr]">
        <div className="flex min-w-0 flex-col gap-4">
          <CivicMap reports={reports ?? []} onSelect={onSelect} onNearMe={onNearMe} />
          {openByDept.length > 0 && (
            <Card className="flex flex-col gap-3">
              <h2 className="m-0 font-serif text-2xl font-normal">Open issues by department · विभागवार</h2>
              {openByDept.map(([dept, open]) => {
                const total = stats?.by_department[dept] ?? open;
                const pct = total ? Math.round(((total - open) / total) * 100) : 0;
                return (
                  <div key={dept} className="flex flex-col gap-1">
                    <div className="flex flex-wrap justify-between gap-x-2 text-sm">
                      <strong className="min-w-0 break-words">{dept}</strong>
                      <span className="text-ink-soft">{open} open of {total}</span>
                    </div>
                    <div className="h-2.5 overflow-hidden rounded-full bg-[#efe8dc]" role="img" aria-label={`${pct}% no longer open`}>
                      <div className="h-full rounded-full bg-ok" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </Card>
          )}
        </div>

        <div className="flex min-w-0 flex-col gap-3">
          {!reports ? (
            <Loading message="Loading civic reports and accountability stats…" />
          ) : reports.length === 0 ? (
            !error && (
              <EmptyState title="No reports match this view" action={<PillLink to="/civic/new" tone="saffron">Report an issue →</PillLink>}>
                Change the filters or report a local issue in your area.
              </EmptyState>
            )
          ) : (
            reports.map((r) => {
              const meta = statusMeta(r.status);
              return (
                <Card key={r.id} className="flex flex-col gap-2.5 !rounded-[22px] !p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-soft">
                    <span className="min-w-0 break-words font-semibold uppercase tracking-wider">
                      {r.department} · {r.severity}
                    </span>
                    <span className={`rounded-full px-3 py-1 text-xs font-semibold ${toneClass[meta.tone]}`}>{meta.label}</span>
                  </div>
                  <h3 className="m-0 break-words font-serif text-2xl font-normal">
                    <Link to={"/civic/" + encodeURIComponent(r.id)} className="text-ink no-underline hover:underline">{r.title}</Link>
                  </h3>
                  {r.address && <p className="m-0 line-clamp-2 text-sm text-ink-soft">{r.address}</p>}
                  <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                    <button
                      type="button"
                      disabled={votingId === r.id || r.profile_id === profileId}
                      onClick={() => void support(r.id)}
                      className="!min-h-11 !rounded-full !bg-peach !px-3.5 !py-1.5 text-sm !text-saffron-text"
                    >
                      <ThumbsUp size={15} aria-hidden="true" /> {r.supporters} · +1 हमारे यहाँ भी
                    </button>
                    <Link to={"/civic/" + encodeURIComponent(r.id)} className="inline-flex min-h-11 items-center text-sm font-semibold">Track timeline →</Link>
                  </div>
                </Card>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}

