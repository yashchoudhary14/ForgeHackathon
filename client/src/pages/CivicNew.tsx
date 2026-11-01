import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Camera, LocateFixed, Mic, Sparkles, ThumbsUp, Upload } from "lucide-react";
import { createCivicReport, triageCivic, voteCivicReport } from "../api/civic";
import type { CivicTriageOut } from "../api/civic";
import { ErrorBox, Loading } from "../components";
import { useApp } from "../context";
import { Card, Eyebrow } from "../ui";
import { useRecorder } from "../useRecorder";
import CameraCapture from "./CameraCapture";

export default function CivicNew() {
  const { profileId, lang } = useApp();
  const navigate = useNavigate();
  const [photo, setPhoto] = useState<File | null>(null);
  const [audio, setAudio] = useState<Blob | null>(null);
  const [text, setText] = useState("");
  const [address, setAddress] = useState("");
  const [district, setDistrict] = useState("");
  const [state, setState] = useState("");
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [camera, setCamera] = useState(false);
  const [locating, setLocating] = useState(false);
  const [triage, setTriage] = useState<CivicTriageOut | null>(null);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("water");
  const [severity, setSeverity] = useState("high");
  const [department, setDepartment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const recorder = useRecorder(
    (blob) => setAudio(blob),
    () => setError("Microphone not available. Describe the issue in text or with a photo."),
  );

  function detectLocation() {
    if (!navigator.geolocation) return setError("Location is not available in this browser. Enter your area below.");
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        setCoords({ lat: Number(pos.coords.latitude.toFixed(5)), lng: Number(pos.coords.longitude.toFixed(5)) });
      },
      () => { setLocating(false); setError("Could not read GPS location. Enter your street or ward below."); },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }

  async function runTriage() {
    if (!photo && !audio && !text.trim()) return;
    setBusy(true);
    setError("");
    try {
      const out = await triageCivic({
        photo,
        photoName: photo?.name,
        audio,
        text,
        lat: coords?.lat ?? null,
        lng: coords?.lng ?? null,
        lang,
      });
      setTriage(out);
      setTitle(out.draft_title || text.slice(0, 80) || "Local civic issue");
      if (out.category) setCategory(out.category);
      if (out.severity) setSeverity(out.severity);
      if (out.department) setDepartment(out.department);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function submitReport() {
    setBusy(true);
    setError("");
    try {
      const created = await createCivicReport({
        profile_id: profileId || null,
        category: category || triage?.category || "other",
        severity: severity || triage?.severity || "medium",
        department: department || triage?.department || undefined,
        title: title.trim() || triage?.draft_title || text.trim() || "Civic report",
        description: text.trim() || triage?.draft_en || triage?.draft_hi || undefined,
        draft_hi: triage?.draft_hi,
        draft_en: triage?.draft_en,
        lat: coords?.lat ?? null,
        lng: coords?.lng ?? null,
        address: address.trim() || undefined,
        district: district.trim() || undefined,
        state: state.trim() || undefined,
        photo,
        photoName: photo?.name,
        audio,
      });
      navigate("/civic/" + encodeURIComponent(String(created.id)));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function upvoteDuplicate(dupId: number | string) {
    setBusy(true);
    setError("");
    try {
      await voteCivicReport(dupId, profileId || undefined);
      navigate("/civic/" + encodeURIComponent(String(dupId)));
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <div className="flex flex-col gap-1">
        <Link to="/civic" className="text-sm font-semibold">← Civic map · नागरिक नक्शा</Link>
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
          <label className="inline-flex min-h-12 cursor-pointer items-center gap-2 rounded-full bg-paper px-5 font-semibold shadow-[inset_0_0_0_1px_#d9cfc0]">
            <Upload size={18} aria-hidden="true" />
            {photo ? photo.name : "Upload photo"}
            <input type="file" accept="image/*" capture="environment" className="sr-only" disabled={busy} onChange={(e) => setPhoto(e.target.files?.[0] || null)} />
          </label>
          <button
            type="button"
            disabled={busy}
            onClick={() => (recorder.recording ? recorder.stop() : void recorder.start())}
            className={recorder.recording ? "!bg-bad !text-white" : "!bg-peach !text-saffron-text"}
          >
            <Mic size={18} aria-hidden="true" />
            {recorder.recording ? "Stop recording" : audio ? "Voice note attached ✓" : "Record voice"}
          </button>
          <button type="button" disabled={busy || locating} onClick={detectLocation} className="secondary">
            <LocateFixed size={18} aria-hidden="true" />
            {coords ? `📍 ${coords.lat}, ${coords.lng}` : locating ? "Locating…" : "Tag GPS location"}
          </button>
        </div>

        <label className="m-0">
          Describe what happened (optional if photo or voice attached)
          <textarea rows={3} value={text} disabled={busy} onChange={(e) => setText(e.target.value)} placeholder="e.g. वार्ड 14 की मुख्य पाइपलाइन से 3 दिन से पानी बह रहा है…" />
        </label>

        <div className="grid gap-2.5 sm:grid-cols-3">
          <input aria-label="Street or ward" value={address} disabled={busy} onChange={(e) => setAddress(e.target.value)} placeholder="Ward / landmark" className="!m-0" />
          <input aria-label="District" value={district} disabled={busy} onChange={(e) => setDistrict(e.target.value)} placeholder="District" className="!m-0" />
          <input aria-label="State" value={state} disabled={busy} onChange={(e) => setState(e.target.value)} placeholder="State" className="!m-0" />
        </div>

        <button type="button" disabled={busy || (!photo && !audio && !text.trim())} onClick={() => void runTriage()} className="!bg-saffron !text-white">
          <Sparkles size={18} aria-hidden="true" />
          {busy && !triage ? "AI is analysing your report…" : "Preview AI triage · AI से जाँचें"}
        </button>
      </Card>

      {error && <ErrorBox error={error} retry={() => void (triage ? submitReport() : runTriage())} />}
      {busy && <Loading message="Preparing your civic grievance…" />}

      {triage && (
        <Card className="flex flex-col gap-3">
          <Eyebrow>AI ने समझा · AI Triage Preview</Eyebrow>
          <div className="flex flex-wrap gap-2">
            <span className="rounded-full bg-ok-soft px-3 py-1 text-xs font-semibold text-ok">{department || triage.department || triage.category}</span>
            <span className="rounded-full bg-[#FFE7D3] px-3 py-1 text-xs font-semibold text-saffron-text">Severity: {severity || triage.severity}</span>
          </div>
          <label className="m-0">
            Report title
            <input value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          {(triage.draft_hi || triage.draft_en) && (
            <div className="rounded-2xl bg-paper p-3.5 text-sm">
              {triage.draft_hi && <p className="m-0 mb-1.5 font-medium">{triage.draft_hi}</p>}
              {triage.draft_en && <p className="m-0 text-ink-soft">{triage.draft_en}</p>}
            </div>
          )}
          {!!triage.duplicates?.length && (
            <div className="rounded-2xl bg-peach p-4">
              <strong className="text-saffron-text">{triage.duplicates.length} similar report(s) nearby · पास में यही शिकायत पहले से दर्ज है</strong>
              <ul className="m-0 mt-2 flex list-none flex-col gap-2 p-0">
                {triage.duplicates.map((d) => (
                  <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-white p-3">
                    <div>
                      <strong className="block text-sm">{d.title}</strong>
                      <small>{d.distance_m != null ? `${Math.round(d.distance_m)}m away · ` : ""}👍 {d.upvotes ?? 1} citizens</small>
                    </div>
                    <button type="button" disabled={busy} onClick={() => void upvoteDuplicate(d.id)} className="!min-h-10 !bg-saffron !px-4 !py-1.5 text-sm !text-white">
                      <ThumbsUp size={15} aria-hidden="true" /> +1 हमारे यहाँ भी है
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <button type="button" disabled={busy} onClick={() => void submitReport()}>Confirm &amp; submit new report · नई शिकायत दर्ज करें</button>
        </Card>
      )}
      {camera && <CameraCapture onClose={() => setCamera(false)} onCapture={(f) => { setPhoto(f); setCamera(false); }} />}
    </div>
  );
}
