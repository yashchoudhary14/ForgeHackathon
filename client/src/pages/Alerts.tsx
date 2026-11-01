import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listNotifications, markNotificationsRead, resolveLink } from "../api/alerts";
import type { NotificationOut } from "../api/types";
import { ErrorBox, Loading } from "../components";
import { Text, useApp } from "../context";
import { Card, EmptyState, Eyebrow, ProfileRequiredCard, SourceLink } from "../ui";
import { PillLink } from "../nav";
import { tt } from "../ui-strings";

/** A notification link: in-app route, or the official source in a new tab. */
export function OpenLink({ link, lang }: { link: string | null; lang: string }) {
  const { to, href } = resolveLink(link);
  const cls = "inline-flex min-h-11 items-center font-semibold";
  if (to) return <Link to={to} className={cls}>{tt(lang, "open")} →</Link>;
  if (href)
    return (
      <SourceLink url={href} />
    );
  return null;
}

/** Alerts from GET /api/notifications. Works as a page and as a panel. */
export function AlertsPanel({
  compact = false,
  onUnread,
}: {
  compact?: boolean;
  onUnread?: (count: number) => void;
}) {
  const { profileId, lang } = useApp();
  const [items, setItems] = useState<NotificationOut[] | null>(null);
  const [unread, setUnread] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function load(signal?: AbortSignal) {
    if (!profileId) return setItems([]);
    try {
      setError("");
      const out = await listNotifications(profileId, signal);
      setItems(out.items ?? []);
      setUnread(out.unread_count ?? 0);
      onUnread?.(out.unread_count ?? 0);
    } catch (e) {
      if (!signal?.aborted) setError((e as Error).message);
    }
  }
  useEffect(() => {
    const c = new AbortController();
    void load(c.signal);
    return () => c.abort();
  }, [profileId]);
  async function markRead() {
    setBusy(true);
    try {
      const out = await markNotificationsRead(profileId);
      setItems((list) => list?.map((n) => ({ ...n, read: true })) ?? list);
      setUnread(out.unread_count);
      onUnread?.(out.unread_count);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (error) return <ErrorBox error={error} retry={() => void load()} />;
  if (!items) return <Loading />;
  const shown = compact ? items.slice(0, 4) : items;
  return (
    <div className="flex flex-col gap-3">
      {shown.length === 0 ? (
        <EmptyState
          title={tt(lang, profileId ? "alertsEmpty" : "alertsProfileTitle")}
          action={
            !profileId && (
              <PillLink to="/talk">{tt(lang, "chooseTalk")} →</PillLink>
            )
          }
        >
          {!profileId && tt(lang, "needProfile")}
        </EmptyState>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {shown.map((n) => (
            <li
              key={n.id}
              className={
                "flex flex-col gap-1 rounded-[22px] p-4 " +
                (n.read ? "bg-white shadow-[inset_0_0_0_1px_#ede5da]" : "bg-peach")
              }
            >
              <div className="flex items-start justify-between gap-2">
                <strong className="min-w-0 break-words"><Text value={n.title} /></strong>
                {!n.read && (
                  <span className="shrink-0 rounded-full bg-saffron-text px-2 py-0.5 text-xs font-semibold text-white">
                    {tt(lang, "new")}
                  </span>
                )}
              </div>
              {n.body && <p className="m-0 break-words text-[15px]">{n.body}</p>}
              <div className="flex flex-wrap items-center justify-between gap-x-3 text-sm text-ink-soft">
                <time dateTime={n.created_at}>{new Date(n.created_at).toLocaleString(lang)}</time>
                <OpenLink link={n.link} lang={lang} />
              </div>
            </li>
          ))}
        </ul>
      )}
      {!compact && unread > 0 && (
        <button
          type="button"
          className="secondary self-start"
          disabled={busy}
          onClick={() => void markRead()}
        >
          {tt(lang, "markAllRead")}
        </button>
      )}
    </div>
  );
}

export default function Alerts() {
  const { lang, profileId } = useApp();
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <Eyebrow>{tt(lang, "navAlerts")}</Eyebrow>
      <h1>{tt(lang, "alertsTitle")}</h1>
      {!profileId ? (
        <ProfileRequiredCard context="alerts" nextPath="/alerts" />
      ) : (
        <Card>
          <AlertsPanel />
        </Card>
      )}
    </div>
  );
}
