import { useTranslation, Text, useApp } from "../context";
import { translate } from "../i18n";
import { useEffect, useState } from "react";
import { Camera, FileCheck2, Landmark, ShieldCheck, Upload } from "lucide-react";
import { request } from "../api/client";
import { deleteLockerItem, uploadForm } from "../api/locker";
import type { LockerItem } from "../api/locker";
import { saveMode } from "../api/profile";
import { ErrorBox, Loading } from "../components";
import {
  Card,
  EmptyState,
  Eyebrow,
  PillButton,
  ProfileRequiredCard,
  StatTile,
} from "../ui";
import { tt } from "../ui-strings";
import CameraCapture from "./CameraCapture";
import LockerItemCard, { label } from "./LockerItemCard";

const docOptions = [
  ["", "Auto-detect with AI"],
  ["income_certificate", "Income certificate"],
  ["aadhaar", "Aadhaar card"],
  ["caste_certificate", "Caste certificate"],
  ["land_record", "Land record / Khatauni"],
  ["bank_passbook", "Bank passbook"],
  ["marksheet", "Marksheet"],
  ["domicile", "Domicile certificate"],
  ["photo", "Passport photo"],
  ["other", "Other document"],
];

export default function Locker() {
  const tr = useTranslation();
  const { profileId, setProfileId, mode, setMode, lang } = useApp();
  const [items, setItems] = useState<LockerItem[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [camera, setCamera] = useState(false);
  const [docType, setDocType] = useState("");
  const [last, setLast] = useState<LockerItem | null>(null);

  async function startLockerNow() {
    setBusy(true);
    setError("");
    try {
      const nextMode = mode || "manual";
      const pid = await saveMode("", nextMode, lang);
      if (!mode) setMode(nextMode);
      setProfileId(pid);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function load(signal?: AbortSignal) {
    if (!profileId) return setItems([]);
    try {
      setError("");
      const out = await request<LockerItem[]>(
        "/locker?" + new URLSearchParams({ profile_id: profileId }),
        { signal },
      );
      setItems(Array.isArray(out) ? out : []);
    } catch (e) {
      if (!signal?.aborted) setError((e as Error).message);
    }
  }

  useEffect(() => {
    const c = new AbortController();
    void load(c.signal);
    return () => c.abort();
  }, [profileId]);

  async function upload(file: Blob, name: string) {
    setBusy(true);
    setError("");
    setCamera(false);
    try {
      setLast(
        await request<LockerItem>("/locker", {
          method: "POST",
          body: uploadForm(profileId, file, name, docType || undefined),
        }),
      );
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    try {
      await deleteLockerItem(id, profileId);
      setItems((l) => l?.filter((x) => x.id !== id) ?? l);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const canCamera = typeof navigator !== "undefined" && !!navigator.mediaDevices;
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-5">
      <div className="flex flex-col gap-2">
        <Eyebrow> <Text value="Locker · Secure, just for you" /> </Eyebrow>
        <h1> <Text value="Your documents" /> </h1>
        <p className="m-0 text-ink-soft">
           <Text value="Scan a paper with your camera. Buddy names it, checks it is readable and makes a small copy that fits government portals." /> </p>
      </div>
      {!profileId ? (
        <div className="flex flex-col gap-5">
          {error && <ErrorBox error={error} retry={() => void startLockerNow()} />}
          <ProfileRequiredCard
            context="locker"
            nextPath="/locker"
            primaryAction={
              <PillButton
                tone="dark"
                disabled={busy}
                onClick={() => void startLockerNow()}
              >
                {tt(lang, "startLockerNow")} →
              </PillButton>
            }
          />
          <div className="flex flex-col gap-3">
            <Eyebrow> <Text value="WHAT YOU CAN STORE IN YOUR LOCKER" /> </Eyebrow>
            <div className="grid gap-3 sm:grid-cols-2">
              {[
                {
                  title: "Aadhaar Card",
                  sub: "Store an identity document for applications.",
                  Icon: ShieldCheck,
                },
                {
                  title: "Income Certificate",
                  sub: "Keep proof of income available for welfare applications.",
                  Icon: FileCheck2,
                },
                {
                  title: "Caste Certificate",
                  sub: "Store a certificate that a scholarship or welfare scheme may request.",
                  Icon: FileCheck2,
                },
                {
                  title: "Bank Passbook / Land Record",
                  sub: "Keep bank or land documents together for applications.",
                  Icon: Landmark,
                },
              ].map(({ title, sub, Icon }) => (
                <Card key={title} className="flex items-start gap-3.5 !rounded-tile border border-line !bg-card !p-4 !shadow-none">
                  <span
                    aria-hidden="true"
                    className="grid h-11 w-11 shrink-0 place-items-center rounded-lg border border-saffron bg-peach text-saffron-text"
                  >
                    <Icon size={20} />
                  </span>
                  <div className="flex flex-col gap-0.5">
                    <strong className="font-serif text-lg font-bold text-ink">
                      <Text value={title} />
                    </strong>
                    <p className="m-0 text-xs text-ink-soft"><Text value={sub} /></p>
                  </div>
                </Card>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <>
          <Card className="flex flex-col gap-4 overflow-hidden !rounded-card !bg-ink !text-paper !shadow-none">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="m-0 font-serif font-bold text-paper"> <Text value="Scan into locker" /> </h2>
              <label className="m-0 flex max-w-full flex-wrap items-center gap-2 text-xs font-semibold text-paper/80">
                <span> <Text value="Document type" /> </span>
                <select
                  value={docType}
                  disabled={busy}
                  onChange={(e) => setDocType(e.target.value)}
                  className="!m-0 !min-h-11 !w-auto min-w-0 max-w-full !rounded-full !border-white/20 !bg-white/10 !px-3 !py-1.5 !text-sm !text-paper"
                >
                  {docOptions.map(([v, txt]) => (
                    <option key={v} value={v} className="text-ink">
                      <Text value={txt} />
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="relative mx-auto flex min-h-44 w-full max-w-md flex-col items-center justify-center gap-3 rounded-tile border border-dashed border-white/30 bg-white/5 p-6 text-center">
              <span aria-hidden="true" className="pointer-events-none absolute left-3 top-3 h-7 w-7 rounded-tl-xl border-l-4 border-t-4 border-lime" />
              <span aria-hidden="true" className="pointer-events-none absolute right-3 top-3 h-7 w-7 rounded-tr-xl border-r-4 border-t-4 border-lime" />
              <span aria-hidden="true" className="pointer-events-none absolute bottom-3 left-3 h-7 w-7 rounded-bl-xl border-b-4 border-l-4 border-lime" />
              <span aria-hidden="true" className="pointer-events-none absolute bottom-3 right-3 h-7 w-7 rounded-br-xl border-b-4 border-r-4 border-lime" />
              <p className="m-0 text-sm text-paper/90">
                 <Text value="Place your document inside the frame so all four corners are visible. Automatically resized to JPG (<200 KB) & PDF (<300 KB)." /> </p>
              <div className="flex flex-wrap justify-center gap-2.5">
                {canCamera && (
                  <button type="button" disabled={busy} onClick={() => setCamera(true)} className="!bg-lime !text-ink">
                    <Camera size={18} aria-hidden="true" />  <Text value="Open camera" /> </button>
                )}
                <label className="inline-flex min-h-12 cursor-pointer items-center gap-2 rounded-full bg-white px-6 font-semibold text-ink">
                  <Upload size={18} aria-hidden="true" />
                   <Text value="Take or choose a photo" /> <input
                    type="file"
                    accept="image/*,application/pdf"
                    capture="environment"
                    className="sr-only"
                    disabled={busy}
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) void upload(f, f.name);
                      e.target.value = "";
                    }}
                  />
                </label>
              </div>
            </div>
            {busy && <Loading message={tr("Reading your document…")} />}
            {last && !busy && (
              <p
                role="status"
                className={
                  "m-0 self-center rounded-full px-4 py-2 text-sm font-semibold " +
                  (last.meta?.readable === false ? "bg-warn-soft text-warn" : "bg-lime text-ink")
                }
              >
                {last.title || tr(label(last.doc_type))}
                {last.meta?.readable === false ? tr(" · hard to read, try again") : tr(" · readable & ready")}
              </p>
            )}
          </Card>
          {error && <ErrorBox error={error} retry={() => void load()} />}
          {!items ? (
            !error && <Loading />
          ) : items.length === 0 ? (
            <EmptyState title={tr("Nothing here yet")}> <Text value="Your scanned documents will be listed here." /> </EmptyState>
          ) : (
            <>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="m-0 font-serif text-3xl font-bold"> <Text value="My locker" /> </h2>
                <span className="text-sm text-ink-soft"> <Text value="Secure, just for you" /> </span>
              </div>
              <div className="[&>div]:!flex-row [&>div]:!items-baseline [&>div]:!gap-3 [&>div]:!rounded-tile [&>div]:!px-4 [&>div]:!py-3 [&>div>span:first-child]:!text-4xl"><StatTile accent value={items.length} label={translate("documents in your locker", lang)} /></div>
              <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
                {items.map((d, i) => (
                  <li key={d.id}>
                    <LockerItemCard item={d} index={i} isNew={last?.id === d.id} profileId={profileId} onDelete={() => void remove(d.id)} />
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
      {camera && <CameraCapture onClose={() => setCamera(false)} onCapture={(f) => void upload(f, f.name)} />}
    </div>
  );
}
