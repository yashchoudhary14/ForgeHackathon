import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Bot, CheckCircle2, RefreshCw, ThumbsUp, Upload, XCircle } from "lucide-react";
import {
  actorBadge,
  checkCivicStatus,
  fileCivicOnCpgrams,
  getCivicReport,
  statusMeta,
  submitCivicEvidence,
  voteCivicReport,
} from "../api/civic";
import type { CivicEvent, CivicReportOut } from "../api/civic";
import { assetUrl } from "../api/client";
import { ErrorBox, Loading } from "../components";
import { useApp } from "../context";
import { Card, Eyebrow } from "../ui";

const badgeStyle = { citizen: "bg-ok-soft text-ok", agent: "bg-act-soft text-act", official: "bg-warn-soft text-warn" };
const dotStyle = { citizen: "bg-ok", agent: "bg-act", official: "bg-saffron" };

export function CivicTimelineView({ report }: { report: CivicReportOut }) {
  const events: CivicEvent[] =
    report.events && report.events.length > 0
      ? report.events
      : [{ id: "created", actor: "citizen", title: "Report submitted · शिकायत दर्ज की गई", note: report.description || report.draft_hi || report.draft_en, created_at: report.created_at }];
  return (
    <ol className="relative m-0 flex list-none flex-col gap-3.5 pl-6 before:absolute before:bottom-3 before:left-2 before:top-3 before:w-0.5 before:bg-[#e5dccf]">
      {events.map((ev, i) => {
        const badge = actorBadge(ev);
        const photo = ev.photo_url ? assetUrl(ev.photo_url) : undefined;
        return (
          <li key={ev.id ?? i} className="relative">
            <span aria-hidden="true" className={`absolute -left-[22px] top-4 h-3.5 w-3.5 rounded-full border-[3px] border-paper ${dotStyle[badge.kind]}`} />
            <Card className="flex flex-col gap-1.5 !rounded-[18px] !p-4">
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-soft">
                <span className={`rounded-full px-2.5 py-0.5 font-semibold ${badgeStyle[badge.kind]}`}>{badge.label}</span>
                {ev.created_at && <time dateTime={ev.created_at}>{new Date(ev.created_at).toLocaleString()}</time>}
              </div>
              <strong className="text-base">{ev.title || (ev.status ? ev.status.replaceAll("_", " ") : "Update")}</strong>
              {(ev.note || ev.body) && <p className="m-0 text-sm text-ink-soft">{ev.note || ev.body}</p>}
              {ev.receipt_no && <span className="self-start rounded-lg bg-paper px-2.5 py-1 font-mono text-xs font-bold">{ev.receipt_no}</span>}
              {photo && <img src={photo} alt="Report evidence" className="mt-1 max-h-48 rounded-xl object-cover" />}
            </Card>
          </li>
        );
      })}
    </ol>
  );
}

export default function CivicTrack() {
  const { id = "" } = useParams();
  const { profileId } = useApp();
  const navigate = useNavigate();
  const [report, setReport] = useState<CivicReportOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [statusNote, setStatusNote] = useState("");
  const [evidencePhoto, setEvidencePhoto] = useState<File | null>(null);
  const [evidenceNote, setEvidenceNote] = useState("");

  async function load(signal?: AbortSignal) {
    setLoading(true);
    setError("");
    try {
      setReport(await getCivicReport(id, signal));
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
  }, [id]);

  async function onVote() {
    if (!report) return;
    setBusy(true);
    setError("");
    try {
      const res = await voteCivicReport(report.id, profileId || undefined);
      setReport((r) => (r ? { ...r, upvotes: res.upvotes ?? r.upvotes + 1, status: res.status || r.status } : r));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function onFileCpgrams() {
    if (!report) return;
    setBusy(true);
    setError("");
    try {
      const res = await fileCivicOnCpgrams(report.id, profileId || undefined);
      if (res.run_id) navigate("/runs/" + encodeURIComponent(res.run_id));
      else await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function onCheckStatus() {
    if (!report) return;
    setBusy(true);
    setError("");
    try {
      const res = await checkCivicStatus(report.id, profileId || undefined);
      setStatusNote(res.official_note || `Current status: ${res.status}`);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function onEvidence(verdict: "citizen_verified" | "still_broken") {
    if (!report) return;
    setBusy(true);
    setError("");
    try {
      const updated = await submitCivicEvidence(report.id, {
        status: verdict,
        photo: evidencePhoto,
        photoName: evidencePhoto?.name,
        note: evidenceNote,
        profile_id: profileId || undefined,
      });
      setReport(updated);
      setEvidencePhoto(null);
      setEvidenceNote("");
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Loading message="Loading civic report timeline…" />;
  if (error && !report) return <ErrorBox error={error} retry={() => void load()} />;
  if (!report) return null;

  const meta = statusMeta(report.status);
  const refNo = report.cpgrams_ref || report.receipt_no;

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link to="/civic" className="text-sm font-semibold">← Civic map · सभी शिकायतें</Link>
        <span className="text-xs font-semibold text-ink-soft">Report #{report.id}</span>
      </div>

      <Card tint="peach" className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-[#FFE7D3] px-3 py-1 text-xs font-semibold text-saffron-text">{meta.label}</span>
          <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold">{report.department || report.category}</span>
          {refNo && <span className="rounded-full bg-white px-3 py-1 font-mono text-xs font-bold">{refNo}</span>}
        </div>
        <h1 className="m-0 font-serif text-3xl font-normal">{report.title}</h1>
        {(report.description || report.draft_hi || report.draft_en) && (
          <p className="m-0 text-sm text-ink-soft">{report.description || report.draft_hi || report.draft_en}</p>
        )}
        {(report.address || report.district || report.state) && (
          <small>📍 {[report.address, report.district, report.state].filter(Boolean).join(", ")}</small>
        )}
        <div className="flex flex-wrap gap-2 pt-1">
          <button type="button" disabled={busy} onClick={() => void onVote()} className="secondary !min-h-11 !px-4 text-sm">
            <ThumbsUp size={16} aria-hidden="true" /> +1 ({report.upvotes ?? 1}) हमारे यहाँ भी
          </button>
          <button type="button" disabled={busy} onClick={() => void onFileCpgrams()} className="!min-h-11 !bg-act !px-4 text-sm !text-white">
            <Bot size={16} aria-hidden="true" /> File on CPGRAMS · CPGRAMS पर भेजें
          </button>
          <button type="button" disabled={busy} onClick={() => void onCheckStatus()} className="secondary !min-h-11 !px-4 text-sm">
            <RefreshCw size={16} aria-hidden="true" /> Check status · स्थिति जाँचें
          </button>
        </div>
        {report.run_id && (
          <Link to={"/runs/" + encodeURIComponent(report.run_id)} className="text-sm font-semibold">Open live CPGRAMS agent session →</Link>
        )}
      </Card>

      {error && <ErrorBox error={error} retry={() => void load()} />}
      {(statusNote || report.official_note) && (
        <Card tint="blue" className="!p-4 text-sm">
          <div role="status"><strong>Official CPGRAMS status:</strong> {statusNote || report.official_note}</div>
        </Card>
      )}

      <Eyebrow>Audit trail · अब तक क्या हुआ</Eyebrow>
      <CivicTimelineView report={report} />

      <Card tint="peach" className="flex flex-col gap-3">
        <strong className="font-serif text-2xl font-normal">Is this fixed on the ground? · क्या यह समस्या सच में ठीक हो गई?</strong>
        <p className="m-0 text-sm text-ink-soft">Official replies only close a report after citizens confirm on site with a photo.</p>
        <div className="flex flex-wrap items-center gap-2">
          <label className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-full bg-white px-4 text-sm font-semibold shadow-[inset_0_0_0_1px_#d9cfc0]">
            <Upload size={16} aria-hidden="true" /> {evidencePhoto ? evidencePhoto.name : "Attach photo proof"}
            <input type="file" accept="image/*" capture="environment" className="sr-only" disabled={busy} onChange={(e) => setEvidencePhoto(e.target.files?.[0] || null)} />
          </label>
          <input aria-label="Verification note" value={evidenceNote} disabled={busy} onChange={(e) => setEvidenceNote(e.target.value)} placeholder="Optional note from the ground…" className="!m-0 min-w-[200px] flex-1 !min-h-11" />
        </div>
        <div className="grid gap-2.5 sm:grid-cols-2">
          <button type="button" disabled={busy} onClick={() => void onEvidence("still_broken")} className="!bg-bad-soft !text-bad">
            <XCircle size={18} aria-hidden="true" /> Still broken · नहीं, अब भी ख़राब है
          </button>
          <button type="button" disabled={busy} onClick={() => void onEvidence("citizen_verified")} className="!bg-ok !text-white">
            <CheckCircle2 size={18} aria-hidden="true" /> Verified fixed · हाँ, ठीक हो गया
          </button>
        </div>
      </Card>
    </div>
  );
}
