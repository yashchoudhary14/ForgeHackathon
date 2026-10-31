import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { post, request } from "../api/client";
import type { NotificationOut } from "../api/types";
import { ErrorBox, Loading } from "../components";
import { useApp } from "../context";
import { Card, EmptyState, Eyebrow } from "../ui";
import { tt } from "../ui-strings";

/** Alerts from GET /api/notifications. Works as a page and as a panel. */
export function AlertsPanel({ compact = false }: { compact?: boolean }) {
  const { profileId, lang } = useApp();
  const [items, setItems] = useState<NotificationOut[] | null>(null);
  const [error, setError] = useState("");
  async function load(signal?: AbortSignal) {
    if (!profileId) return setItems([]);
    try {
      setError("");
      const out = await request<NotificationOut[]>(
        "/notifications?" + new URLSearchParams({ profile_id: profileId }),
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
  async function markRead() {
    try {
      await post("/notifications/read", { profile_id: profileId });
      setItems((list) => list?.map((n) => ({ ...n, read: true })) ?? list);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  if (error) return <ErrorBox error={error} retry={() => void load()} />;
  if (!items) return <Loading />;
  const shown = compact ? items.slice(0, 4) : items;
  return (
    <div className="flex flex-col gap-3">
      {shown.length === 0 ? (
        <EmptyState title={tt(lang, "alertsTitle")}>
          {tt(lang, "alertsEmpty")}
        </EmptyState>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {shown.map((n) => (
            <li
              key={n.id}
              className={
                "rounded-[22px] p-4 " +
                (n.read
                  ? "bg-white shadow-[inset_0_0_0_1px_#ede5da]"
                  : "bg-peach")
              }
            >
              <strong>{n.title}</strong>
              {n.body && <p className="m-0 text-[15px]">{n.body}</p>}
              <small>
                {new Date(n.created_at).toLocaleString()}
                {n.link && (
                  <>
                    {" · "}
                    <Link to={n.link}>Open</Link>
                  </>
                )}
              </small>
            </li>
          ))}
        </ul>
      )}
      {!compact && items.some((n) => !n.read) && (
        <button type="button" className="secondary self-start" onClick={() => void markRead()}>
          Mark all read
        </button>
      )}
    </div>
  );
}

export default function Alerts() {
  const { lang } = useApp();
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <Eyebrow>{tt(lang, "navAlerts")}</Eyebrow>
      <h1>{tt(lang, "alertsTitle")}</h1>
      <Card>
        <AlertsPanel />
      </Card>
    </div>
  );
}
