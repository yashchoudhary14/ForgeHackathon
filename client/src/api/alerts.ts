import { post, request } from "./client";
import type { ActivityItem, NotificationsOut, NotificationsReadOut } from "./types";

const q = (profileId: string) => "?" + new URLSearchParams({ profile_id: profileId });

/** GET /notifications?profile_id= -> {items, unread_count} */
export const listNotifications = (profileId: string, signal?: AbortSignal) =>
  request<NotificationsOut>("/notifications" + q(profileId), { signal });

/** POST /notifications/read. Omit ids to mark everything read. */
export const markNotificationsRead = (profileId: string, ids?: number[]) =>
  post<NotificationsReadOut>("/notifications/read", ids ? { profile_id: profileId, ids } : { profile_id: profileId });

/** GET /activity?profile_id= -> runs, reports and notifications, newest first. */
export const getActivity = (profileId: string, signal?: AbortSignal) =>
  request<ActivityItem[]>("/activity" + q(profileId), { signal });

/**
 * Server links point at server-side paths (/runs/{id}, /reports/{id}, /schemes/{slug})
 * or at an official page (PIB). Returns an in-app route or an external URL.
 */
export function resolveLink(link: string | null | undefined): { to?: string; href?: string } {
  if (!link) return {};
  if (/^https?:\/\//i.test(link)) return { href: link };
  if (!link.startsWith("/")) return {};
  const report = link.match(/^\/reports\/([^/?#]+)/);
  if (report) return { to: "/civic/" + report[1] };
  return { to: link };
}
