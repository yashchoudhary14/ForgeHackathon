import { useTranslation, Text, useApp } from "../context";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Bell, Bot, CheckCircle2, Landmark, MapPin, RefreshCw, ThumbsUp, Upload, XCircle } from "lucide-react";
import {
  addEvidence,
  checkReportStatus,
  fileReport,
  firstPhoto,
  getReport,
  sourceBadge,
  statusMeta,
  voteReport,
} from "../api/civic";
import type { ReportOut, VoteKind } from "../api/civic";
import { assetUrl } from "../api/client";
import { ErrorBox, Loading } from "../components";
import { tt } from "../ui-strings";
import { Card, EmptyState, Eyebrow } from "../ui";

const badgeStyle = {
  citizen: "bg-ok-soft text-ok",
  system: "bg-act-soft text-act",
  official: "bg-warn-soft text-warn",
};
const dotStyle = { citizen: "bg-ok", system: "bg-act", official: "bg-saffron" };

/** Audit trail with official replies labelled apart from citizen and system notes. */
export function CivicTimelineView({ report }: { report: Pick<ReportOut, "events"> }) {
  const tr = useTranslation();
  const { lang } = useApp();
  if (!report.events?.length)
    return <EmptyState title={tr("No updates yet")}> <Text value="Updates from citizens and the department will appear here." /> </EmptyState>;
  return (
    <ol className="relative m-0 flex list-none flex-col gap-3.5 pl-6 before:absolute before:bottom-3 before:left-2 before:top-3 before:w-0.5 before:bg-line">
      {report.events.map((ev) => {
        const badge = sourceBadge(ev);
        if (badge.kind === "system") badge.label = tt(lang, "brandName");
        const media = (ev.meta?.media as { type?: string; url?: string }[] | undefined) ?? [];
        const photo = Array.isArray(media) ? media.find((m) => m.type === "photo")?.url : undefined;
        return (
          <li key={ev.id} className="relative">
            <span aria-hidden="true" className={`absolute -left-[22px] top-4 h-3.5 w-3.5 rounded-full border-[3px] border-paper ${dotStyle[badge.kind]}`} />
            <Card className={"flex flex-col gap-1.5 !rounded-tile border border-line !bg-card !p-4 !shadow-none " + (badge.kind === "official" ? "border-l-4 !border-l-saffron !bg-peach" : "")}>
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-soft">
                <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 font-semibold ${badgeStyle[badge.kind]}`}>{badge.kind === "official" && <Landmark size={14} aria-hidden="true" className="shrink-0" />}{badge.kind === "official" ? tr("Official CPGRAMS reply") : tr(badge.kind === "citizen" ? "Citizen" : badge.label)}</span>
                <time dateTime={ev.created_at}>{new Date(ev.created_at).toLocaleString(lang)}</time>
              </div>
              <p className="m-0 break-words text-[15px]">{ev.text}</p>
              {photo && <img src={assetUrl(photo)} alt={tr("Evidence photo")} className="mt-1 max-h-48 rounded-xl object-cover" />}
            </Card>
          </li>
        );
      })}
    </ol>
  );
}

export default function CivicTrack() {
  const tr = useTranslation();
  const { id = "" } = useParams();
  const { profileId, lang } = useApp();
  const navigate = useNavigate();
  const [report, setReport] = useState<ReportOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [evidencePhoto, setEvidencePhoto] = useState<File | null>(null);
  const [evidenceNote, setEvidenceNote] = useState("");

  async function load(signal?: AbortSignal) {
    setError("");
    try {
      setReport(await getReport(id, signal));
    } catch (e) {
      if (!signal?.aborted) setError((e as Error).message);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    const c = new AbortController();
    void load(c.signal);
    return () => c.abort();
  }, [id]);

  async function act(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const vote = (kind: VoteKind, message: string) =>
    act(async () => {
      await voteReport(id, profileId, kind);
      setNotice(message);
      await load();
    });

  // Both start an agent run on pgportal.gov.in; the citizen follows it on the run screen.
  const startRun = (fn: typeof fileReport) =>
    act(async () => {
      const res = await fn(id, profileId);
      navigate("/runs/" + encodeURIComponent(res.run_id));
    });

  const sendEvidence = () =>
    act(async () => {
      await addEvidence(id, { profile_id: profileId, text: evidenceNote, photo: evidencePhoto, photoName: evidencePhoto?.name });
      setEvidencePhoto(null);
      setEvidenceNote("");
      setNotice("Thank you. Your evidence was added to the timeline.");
      await load();
    });

  if (loading)
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-4">
        <Link
          to="/civic"
          className="inline-flex min-h-11 items-center self-start text-sm font-semibold"
        >
           <Text value="← Civic map" /> </Link>
        <Card tint="peach" className="flex flex-col gap-2">
          <Eyebrow> <Text value="Public accountability" /> </Eyebrow>
          <h1 className="m-0 font-serif text-3xl font-normal">
             <Text value="Civic report #" /> {id}
          </h1>
        </Card>
        <Loading message={tr("Loading civic report timeline…")} />
      </div>
    );
  if (!report)
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-4">
        <Link to="/civic" className="inline-flex min-h-11 items-center text-sm font-semibold"> <Text value="← Civic map" /> </Link>
        <ErrorBox error={error || "We couldn’t find that item. Go back to the list or try again."} retry={() => void load()} />
      </div>
    );

  const meta = statusMeta(report.status);
  const mine = !!profileId && report.profile_id === profileId;
  const photo = firstPhoto(report);
  const closed = report.status === "closed" || report.status === "resolved";

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <Link to="/civic" className="inline-flex min-h-11 items-center self-start text-sm font-semibold"> <Text value="← Civic map" /> </Link>

      <Card tint="peach" className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-lg bg-peach px-2.5 py-1 text-xs font-semibold text-saffron-text"><Text value={meta.label} /></span>
          <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold">{report.department}</span>
          <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold capitalize"><Text value={report.category} /> · <Text value={report.severity} /></span>
          {report.official_ref && (
            <span className="break-all rounded-full bg-white px-3 py-1 font-mono text-xs font-bold">{report.official_ref}</span>
          )}
        </div>
        <h1 className="m-0 break-words font-serif text-3xl font-normal">{lang !== "en" && report.language === lang && report.title_local ? report.title_local : report.title}</h1>
        <p className="m-0 text-sm text-ink-soft">{report.description}</p>
        {photo && <img src={assetUrl(photo)} alt={tr("Photo of the reported issue")} className="max-h-64 w-full rounded-2xl object-cover" />}
        {report.address && <small className="break-words"><MapPin size={15} aria-hidden="true" className="mr-1 inline shrink-0" />{report.address}</small>}
        <small><ThumbsUp size={15} aria-hidden="true" className="mr-1 inline shrink-0" />{report.supporters} · {new Date(report.created_at).toLocaleDateString(lang)}</small>
        {profileId ? (
          <div className="flex flex-wrap gap-2 pt-1">
            {!mine && (
              <button type="button" disabled={busy} onClick={() => void vote("support", "Your +1 was added.")} className="secondary !min-h-11 !px-4 text-sm">
                <ThumbsUp size={16} aria-hidden="true" />  <Text value="+1 Here too" /> </button>
            )}
            {!mine && (
              <button type="button" disabled={busy} onClick={() => void vote("follow", "You will get alerts for this report.")} className="secondary !min-h-11 !px-4 text-sm">
                <Bell size={16} aria-hidden="true" />  <Text value="Follow" /> </button>
            )}
            {mine && !report.official_ref && !closed && (
              <button type="button" disabled={busy} onClick={() => void startRun(fileReport)} className="!min-h-11 !bg-act !px-4 text-sm !text-white">
                <Bot size={16} aria-hidden="true" />  <Text value="File on CPGRAMS" /> </button>
            )}
            {mine && report.official_ref && (
              <button type="button" disabled={busy} onClick={() => void startRun(checkReportStatus)} className="secondary !min-h-11 !px-4 text-sm">
                <RefreshCw size={16} aria-hidden="true" />  <Text value="Check status" /> </button>
            )}
          </div>
        ) : (
          <p className="m-0 text-sm">
            <Link to="/talk"> <Text value="Create a profile" /> </Link>  <Text value="to support or follow this report." /> </p>
        )}
      </Card>

      {busy && <Loading />}
      {error && <ErrorBox error={error} retry={() => void load()} />}
      {notice && <p role="status" className="m-0 rounded-2xl bg-ok-soft p-3 text-sm font-semibold text-ok"><Text value={notice} /></p>}
      {report.official_status && (
        <Card tint="blue" className="!p-4 text-sm">
          <strong> <Text value="Official CPGRAMS status:" /> </strong> {report.official_status}
        </Card>
      )}

      <Eyebrow> <Text value="Audit trail" /> </Eyebrow>
      <CivicTimelineView report={report} />

      {profileId && (
        <Card tint="peach" className="flex flex-col gap-3">
          <strong className="font-serif text-2xl font-normal"> <Text value="Is this fixed on the ground?" /> </strong>
          <p className="m-0 text-sm text-ink-soft"> <Text value="Citizen confirmations are shown separately from official replies." /> </p>
          <div className="grid gap-2.5 sm:grid-cols-2">
            <button type="button" disabled={busy} onClick={() => void vote("still_broken", "Marked as still broken.")} className="!bg-bad-soft !text-bad">
              <XCircle size={18} aria-hidden="true" />  <Text value="Still broken" /> </button>
            <button type="button" disabled={busy} onClick={() => void vote("fixed", "Marked as fixed. Thank you.")} className="!bg-ok !text-white">
              <CheckCircle2 size={18} aria-hidden="true" />  <Text value="Fixed" /> </button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="inline-flex min-h-11 max-w-full cursor-pointer items-center gap-2 rounded-full border border-line bg-card px-4 text-sm font-semibold">
              <Upload size={16} aria-hidden="true" className="shrink-0" />
              <span className="truncate">{evidencePhoto ? evidencePhoto.name : tr("Attach photo proof")}</span>
              <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" className="sr-only" disabled={busy} onChange={(e) => setEvidencePhoto(e.target.files?.[0] || null)} />
            </label>
            <input aria-label={tr("Note from the ground")} value={evidenceNote} disabled={busy} onChange={(e) => setEvidenceNote(e.target.value)} placeholder={tr("Note from the ground…")} className="!m-0 !min-h-11 min-w-0 flex-1 basis-48" />
            <button type="button" disabled={busy || (!evidencePhoto && !evidenceNote.trim())} onClick={() => void sendEvidence()} className="secondary !min-h-11">
               <Text value="Add evidence" /> </button>
          </div>
        </Card>
      )}
    </div>
  );
}

