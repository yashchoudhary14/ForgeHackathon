import { post, request } from "./client";

// Shapes follow server/app/schemas.py (civic section) and routers/reports.py.
export type ReportCategory =
  | "water"
  | "roads"
  | "electricity"
  | "sanitation"
  | "streetlight"
  | "drainage"
  | "safety"
  | "other";
export type ReportStatus = "open" | "filed" | "in_progress" | "resolved" | "closed";
export type Severity = "low" | "medium" | "high" | "urgent";

export const categories: ReportCategory[] = [
  "water",
  "roads",
  "electricity",
  "sanitation",
  "streetlight",
  "drainage",
  "safety",
  "other",
];
export const statuses: ReportStatus[] = ["open", "filed", "in_progress", "resolved", "closed"];

/** The AI triage the citizen can accept before saving (CivicTriage). */
export interface CivicTriage {
  category: ReportCategory;
  title: string;
  title_local: string;
  description: string;
  severity: Severity;
  severity_reason: string;
  department: string;
  since_when?: string;
  people_affected?: string;
}

export interface ReportMedia {
  type: "photo" | "audio";
  url: string;
  mime?: string;
  bytes?: number;
}

/** ReportEventOut: source is official | citizen | system. */
export interface ReportEvent {
  id: number;
  source: string;
  kind: string;
  text: string;
  meta?: Record<string, unknown>;
  created_at: string;
}

export interface ComplaintDraft {
  subject: string;
  english: string;
  local: string;
  language: string;
}

export interface ReportOut extends CivicTriage {
  id: string;
  profile_id: string | null;
  language: string;
  lat: number;
  lng: number;
  address: string | null;
  media: ReportMedia[];
  status: string;
  official_ref: string | null;
  official_status: string | null;
  supporters: number;
  created_at: string;
  updated_at: string;
  events: ReportEvent[];
  distance_m?: number | null;
  similarity?: number | null;
  duplicate_score?: number | null;
  source_url?: string | null;
  complaint_draft?: ComplaintDraft | null;
}

export interface TriageOut extends CivicTriage {
  language: string;
  address: string | null;
  geocoding_attribution?: string;
  duplicates: ReportOut[];
}

/** GET /reports/stats: counts from real rows only. */
export interface ReportStats {
  total: number;
  by_status: Record<string, number>;
  by_department: Record<string, number>;
  by_category: Record<string, number>;
  confirmed_by_others: number;
  official_number: number;
  resolved_confirmed: number;
  open_by_department: Record<string, number>;
}

export interface ReportFilter {
  category?: string;
  status?: string;
  profile_id?: string;
  lat?: number;
  lng?: number;
  radius_km?: number;
  limit?: number;
}

export interface SubmissionInput {
  profile_id: string;
  lat: number;
  lng: number;
  text?: string;
  photo?: Blob | null;
  photoName?: string;
  audio?: Blob | null;
  audioName?: string;
}

export type VoteKind = "support" | "still_broken" | "fixed" | "follow";

const id = (v: string) => encodeURIComponent(v);

/** Multipart body for POST /reports/triage and POST /reports. `accepted` is the triage the citizen confirmed. */
export function submissionForm(input: SubmissionInput, accepted?: CivicTriage | null): FormData {
  const form = new FormData();
  form.set("profile_id", input.profile_id);
  form.set("lat", String(input.lat));
  form.set("lng", String(input.lng));
  if (input.text?.trim()) form.set("text", input.text.trim());
  if (input.photo) form.set("photo", input.photo, input.photoName || "issue.jpg");
  if (input.audio) form.set("audio", input.audio, input.audioName || "voice.webm");
  if (accepted) form.set("triage", JSON.stringify(accepted));
  return form;
}

export function reportsQuery(filter: ReportFilter = {}): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filter)) {
    if (typeof v === "number" && Number.isFinite(v)) params.set(k, String(v));
    else if (typeof v === "string" && v.trim()) params.set(k, v.trim());
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function statusMeta(status: string): {
  label: string;
  tone: "ok" | "warn" | "bad" | "act" | "neutral";
} {
  switch ((status || "open").toLowerCase()) {
    case "resolved":
      return { label: "Resolved", tone: "ok" };
    case "closed":
      return { label: "Closed", tone: "neutral" };
    case "filed":
      return { label: "Filed on CPGRAMS", tone: "act" };
    case "in_progress":
      return { label: "In progress", tone: "act" };
    default:
      return { label: "Open", tone: "warn" };
  }
}

/** Timeline label: official replies are kept visually apart from citizen and system notes. */
export function sourceBadge(event: Pick<ReportEvent, "source">): {
  label: string;
  kind: "official" | "citizen" | "system";
} {
  if (event.source === "official") return { label: "Official", kind: "official" };
  if (event.source === "system") return { label: "Buddy", kind: "system" };
  return { label: "Citizen", kind: "citizen" };
}

export const firstPhoto = (r: Pick<ReportOut, "media">) =>
  r.media?.find((m) => m.type === "photo")?.url;

export const triageReport = (input: SubmissionInput, signal?: AbortSignal) =>
  request<TriageOut>("/reports/triage", { method: "POST", body: submissionForm(input), signal });

export const createReport = (input: SubmissionInput, accepted: CivicTriage) =>
  request<ReportOut>("/reports", { method: "POST", body: submissionForm(input, accepted) });

export const listReports = (filter: ReportFilter = {}, signal?: AbortSignal) =>
  request<ReportOut[]>("/reports" + reportsQuery(filter), { signal });

export const getReport = (reportId: string, signal?: AbortSignal) =>
  request<ReportOut>(`/reports/${id(reportId)}`, { signal });

export const getReportStats = (signal?: AbortSignal) =>
  request<ReportStats>("/reports/stats", { signal });

export const voteReport = (reportId: string, profileId: string, kind: VoteKind) =>
  post<ReportOut>(`/reports/${id(reportId)}/vote`, { profile_id: profileId, kind });

export function addEvidence(
  reportId: string,
  input: { profile_id: string; text?: string; photo?: Blob | null; photoName?: string },
) {
  const form = new FormData();
  form.set("profile_id", input.profile_id);
  if (input.text?.trim()) form.set("text", input.text.trim());
  if (input.photo) form.set("photo", input.photo, input.photoName || "evidence.jpg");
  return request<ReportOut>(`/reports/${id(reportId)}/evidence`, { method: "POST", body: form });
}

export const fileReport = (reportId: string, profileId: string) =>
  post<{ run_id: string; draft?: ComplaintDraft | null }>(`/reports/${id(reportId)}/file`, {
    profile_id: profileId,
  });

export const checkReportStatus = (reportId: string, profileId: string) =>
  post<{ run_id: string }>(`/reports/${id(reportId)}/check-status`, { profile_id: profileId });
