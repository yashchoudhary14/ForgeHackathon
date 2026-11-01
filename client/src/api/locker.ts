import { BASE, withOwner } from "./client";
import { responseError } from "./errors";

/** Server DocType (services/locker.py). */
export const docTypes = [
  "aadhaar",
  "income_certificate",
  "caste_certificate",
  "domicile",
  "marksheet",
  "photo",
  "land_record",
  "bank_passbook",
  "other",
] as const;

/** LockerOut: variants are portal-ready copies, e.g. [{format: "jpg", bytes: 180000}]. */
export interface LockerItem {
  id: string;
  doc_type: string;
  title: string;
  variants: { format: string; bytes: number }[];
  meta: {
    readable?: boolean;
    issues?: string[];
    detected_doc_type?: string;
  } & Record<string, unknown>;
  created_at: string;
}

export function variantSizes(item: Pick<LockerItem, "variants">): [string, number | null][] {
  return (item.variants ?? []).map((v) => [
    String(v.format || "file").toUpperCase(),
    typeof v.bytes === "number" ? v.bytes : null,
  ]);
}

export const formatKb = (bytes: number | null) =>
  bytes == null ? "" : `${Math.max(1, Math.round(bytes / 1024))} KB`;

export const lockerFileUrl = (id: string, variant: string, profileId: string) =>
  BASE +
  "/api" +
  withOwner(
    `/locker/${encodeURIComponent(id)}/file?variant=${encodeURIComponent(variant)}`,
    profileId,
  );

export function variantSummary(item: Pick<LockerItem, "variants">): string {
  const parts = variantSizes(item).map(([name, size]) => {
    const kb = formatKb(size);
    return kb ? `${name} ${kb}` : name;
  });
  return parts.join(" · ");
}

export function uploadForm(
  profileId: string,
  file: Blob,
  name: string,
  docType?: string,
) {
  const form = new FormData();
  form.set("profile_id", profileId);
  form.set("file", file, name);
  if (docType?.trim()) form.set("doc_type", docType.trim());
  return form;
}

export async function deleteLockerItem(id: string, profileId: string) {
  const res = await fetch(
    BASE + "/api" + withOwner(`/locker/${encodeURIComponent(id)}`, profileId),
    { method: "DELETE", credentials: "include" },
  );
  if (!res.ok) throw new Error(responseError(res.status));
}
