import { useTranslation, Text, useApp } from "../context";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Camera, CheckCircle2, LocateFixed, MapPin, Mic, Sparkles, ThumbsUp, Upload } from "lucide-react";
import { createReport, triageReport, voteReport } from "../api/civic";
import type { CivicTriage, SubmissionInput, TriageOut } from "../api/civic";
import { ErrorBox, Loading } from "../components";
import { tt } from "../ui-strings";
import { PillLink } from "../nav";
import { Card, EmptyState, Eyebrow, ProfileRequiredCard } from "../ui";
import { useRecorder } from "../useRecorder";
import CameraCapture from "./CameraCapture";

export default function CivicNew() {
  const tr = useTranslation();
  const { profileId, lang } = useApp();
  const navigate = useNavigate();
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState("");
  useEffect(() => {
    if (!photo) { setPhotoPreview(""); return; }
    const url = URL.createObjectURL(photo);
    setPhotoPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);
  const [audio, setAudio] = useState<Blob | null>(null);
  const [text, setText] = useState("");
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [camera, setCamera] = useState(false);
  const [locating, setLocating] = useState(false);
  const [triage, setTriage] = useState<TriageOut | null>(null);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const recorder = useRecorder(
    (blob) => setAudio(blob),
    () => setError("Microphone not available. Describe the issue in text or with a photo."),
  );
  const hasEvidence = !!(photo || audio || text.trim());

  function detectLocation() {
    if (!navigator.geolocation) return setError("Location is not available in this browser.");
    setLocating(true);
    setError("");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        setCoords({
          lat: Number(pos.coords.latitude.toFixed(6)),
          lng: Number(pos.coords.longitude.toFixed(6)),
        });
      },
      () => {
        setLocating(false);
        setError("Could not read your location. Allow location access and try again.");
      },
      { enableHighAccuracy: true, timeout: 15000 },
    );
  }

  const submission = (): SubmissionInput | null =>
    coords && profileId
      ? { profile_id: profileId, lat: coords.lat, lng: coords.lng, text, photo, photoName: photo?.name, audio }
      : null;

  async function runTriage() {
    const input = submission();
    if (!input || !hasEvidence) return;
    setBusy(true);
    setError("");
    try {
      const out = await triageReport(input);
      setTriage(out);
      setTitle(lang !== "en" && out.language === lang && out.title_local ? out.title_local : out.title);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function submitReport() {
    const input = submission();
    if (!input || !triage) return;
    setBusy(true);
    setError("");
    try {
      // Save exactly the triage the citizen saw (with their edited title); the server does not re-run AI.
      const { duplicates: _d, language: _l, address: _a, geocoding_attribution: _g, ...accepted } = triage;
      const created = await createReport(input, { ...(accepted as CivicTriage), title: title.trim() || triage.title });
      navigate("/civic/" + encodeURIComponent(created.id));
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  async function supportDuplicate(dupId: string) {
    if (!profileId) return;
    setBusy(true);
    setError("");
    try {
      await voteReport(dupId, profileId, "support");
      navigate("/civic/" + encodeURIComponent(dupId));
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  if (!profileId)
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-5">
        <div className="flex flex-col gap-1">
          <Link
            to="/civic"
            className="inline-flex min-h-11 items-center self-start text-sm font-semibold"
          >
             <Text value="← Civic map" /> </Link>
          <Eyebrow> <Text value="Speak up" /> </Eyebrow>
          <h1>
             <Text value="Report a local issue" /> </h1>
          <p className="m-0 text-ink-soft">
             <Text value="Take a photo or describe the issue by voice — AI will identify the department and draft the grievance." /> </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          {[
            {
              step: "1",
              title: "Photo or Voice",
              sub: "Attach a street photo or describe the issue in your language",
              Icon: Camera,
            },
            {
              step: "2",
              title: "Location",
              sub: "Pinpoint your street so neighbours can support with +1",
              Icon: LocateFixed,
            },
            {
              step: "3",
              title: "AI CPGRAMS Triage",
              sub: "Buddy identifies the department and drafts the formal grievance",
              Icon: Sparkles,
            },
          ].map(({ step, title: stepTitle, sub, Icon }) => (
            <Card key={step} className="flex flex-col gap-2 !p-4">
              <div className="flex items-center justify-between">
                <span className="grid h-8 w-8 place-items-center rounded-full bg-peach text-xs font-bold text-saffron-text">
                  {step}
                </span>
                <Icon size={18} aria-hidden="true" className="text-saffron-text" />
              </div>
              <strong className="font-serif text-lg font-normal text-ink">
                <Text value={stepTitle} />
              </strong>
              <p className="m-0 text-xs text-ink-soft"><Text value={sub} /></p>
            </Card>
          ))}
        </div>
        <ProfileRequiredCard context="civic" nextPath="/civic/new" />
      </div>
    );

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <div className="flex flex-col gap-1">
        <Link to="/civic" className="inline-flex min-h-11 items-center text-sm font-semibold"> <Text value="← Civic map" /> </Link>
        <Eyebrow> <Text value="Speak up" /> </Eyebrow>
        <h1>
           <Text value="Report a local issue" /> </h1>
        <p className="m-0 text-ink-soft"> <Text value="Take a photo or describe the issue by voice — AI will identify the department and draft the grievance." /> </p>
      </div>

      <Card className="flex flex-col gap-4">
        <h2 className="m-0 flex items-center gap-2 text-2xl"><span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-peach font-sans text-sm font-semibold text-saffron-text">1</span>  <Text value="Photo or voice" /> </h2>
        {photoPreview && <div className="flex items-center gap-3"><img src={photoPreview} alt={tr("Your attached evidence photo")} className="h-20 w-20 rounded-2xl border border-line object-cover" /><span className="text-sm text-ink-soft"> <Text value="Photo attached" /> </span></div>}
        <div className="flex flex-wrap gap-2.5">
          {typeof navigator !== "undefined" && !!navigator.mediaDevices && (
            <button type="button" disabled={busy} onClick={() => setCamera(true)}>
              <Camera size={18} aria-hidden="true" />  <Text value="Take photo" /> </button>
          )}
          <label className="inline-flex min-h-12 max-w-full cursor-pointer items-center gap-2 rounded-full bg-paper px-5 font-semibold shadow-[inset_0_0_0_1px_#d9cfc0]">
            <Upload size={18} aria-hidden="true" className="shrink-0" />
            <span className="truncate">{photo ? photo.name : tr("Upload photo")}</span>
            <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" className="sr-only" disabled={busy} onChange={(e) => { setPhoto(e.target.files?.[0] || null); setTriage(null); }} />
          </label>
          <button
            type="button"
            disabled={busy}
            aria-pressed={recorder.recording}
            onClick={() => (recorder.recording ? recorder.stop() : void recorder.start())}
            className={recorder.recording ? "!bg-bad !text-white" : "!bg-peach !text-saffron-text"}
          >
            <Mic size={18} aria-hidden="true" />
            {audio && !recorder.recording && <CheckCircle2 size={16} aria-hidden="true" className="shrink-0" />}
            {recorder.recording ? tr("Stop recording") : audio ? tr("Voice note attached") : tr("Record voice")}
          </button>
        </div>

        <label className="m-0">
           <Text value="Describe what happened (optional if photo or voice attached)" /> <textarea rows={3} value={text} disabled={busy} onChange={(e) => { setText(e.target.value); setTriage(null); }} placeholder={tr("e.g. The main water pipe in Ward 14 has been leaking for three days…")} />
        </label>

        <div className="flex flex-col gap-1.5 rounded-2xl bg-paper p-3.5">
          <h2 className="m-0 mb-2 flex items-center gap-2 text-2xl"><span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-white font-sans text-sm font-semibold text-saffron-text">2</span>  <Text value="Location" /> </h2>
          <button type="button" disabled={busy || locating} onClick={detectLocation} className="secondary self-start">
            <LocateFixed size={18} aria-hidden="true" />
            {locating ? tr("Locating…") : coords ? tr("Update location") : tr("Use my location")}
          </button>
          <p className="m-0 text-sm text-ink-soft">
            {coords
              ? <><MapPin size={16} aria-hidden="true" className="mr-1 inline shrink-0 text-saffron-text" />{coords.lat}, {coords.lng}  <Text value="— the address is looked up from OpenStreetMap." /> </>
              : tr("Location is needed to place the issue on the map and find nearby reports.")}
          </p>
        </div>

        <h2 className="m-0 flex items-center gap-2 text-2xl"><span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-peach font-sans text-sm font-semibold text-saffron-text">3</span>  <Text value="AI check" /> </h2>
        <button type="button" disabled={busy || !hasEvidence || !coords} onClick={() => void runTriage()} className="!bg-saffron-text !text-white">
          <Sparkles size={18} aria-hidden="true" />
           <Text value="Preview AI triage" /> </button>
      </Card>
      {error && <ErrorBox error={error} retry={() => void (triage ? submitReport() : runTriage())} />}
      {busy && <Loading message={triage ? tr("Saving your report…") : tr("AI is reading your report…")} />}

      {triage && !busy && (
        <Card className="flex flex-col gap-3">
          <Eyebrow> <Text value="AI triage" /> </Eyebrow>
          <div className="flex flex-wrap gap-2">
            <span className="rounded-full bg-ok-soft px-3 py-1 text-xs font-semibold text-ok">{triage.department}</span>
            <span className="rounded-full bg-[#FFE7D3] px-3 py-1 text-xs font-semibold capitalize text-saffron-text">
              <Text value={triage.category} /> · <Text value={triage.severity} />
            </span>
          </div>
          <p className="m-0 text-sm text-ink-soft">{triage.severity_reason}</p>
          {triage.address && <p className="m-0 text-sm"><MapPin size={16} aria-hidden="true" className="mr-1 inline shrink-0 text-saffron-text" />{triage.address}</p>}
          <label className="m-0">
             <Text value="Report title" /> <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
          </label>
          <div className="rounded-2xl bg-paper p-3.5 text-sm">
            <p className="m-0 text-ink-soft">{triage.description}</p>
          </div>
          {triage.duplicates.length > 0 && (
            <div className="rounded-2xl bg-peach p-4">
              <strong className="text-saffron-text">
                {triage.duplicates.length}  <Text value="similar report(s) nearby" /> </strong>
              <ul className="m-0 mt-2 flex list-none flex-col gap-2 p-0">
                {triage.duplicates.map((d) => (
                  <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-white p-3">
                    <div className="min-w-0 flex-1">
                      <Link to={"/civic/" + encodeURIComponent(d.id)} className="block break-words text-sm font-semibold">{d.title}</Link>
                      <small>
                        {d.distance_m != null ? `${Math.round(d.distance_m)} ${tr("m away")} · ` : ""}<ThumbsUp size={14} aria-hidden="true" className="mr-1 inline shrink-0" />{d.supporters}
                      </small>
                    </div>
                    <button type="button" disabled={busy} onClick={() => void supportDuplicate(d.id)} className="!min-h-11 !bg-saffron-text !px-4 !py-1.5 text-sm !text-white">
                      <ThumbsUp size={15} aria-hidden="true" />  <Text value="+1 Here too" /> </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <button type="button" disabled={busy || !title.trim()} onClick={() => void submitReport()}>
             <Text value="Confirm & submit new report" /> </button>
          {triage.geocoding_attribution && <small>{triage.geocoding_attribution}</small>}
        </Card>
      )}
      {camera && <CameraCapture onClose={() => setCamera(false)} onCapture={(f) => { setPhoto(f); setTriage(null); setCamera(false); }} />}
    </div>
  );
}


