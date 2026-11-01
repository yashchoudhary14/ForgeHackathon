import { BASE, post, request } from "./client";
import { responseError } from "./errors";

export interface CivicDuplicate {
  id: number | string;
  title: string;
  distance_m?: number | null;
  upvotes?: number;
}

export interface CivicTriageOut {
  category: string;
  severity: string;
  department: string;
  draft_title: string;
  draft_hi?: string | null;
  draft_en?: string | null;
  duplicates?: CivicDuplicate[];
}

export interface CivicEvent {
  id?: number | string;
  kind?: string;
  actor?: string;
  status?: string | null;
  title?: string | null;
  note?: string | null;
  body?: string | null;
  photo_url?: string | null;
  receipt_no?: string | null;
  created_at?: string;
  meta?: Record<string, unknown> | null;
}

export interface CivicReportOut {
  id: number | string;
  profile_id?: string | null;
  category: string;
  severity?: string | null;
  department?: string | null;
  title: string;
  description?: string | null;
  draft_hi?: string | null;
  draft_en?: string | null;
  lat?: number | null;
  lng?: number | null;
  address?: string | null;
  state?: string | null;
  district?: string | null;
  photo_url?: string | null;
  audio_url?: string | null;
  status: string;
  upvotes: number;
  cpgrams_ref?: string | null;
  receipt_no?: string | null;
  run_id?: string | null;
  official_note?: string | null;
  created_at?: string;
  updated_at?: string;
  events?: CivicEvent[];
}

export interface CivicDepartmentStat {
  department: string;
  total?: number;
  open?: number;
  filed?: number;
  resolved?: number;
  resolved_pct?: number;
  avg_days?: number | null;
}

export interface CivicStatsOut {
  total: number;
  open: number;
  filed: number;
  resolved: number;
  avg_days_open?: number | null;
  by_department?: CivicDepartmentStat[];
  oldest_unresolved?: CivicReportOut[];
}

export interface CivicFilter {
  state?: string;
  district?: string;
  category?: string;
  status?: string;
  near?: string;
}

export interface CivicTriageInput {
  photo?: Blob | null;
  photoName?: string;
  audio?: Blob | null;
  audioName?: string;
  text?: string;
  lat?: number | null;
  lng?: number | null;
  lang?: string;
}

export interface CivicReportCreateInput {
  profile_id?: string | null;
  category: string;
  severity?: string;
  department?: string;
  title: string;
  description?: string;
  draft_hi?: string | null;
  draft_en?: string | null;
  lat?: number | null;
  lng?: number | null;
  address?: string;
  state?: string;
  district?: string;
  photo?: Blob | null;
  photoName?: string;
  audio?: Blob | null;
  audioName?: string;
}

export function triageForm(input: CivicTriageInput): FormData {
  const form = new FormData();
  if (input.photo) form.set("photo", input.photo, input.photoName || "issue.jpg");
  if (input.audio) form.set("audio", input.audio, input.audioName || "voice.webm");
  if (input.text?.trim()) form.set("text", input.text.trim());
  if (typeof input.lat === "number" && Number.isFinite(input.lat)) form.set("lat", String(input.lat));
  if (typeof input.lng === "number" && Number.isFinite(input.lng)) form.set("lng", String(input.lng));
  if (input.lang) form.set("lang", input.lang);
  return form;
}

export function reportsQuery(filter: CivicFilter = {}): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filter)) {
    if (typeof v === "string" && v.trim()) params.set(k, v.trim());
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function statusMeta(status: string): {
  label: string;
  tone: "ok" | "warn" | "bad" | "act" | "neutral";
} {
  const s = (status || "open").toLowerCase();
  if (s === "citizen_verified" || s === "resolved") return { label: "Citizen verified · resolved", tone: "ok" };
  if (s === "official_resolved") return { label: "Official reply · verify on site", tone: "warn" };
  if (s === "filed" || s === "in_progress") return { label: "Filed on CPGRAMS", tone: "act" };
  if (s === "still_broken" || s === "escalated") return { label: "Still broken · escalated", tone: "bad" };
  if (s === "community_verified") return { label: "Confirmed by neighbours", tone: "warn" };
  return { label: "Open", tone: "warn" };
}

export function actorBadge(event: CivicEvent): { label: string; kind: "official" | "citizen" | "agent" } {
  const raw = `${event.actor || ""} ${event.kind || ""} ${event.status || ""}`.toLowerCase();
  if (/official|cpgrams|dept|department|gov/.test(raw)) return { label: "Official · सरकारी जवाब", kind: "official" };
  if (/agent|filed/.test(raw) || event.receipt_no) return { label: "Adhikaar Agent · CPGRAMS", kind: "agent" };
  return { label: "Citizen · नागरिक", kind: "citizen" };
}

export const triageCivic = (input: CivicTriageInput, signal?: AbortSignal) =>
  request<CivicTriageOut>("/civic/triage", { method: "POST", body: triageForm(input), signal });

export async function createCivicReport(input: CivicReportCreateInput): Promise<CivicReportOut> {
  const { photo, photoName, audio, audioName, ...jsonFields } = input;
  if (photo || audio) {
    const form = new FormData();
    for (const [k, v] of Object.entries(jsonFields)) {
      if (v !== undefined && v !== null && v !== "") form.set(k, String(v));
    }
    if (photo) form.set("photo", photo, photoName || "issue.jpg");
    if (audio) form.set("audio", audio, audioName || "voice.webm");
    const res = await fetch(`${BASE}/api/civic/reports`, { method: "POST", credentials: "include", body: form });
    if (res.ok) return (await res.json()) as CivicReportOut;
    if (res.status !== 422 && res.status !== 415) throw new Error(responseError(res.status));
  }
  return post<CivicReportOut>("/civic/reports", jsonFields);
}

export async function listCivicReports(filter: CivicFilter = {}, signal?: AbortSignal): Promise<CivicReportOut[]> {
  const out = await request<CivicReportOut[] | { items?: CivicReportOut[] }>("/civic/reports" + reportsQuery(filter), { signal });
  return Array.isArray(out) ? out : Array.isArray(out?.items) ? out.items : [];
}

export const getCivicReport = (id: string | number, signal?: AbortSignal) =>
  request<CivicReportOut>(`/civic/reports/${encodeURIComponent(String(id))}`, { signal });

export const getCivicStats = (filter: { state?: string; district?: string } = {}, signal?: AbortSignal) =>
  request<CivicStatsOut>("/civic/stats" + reportsQuery(filter), { signal });

export const voteCivicReport = (id: string | number, profileId?: string) =>
  post<{ upvotes: number; status: string }>(`/civic/reports/${encodeURIComponent(String(id))}/vote`, profileId ? { profile_id: profileId } : {});

export async function submitCivicEvidence(
  id: string | number,
  input: { status: "citizen_verified" | "still_broken"; photo?: Blob | null; photoName?: string; note?: string; profile_id?: string },
): Promise<CivicReportOut> {
  const path = `/civic/reports/${encodeURIComponent(String(id))}/evidence`;
  const form = new FormData();
  form.set("status", input.status);
  if (input.profile_id) form.set("profile_id", input.profile_id);
  if (input.note?.trim()) form.set("note", input.note.trim());
  if (input.photo) form.set("photo", input.photo, input.photoName || "evidence.jpg");
  const res = await fetch(`${BASE}/api${path}`, { method: "POST", credentials: "include", body: form });
  if (res.ok) return (await res.json()) as CivicReportOut;
  if (res.status !== 422 && res.status !== 415) throw new Error(responseError(res.status));
  return post<CivicReportOut>(path, { status: input.status, profile_id: input.profile_id || null, note: input.note?.trim() || null });
}

export const fileCivicOnCpgrams = (id: string | number, profileId?: string) =>
  post<{ run_id: string }>(`/civic/reports/${encodeURIComponent(String(id))}/file`, profileId ? { profile_id: profileId } : {});

export const checkCivicStatus = (id: string | number, profileId?: string) =>
  post<{ status: string; official_note?: string | null }>(`/civic/reports/${encodeURIComponent(String(id))}/check-status`, profileId ? { profile_id: profileId } : {});
