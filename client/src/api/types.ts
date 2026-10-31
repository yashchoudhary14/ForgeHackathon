export type Lang =
  "en" | "hi" | "bn" | "ta" | "te" | "mr" | "gu" | "kn" | "ml" | "pa" | "od";
export interface ProfileData {
  age?: number | null;
  gender?: "male" | "female" | "transgender" | null;
  state?: string | null;
  district?: string | null;
  residence?: "urban" | "rural" | null;
  caste?: "general" | "obc" | "sc" | "st" | "pvtg" | "dnt" | null;
  annual_income?: number | null;
  occupation?: string | null;
  is_student?: boolean | null;
  education_level?: string | null;
  disability_percent?: number | null;
  marital_status?: string | null;
  is_bpl?: boolean | null;
  land_acres?: number | null;
  is_minority?: boolean | null;
}
export interface SensitiveData {
  full_name?: string | null;
  phone?: string | null;
  email?: string | null;
  dob?: string | null;
  address?: string | null;
  father_name?: string | null;
  bank_ifsc?: string | null;
}
export interface ProfileIn {
  data: ProfileData;
  sensitive: SensitiveData;
  language: Lang;
}
export interface ProfileOut extends ProfileIn {
  id: string;
}
export interface ProfileExtractIn {
  text: string;
  language: Lang;
  profile_id?: string | null;
}
export interface ProfileExtractOut {
  profile: ProfileOut;
  missing_fields: string[];
  follow_up_question?: string | null;
}
export interface Citation {
  source_url: string;
  title?: string | null;
  quote: string;
  section?: string | null;
}
export interface ApplicationMode {
  mode: string;
  steps_md: string;
  url?: string | null;
}
export interface SchemeSummary {
  slug: string;
  name: string;
  ministry?: string | null;
  state?: string | null;
  tags: string[];
  brief?: string | null;
}
export interface SchemeDetail extends SchemeSummary {
  id: string;
  details_md: string;
  benefits_md: string;
  eligibility_md: string;
  exclusions_md: string;
  application: ApplicationMode[];
  documents_md: string;
  faqs: Record<string, unknown>[];
  references: Record<string, unknown>[];
  source_url: string;
}
export interface SearchOut {
  total: number;
  items: SchemeSummary[];
}
export interface MatchIn {
  profile_id: string;
  keyword?: string | null;
  limit?: number;
}
export interface Reason {
  claim: string;
  met: boolean | null;
  citation?: Citation | null;
}
export interface MatchResult {
  scheme: SchemeSummary;
  verdict: "eligible" | "likely" | "not_eligible" | "unknown";
  confidence: number;
  reasons: Reason[];
  missing_info: string[];
  documents_needed: string[];
}
export type MatchEvent =
  | { type: "progress"; message: string; checked: number; total: number }
  | { type: "result"; result: MatchResult }
  | { type: "done"; results: MatchResult[] }
  | { type: "error"; message: string };
export interface ExplainSource {
  type: "scheme" | "document" | "url";
  slug?: string | null;
  document_id?: string | null;
  url?: string | null;
}
export interface ExplainIn {
  source: ExplainSource;
  profile_id?: string | null;
  language: Lang;
  with_audio?: boolean;
}
export interface ExplainOut {
  title: string;
  summary: string;
  key_points: string[];
  your_rights: string[];
  what_it_means_for_you?: string | null;
  deadlines: string[];
  documents_needed: string[];
  citations: Citation[];
  language: Lang;
  audio_url?: string | null;
}
export interface DocumentOut {
  id: string;
  title: string;
  source_type: string;
  source_url?: string | null;
  pages: number;
  chunks: number;
}
export interface FeedItem {
  title: string;
  url: string;
  published?: string | null;
  ministry?: string | null;
  source: string;
}
export interface ChatIn {
  session_id: string;
  message: string;
  language: Lang;
  profile_id?: string | null;
  document_ids?: string[];
}
export type ChatEvent =
  | { type: "token"; text: string }
  | { type: "tool_call"; name: string; args: Record<string, unknown> }
  | { type: "tool_result"; name: string; summary: string }
  | { type: "citation"; citation: Citation }
  | { type: "done"; message_id: number }
  | { type: "error"; message: string };
export interface SttOut {
  text: string;
  language: Lang;
}
export interface TtsIn {
  text: string;
  language?: Lang;
}
export interface RunIn {
  profile_id: string;
  portal_url: string;
  goal: string;
  scheme_slug?: string | null;
}
export interface RunStepOut {
  idx: number;
  thought: string | null;
  action: Record<string, unknown> | null;
  status: string;
  result?: string | null;
  url: string | null;
  screenshot: string | null;
}
export interface Receipt {
  reference_no?: string;
  screenshot?: string;
  url?: string;
  summary?: string;
  [key: string]: unknown;
}
export type RunStatus =
  | "queued"
  | "running"
  | "needs_human"
  | "awaiting_approval"
  | "done"
  | "failed"
  | "aborted";
export interface RunOut {
  id: string;
  profile_id: string | null;
  scheme_slug: string | null;
  portal_url: string;
  goal: string;
  status: RunStatus;
  receipt: Receipt | null;
  error: string | null;
  steps: RunStepOut[];
}
export type HumanKind =
  "captcha" | "otp" | "missing_field" | "confirm_submit" | "login";
export type ServerMessage =
  | { type: "frame"; jpeg: string }
  | { type: "step"; step: RunStepOut }
  | { type: "status"; status: RunStatus }
  | { type: "needs_human"; kind: HumanKind; message: string; field?: string }
  | { type: "done"; receipt: Receipt }
  | { type: "error"; message: string };
export type ClientMessage =
  | { type: "human_input"; value: string }
  | { type: "click"; x: number; y: number }
  | { type: "type"; text: string }
  | { type: "key"; key: string }
  | { type: "resume" | "approve" | "abort" };
