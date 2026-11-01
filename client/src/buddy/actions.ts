import type { Lang, ProfileData } from "../api/types";

export type BuddyAction =
  | { type: "navigate"; route: string }
  | { type: "open_scheme"; slug: string }
  | { type: "start_application"; slug: string; run_id: string }
  | { type: "open_camera"; doc_type: string; reason: string }
  | { type: "open_report" | "show_profile" }
  | { type: "set_language"; lang: Lang }
  | {
      type: "fill_profile_field";
      field: keyof ProfileData;
      value: string | number | boolean;
    };

export const routes = new Set([
  "/",
  "/schemes",
  "/locker",
  "/civic",
  "/civic/new",
  "/runs",
  "/alerts",
  "/explain",
  "/profile",
  "/talk",
  "/ask",
]);
export const profileFields = [
  "state",
  "age",
  "gender",
  "occupation",
  "is_student",
  "annual_income",
  "caste",
  "residence",
] as const;
const safeFields = new Set<string>([
  ...profileFields,
  "district",
  "education_level",
  "disability_percent",
  "land_acres",
  "is_bpl",
  "is_minority",
  "marital_status",
]);
const languages = new Set([
  "en",
  "hi",
  "bn",
  "as",
  "ta",
  "te",
  "mr",
  "gu",
  "kn",
  "ml",
  "pa",
  "od",
]);
const docTypes = new Set([
  "aadhaar",
  "income_certificate",
  "caste_certificate",
  "domicile",
  "marksheet",
  "photo",
  "land_record",
  "bank_passbook",
  "other",
]);

export interface ActionHost {
  navigate: (route: string) => void;
  activateRun: (id: string) => void;
  openCamera: (docType: string, reason: string) => void;
  setLanguage: (lang: Lang) => void | Promise<void>;
  profileChanged: (
    field: keyof ProfileData,
    value: string | number | boolean,
  ) => void;
}

/** SSE is an untrusted boundary. Never follow arbitrary URLs or create a run here. */
export async function dispatchAction(
  input: unknown,
  host: ActionHost,
): Promise<boolean> {
  if (!input || typeof input !== "object") return false;
  const a = input as Record<string, unknown>;
  const identifier = (v: unknown): v is string =>
    typeof v === "string" && /^[\w-]{1,200}$/.test(v);
  switch (a.type) {
    case "navigate":
      if (typeof a.route !== "string" || !routes.has(a.route)) return false;
      host.navigate(a.route);
      return true;
    case "open_scheme":
      if (!identifier(a.slug)) return false;
      host.navigate("/schemes/" + encodeURIComponent(a.slug));
      return true;
    case "start_application":
      if (!identifier(a.slug) || !identifier(a.run_id)) return false;
      host.activateRun(a.run_id);
      host.navigate("/runs/" + encodeURIComponent(a.run_id));
      return true;
    case "open_camera":
      if (
        typeof a.doc_type !== "string" ||
        !docTypes.has(a.doc_type) ||
        typeof a.reason !== "string"
      )
        return false;
      host.openCamera(a.doc_type, a.reason.slice(0, 300));
      return true;
    case "open_report":
      host.navigate("/civic/new");
      return true;
    case "show_profile":
      host.navigate("/profile");
      return true;
    case "set_language":
      if (typeof a.lang !== "string" || !languages.has(a.lang)) return false;
      await host.setLanguage(a.lang as Lang);
      return true;
    case "fill_profile_field":
      if (
        typeof a.field !== "string" ||
        !safeFields.has(a.field) ||
        !["string", "number", "boolean"].includes(typeof a.value)
      )
        return false;
      // Acknowledgement of a server-saved fact, not a second write of model output.
      host.profileChanged(
        a.field as keyof ProfileData,
        a.value as string | number | boolean,
      );
      return true;
    default:
      return false;
  }
}

export function profileComplete(data: ProfileData) {
  return profileFields.every(
    (field) =>
      data[field] !== null && data[field] !== undefined && data[field] !== "",
  );
}

export function normaliseAnswer(
  text: string,
  kind: string,
  spoken = false,
): string {
  const digits = text.replace(/[०-९০-৯]/g, (c) =>
    String(c.charCodeAt(0) - (c >= "০" ? 0x09e6 : 0x0966)),
  );
  const words: Record<string, string> = {
    zero: "0",
    one: "1",
    two: "2",
    three: "3",
    four: "4",
    five: "5",
    six: "6",
    seven: "7",
    eight: "8",
    nine: "9",
    शून्य: "0",
    एक: "1",
    दो: "2",
    तीन: "3",
    चार: "4",
    पाँच: "5",
    पांच: "5",
    छह: "6",
    सात: "7",
    आठ: "8",
    नौ: "9",
    শূন্য: "0",
    এক: "1",
    দুই: "2",
    তিন: "3",
    চার: "4",
    পাঁচ: "5",
    ছয়: "6",
    সাত: "7",
    আট: "8",
    নয়: "9",
  };
  if (kind === "otp")
    return digits
      .toLowerCase()
      .split(/[\s,।.!?-]+/)
      .filter(Boolean)
      .map((word) => words[word] ?? word)
      .join("");
  if (kind !== "captcha" || !spoken) return text.trim();
  const letters: Record<string, string> = {
    ए: "A",
    बी: "B",
    सी: "C",
    डी: "D",
    ई: "E",
    एफ: "F",
    जी: "G",
    एच: "H",
    आई: "I",
    जे: "J",
    के: "K",
    एल: "L",
    एम: "M",
    एन: "N",
    ओ: "O",
    पी: "P",
    क्यू: "Q",
    आर: "R",
    एस: "S",
    टी: "T",
    यू: "U",
    वी: "V",
    डब्ल्यू: "W",
    एक्स: "X",
    वाई: "Y",
    जेड: "Z",
    এ: "A",
    বি: "B",
    সি: "C",
    ডি: "D",
    ই: "E",
    এফ: "F",
    জি: "G",
    এইচ: "H",
    আই: "I",
    জে: "J",
    কে: "K",
    এল: "L",
    এম: "M",
    এন: "N",
    ও: "O",
    পি: "P",
    কিউ: "Q",
    আর: "R",
    এস: "S",
    টি: "T",
    ইউ: "U",
    ভি: "V",
    ডব্লিউ: "W",
    এক্স: "X",
    ওয়াই: "Y",
    জেড: "Z",
  };
  let casing: "upper" | "lower" | null = null;
  const result: string[] = [];
  for (const token of digits.split(/[\s,।.!?-]+/).filter(Boolean)) {
    if (/^(capital|uppercase|बड़ा|बड़े|বড়)$/i.test(token)) {
      casing = "upper";
      continue;
    }
    if (/^(small|lowercase|छोटा|छोटे|ছোট)$/i.test(token)) {
      casing = "lower";
      continue;
    }
    const character = words[token.toLowerCase()] ?? letters[token] ?? token;
    if (!/^[A-Za-z0-9]$/.test(character)) return text.trim();
    result.push(
      casing === "upper"
        ? character.toUpperCase()
        : casing === "lower"
          ? character.toLowerCase()
          : character,
    );
    casing = null;
  }
  return result.join("");
}

export function confirmationIntent(text: string): "yes" | "no" | null {
  const value = text
    .trim()
    .toLowerCase()
    .replace(/[.!?।]+$/g, "");
  if (/^(yes|correct|ok|okay|हाँ|हां|सही|जी|হ্যাঁ|হাঁ|ঠিক|হয়)$/.test(value))
    return "yes";
  if (/^(no|wrong|नहीं|नही|गलत|না|ভুল|নহয়)$/.test(value)) return "no";
  return null;
}
