import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Camera, LocateFixed, Mic, Sparkles, ThumbsUp, Upload } from "lucide-react";
import { createReport, triageReport, voteReport } from "../api/civic";
import type { CivicTriage, SubmissionInput, TriageOut } from "../api/civic";
import { ErrorBox, Loading } from "../components";
import { useApp } from "../context";
import { PillLink } from "../nav";
import { Card, EmptyState, Eyebrow } from "../ui";
import { useRecorder } from "../useRecorder";
import CameraCapture from "./CameraCapture";

export default function CivicNew() {
  const { profileId } = useApp();
  const navigate = useNavigate();
  const [photo, setPhoto] = useState<File | null>(null);
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
      setTitle(out.title);
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
      <div className="mx-auto flex max-w-2xl flex-col gap-4">
        <h1>Report a local issue · समस्या बताएँ</h1>
        <EmptyState title="Create a profile first" action={<PillLink to="/talk">Talk to Sahayak →</PillLink>}>
          Reports are linked to your profile so you can follow the official reply.
        </EmptyState>
      </div>
    );

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <div className="flex flex-col gap-1">
        <Link to="/civic" className="inline-flex min-h-11 items-center text-sm font-semibold">← Civic map · नागरिक नक्शा</Link>
        <Eyebrow>Speak up · आवाज़ उठाएँ</Eyebrow>
        <h1>Report a local issue · समस्या बताएँ</h1>
        <p className="m-0 text-ink-soft">फ़ोटो लें या अपनी आवाज़ में बताएँ — विभाग और अर्ज़ी AI तैयार करेगा</p>
      </div>

      <Card className="flex flex-col gap-4">
        <div className="flex flex-wrap gap-2.5">
          {typeof navigator !== "undefined" && !!navigator.mediaDevices && (
            <button type="button" disabled={busy} onClick={() => setCamera(true)}>
              <Camera size={18} aria-hidden="true" /> Take photo
            </button>
          )}
          <label className="inline-flex min-h-12 max-w-full cursor-pointer items-center gap-2 rounded-full bg-paper px-5 font-semibold shadow-[inset_0_0_0_1px_#d9cfc0]">
            <Upload size={18} aria-hidden="true" className="shrink-0" />
            <span className="truncate">{photo ? photo.name : "Upload photo"}</span>
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
            {recorder.recording ? "Stop recording" : audio ? "Voice note attached ✓" : "Record voice"}
          </button>
        </div>

        <label className="m-0">
          Describe what happened (optional if photo or voice attached)
          <textarea rows={3} value={text} disabled={busy} onChange={(e) => { setText(e.target.value); setTriage(null); }} placeholder="e.g. वार्ड 14 की मुख्य पाइपलाइन से 3 दिन से पानी बह रहा है…" />
        </label>

        <div className="flex flex-col gap-1.5 rounded-2xl bg-paper p-3.5">
          <button type="button" disabled={busy || locating} onClick={detectLocation} className="secondary self-start">
            <LocateFixed size={18} aria-hidden="true" />
            {locating ? "Locating…" : coords ? "Update location" : "Use my location"}
          </button>
          <p className="m-0 text-sm text-ink-soft">
            {coords
              ? `📍 ${coords.lat}, ${coords.lng} — the address is looked up from OpenStreetMap.`
              : "Location is needed to place the issue on the map and find nearby reports."}
          </p>
        </div>

        <button type="button" disabled={busy || !hasEvidence || !coords} onClick={() => void runTriage()} className="!bg-saffron-text !text-white">
          <Sparkles size={18} aria-hidden="true" />
          Preview AI triage · AI से जाँचें
        </button>
      </Card>
      {error && <ErrorBox error={error} retry={() => void (triage ? submitReport() : runTriage())} />}
      {busy && <Loading message={triage ? "Saving your report…" : "AI is reading your report…"} />}

      {triage && !busy && (
        <Card className="flex flex-col gap-3">
          <Eyebrow>AI ने समझा · AI triage</Eyebrow>
          <div className="flex flex-wrap gap-2">
            <span className="rounded-full bg-ok-soft px-3 py-1 text-xs font-semibold text-ok">{triage.department}</span>
            <span className="rounded-full bg-[#FFE7D3] px-3 py-1 text-xs font-semibold capitalize text-saffron-text">
              {triage.category} · {triage.severity}
            </span>
          </div>
          <p className="m-0 text-sm text-ink-soft">{triage.severity_reason}</p>
          {triage.address && <p className="m-0 text-sm">📍 {triage.address}</p>}
          <label className="m-0">
            Report title
            <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
          </label>
          <div className="rounded-2xl bg-paper p-3.5 text-sm">
            {triage.title_local && triage.title_local !== triage.title && (
              <p className="m-0 mb-1.5 font-medium">{triage.title_local}</p>
            )}
            <p className="m-0 text-ink-soft">{triage.description}</p>
          </div>
          {triage.duplicates.length > 0 && (
            <div className="rounded-2xl bg-peach p-4">
              <strong className="text-saffron-text">
                {triage.duplicates.length} similar report(s) nearby · पास में यही शिकायत पहले से दर्ज है
              </strong>
              <ul className="m-0 mt-2 flex list-none flex-col gap-2 p-0">
                {triage.duplicates.map((d) => (
                  <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-white p-3">
                    <div className="min-w-0 flex-1">
                      <Link to={"/civic/" + encodeURIComponent(d.id)} className="block break-words text-sm font-semibold">{d.title}</Link>
                      <small>
                        {d.distance_m != null ? `${Math.round(d.distance_m)} m away · ` : ""}👍 {d.supporters}
                      </small>
                    </div>
                    <button type="button" disabled={busy} onClick={() => void supportDuplicate(d.id)} className="!min-h-11 !bg-saffron-text !px-4 !py-1.5 text-sm !text-white">
                      <ThumbsUp size={15} aria-hidden="true" /> +1 हमारे यहाँ भी है
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <button type="button" disabled={busy || !title.trim()} onClick={() => void submitReport()}>
            Confirm &amp; submit new report · नई शिकायत दर्ज करें
          </button>
          {triage.geocoding_attribution && <small>{triage.geocoding_attribution}</small>}
        </Card>
      )}
      {camera && <CameraCapture onClose={() => setCamera(false)} onCapture={(f) => { setPhoto(f); setTriage(null); setCamera(false); }} />}
    </div>
  );
}


