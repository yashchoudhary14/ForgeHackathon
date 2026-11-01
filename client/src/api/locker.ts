import { BASE } from "./client";
import { responseError } from "./errors";

export interface LockerItem {
  id: string | number;
  doc_type: string;
  title: string;
  // Sizes in bytes per variant, e.g. {jpg: 180000, pdf: 210000}. An array of
  // {name|variant, size} is also accepted so a small server change does not break the list.
  variants?: Record<string, number> | { variant?: string; name?: string; size?: number }[] | null;
  meta?: { readable?: boolean; issues?: string[] } | null;
  created_at?: string;
}

export function variantSizes(item: LockerItem): [string, number | null][] {
  const v = item.variants;
  if (!v) return [];
  if (Array.isArray(v))
    return v.map((x) => [
      String(x.variant ?? x.name ?? "file").toUpperCase(),
      typeof x.size === "number" ? x.size : null,
    ]);
  return Object.entries(v).map(([k, size]) => [
    k.toUpperCase(),
    typeof size === "number" ? size : null,
  ]);
}

export const formatKb = (bytes: number | null) =>
  bytes == null ? "" : `${Math.max(1, Math.round(bytes / 1024))} KB`;

export const lockerFileUrl = (id: string | number, variant: string) =>
  `${BASE}/api/locker/${encodeURIComponent(String(id))}/file?variant=${encodeURIComponent(variant)}`;

export function variantSummary(item: LockerItem): string {
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

export async function deleteLockerItem(id: string | number) {
  const res = await fetch(`${BASE}/api/locker/${encodeURIComponent(String(id))}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok) throw new Error(responseError(res.status));
}
