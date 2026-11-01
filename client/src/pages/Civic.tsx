import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus, ThumbsUp } from "lucide-react";
import { getCivicStats, listCivicReports, statusMeta, voteCivicReport } from "../api/civic";
import type { CivicReportOut, CivicStatsOut } from "../api/civic";
import { ErrorBox, Loading } from "../components";
import { useApp } from "../context";
import { PillLink } from "../nav";
import { Card, EmptyState, Eyebrow, StatTile } from "../ui";
import CivicMap from "./CivicMap";

const statusTabs = [
  ["", "All"], ["open", "Open"], ["filed", "Filed on CPGRAMS"],
  ["citizen_verified", "Citizen verified"], ["still_broken", "Still broken"],
];
const toneClass: Record<string, string> = {
  ok: "bg-ok-soft text-ok", warn: "bg-warn-soft text-warn",
  bad: "bg-bad-soft text-bad", act: "bg-act-soft text-act", neutral: "bg-[#efe8dc] text-ink-soft",
};

export default function Civic() {
  const { profileId } = useApp();
  const navigate = useNavigate();
  const [reports, setReports] = useState<CivicReportOut[]>([]);
  const [stats, setStats] = useState<CivicStatsOut | null>(null);
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [state, setState] = useState("");
  const [district, setDistrict] = useState("");
  const [near, setNear] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [votingId, setVotingId] = useState<string | number | null>(null);

  async function load(signal?: AbortSignal) {
    setLoading(true);
    setError("");
    try {
      const [repList, statData] = await Promise.all([
        listCivicReports({ status, category, state, district, near }, signal),
        getCivicStats({ state, district }, signal).catch(() => null),
      ]);
      if (signal?.aborted) return;
      setReports(repList);
      setStats(statData);
    } catch (e) {
      if (!signal?.aborted) setError((e as Error).message);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }

  useEffect(() => {
    const c = new AbortController();
    void load(c.signal);
    return () => c.abort();
  }, [status, category, state, district, near]);

  async function handleVote(id: string | number) {
    setVotingId(id);
    try {
      const res = await voteCivicReport(id, profileId || undefined);
      setReports((list) =>
        list.map((r) => (r.id === id ? { ...r, upvotes: res.upvotes ?? r.upvotes + 1, status: res.status || r.status } : r)),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setVotingId(null);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <Eyebrow>Public accountability · नागरिक नक्शा</Eyebrow>
        <h1>Civic map &amp; local issues</h1>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <StatTile
          accent
          value={stats?.total ?? reports.length}
          label={`${stats?.open ?? 0} open · ${stats?.filed ?? 0} on CPGRAMS · ${stats?.resolved ?? 0} citizen-verified`}
        />
        <StatTile
          value={stats?.avg_days_open != null ? `${Math.round(stats.avg_days_open)}d` : "—"}
          label="Average days a report stays open"
        />
        <Card tint="peach" className="flex flex-col justify-between gap-3">
          <div>
            <strong className="font-serif text-2xl font-normal">See a problem on your street?</strong>
            <p className="m-0 text-sm text-ink-soft">सड़क, पानी, बिजली या सफ़ाई — फ़ोटो लें या बोलकर बताएँ</p>
          </div>
          <PillLink to="/civic/new" className="self-start">
            <Plus size={18} aria-hidden="true" />
            Report an issue · शिकायत दर्ज करें
          </PillLink>
        </Card>
      </div>

      <Card className="flex flex-col gap-3 !p-4">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by status">
          {statusTabs.map(([val, lbl]) => (
            <button
              key={val}
              type="button"
              onClick={() => setStatus(val)}
              className={status === val ? "!min-h-10 !px-4 !py-1.5 text-sm" : "secondary !min-h-10 !px-4 !py-1.5 text-sm"}
            >
              {lbl}
            </button>
          ))}
        </div>
        <div className="grid gap-2.5 sm:grid-cols-3">
          <select aria-label="Category" value={category} onChange={(e) => setCategory(e.target.value)} className="!m-0 !min-h-11">
            <option value="">All categories</option>
            <option value="water">Water / Jal Jeevan</option>
            <option value="roads">Roads &amp; drainage</option>
            <option value="sanitation">Sanitation / Swachhata</option>
            <option value="electricity">Electricity / Streetlights</option>
            <option value="ration_pds">Ration / PDS</option>
            <option value="other">Other civic issue</option>
          </select>
          <input aria-label="State" value={state} onChange={(e) => setState(e.target.value)} placeholder="State (e.g. Uttar Pradesh)" className="!m-0 !min-h-11" />
          <input aria-label="District" value={district} onChange={(e) => setDistrict(e.target.value)} placeholder="District (e.g. Varanasi)" className="!m-0 !min-h-11" />
        </div>
      </Card>

      {error && <ErrorBox error={error} retry={() => void load()} />}

      <div className="grid items-start gap-5 lg:grid-cols-[1.35fr_1fr]">
        <div className="flex flex-col gap-4">
          <CivicMap
            reports={reports}
            onSelect={(r) => navigate("/civic/" + encodeURIComponent(String(r.id)))}
            onNearMe={(lat, lng) => setNear(`${lat.toFixed(4)},${lng.toFixed(4)},25`)}
          />
          {stats && (!!stats.by_department?.length || !!stats.oldest_unresolved?.length) && (
            <Card className="flex flex-col gap-3">
              <h2 className="m-0 font-serif text-2xl font-normal">Department accountability · विभागवार स्थिति</h2>
              {stats.by_department?.map((d) => {
                const total = d.total || (d.open ?? 0) + (d.resolved ?? 0) || 1;
                const pct = d.resolved_pct ?? Math.round(((d.resolved ?? 0) / total) * 100);
                return (
                  <div key={d.department} className="flex flex-col gap-1">
                    <div className="flex justify-between text-sm">
                      <strong>{d.department}</strong>
                      <span className="text-ink-soft">
                        {pct}% resolved{d.avg_days != null ? ` · avg ${Math.round(d.avg_days)}d` : ""}
                      </span>
                    </div>
                    <div className="h-2.5 overflow-hidden rounded-full bg-[#efe8dc]">
                      <div className="h-full rounded-full bg-ok" style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
                    </div>
                  </div>
                );
              })}
              {!!stats.oldest_unresolved?.length && (
                <div className="mt-2 border-t border-line pt-3">
                  <Eyebrow>Oldest unresolved</Eyebrow>
                  <ul className="m-0 mt-2 flex list-none flex-col gap-1.5 p-0 text-sm">
                    {stats.oldest_unresolved.slice(0, 3).map((old) => (
                      <li key={old.id} className="flex justify-between gap-2">
                        <Link to={"/civic/" + encodeURIComponent(String(old.id))}>{old.title}</Link>
                        <span className="text-ink-soft">{old.department || old.category}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Card>
          )}
        </div>

        <div className="flex flex-col gap-3">
          {loading ? (
            <Loading message="Loading civic reports and accountability stats…" />
          ) : reports.length === 0 ? (
            <EmptyState title="No reports match this view" action={<PillLink to="/civic/new" tone="saffron">Report an issue →</PillLink>}>
              Adjust the filters above or report a local issue in your area.
            </EmptyState>
          ) : (
            reports.map((r) => {
              const meta = statusMeta(r.status);
              return (
                <Card key={r.id} className="flex flex-col gap-2.5 !rounded-[22px] !p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-soft">
                    <span className="font-semibold uppercase tracking-wider">
                      {r.department || r.category}{r.severity ? ` · ${r.severity}` : ""}
                    </span>
                    <span className={`rounded-full px-3 py-1 text-xs font-semibold ${toneClass[meta.tone]}`}>{meta.label}</span>
                  </div>
                  <h3 className="m-0 font-serif text-2xl font-normal">
                    <Link to={"/civic/" + encodeURIComponent(String(r.id))} className="text-ink no-underline hover:underline">{r.title}</Link>
                  </h3>
                  {(r.address || r.district || r.state) && (
                    <p className="m-0 text-sm text-ink-soft">{[r.address, r.district, r.state].filter(Boolean).join(", ")}</p>
                  )}
                  <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                    <button type="button" disabled={votingId === r.id} onClick={() => void handleVote(r.id)} className="!min-h-10 !bg-peach !px-3.5 !py-1.5 text-sm !text-saffron-text">
                      <ThumbsUp size={15} aria-hidden="true" /> {r.upvotes ?? 1} · +1 हमारे यहाँ भी
                    </button>
                    <Link to={"/civic/" + encodeURIComponent(String(r.id))} className="text-sm font-semibold">Track timeline →</Link>
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
