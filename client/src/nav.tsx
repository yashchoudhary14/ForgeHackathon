import { useEffect, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import {
  Bell,
  FileSearch,
  ListChecks,
  MapPin,
  Mic,
  UserCheck,
  UserPlus,
} from "lucide-react";
import { tt } from "./ui-strings";
import { languages, useApp } from "./context";
import { request } from "./api/client";
import { profileInitials } from "./profile-form";
import type { Lang, ProfileOut } from "./api/types";
import type { ReactNode } from "react";
import { cx, pillBase, TextSizeToggle, tones } from "./ui";
import type { PillTone } from "./ui";

export function PillLink({
  to,
  tone = "dark",
  className,
  children,
}: {
  to: string;
  tone?: PillTone;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link
      to={to}
      className={cx(pillBase, tones[tone], className)}
      // Inline because the global unlayered `a { color }` rule beats Tailwind text utilities.
      style={{ color: toneText[tone] }}
    >
      {children}
    </Link>
  );
}

const toneText: Record<PillTone, string> = {
  dark: "#fbf6ee",
  saffron: "#17140f",
  act: "#ffffff",
  lime: "#17140f",
  light: "#17140f",
  ghost: "#17140f",
};

export function PersonIcon({ size = 20, className }: { size?: number; className?: string }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true" className={className}><circle cx="12" cy="8" r="4" /><path d="M4 21v-2a8 8 0 0 1 16 0v2" /></svg>;
}

export function BrandWordmark({ compact = false }: { compact?: boolean }) {
  return (
    <Link
      to="/"
      className="group inline-flex min-h-11 items-center gap-2 px-1.5 no-underline"
      style={{ color: "inherit" }}
    >
      <span
        className={cx(
          "font-serif font-normal leading-none tracking-[-0.02em] text-ink",
          compact ? "text-[26px]" : "text-[26px] md:text-[30px]",
        )}
      >
        Buddy<span className="text-saffron">.</span>
      </span>
      <span className="rounded-full border border-[#f3d2b8] bg-peach px-2.5 py-0.5 text-xs font-semibold text-saffron-text">
        साथी · বন্ধু
      </span>
    </Link>
  );
}

function useNavProfileSummary(profileId: string) {
  const [summary, setSummary] = useState<{ initials: string; label: string }>({
    initials: "",
    label: "",
  });
  useEffect(() => {
    if (!profileId) {
      setSummary({ initials: "", label: "" });
      return;
    }
    const c = new AbortController();
    request<ProfileOut>(`/profile/${encodeURIComponent(profileId)}`, {
      signal: c.signal,
    })
      .then((out) => {
        if (c.signal.aborted) return;
        const initials = profileInitials(out);
        const parts = [out.data?.state, out.data?.occupation].filter(Boolean);
        setSummary({
          initials,
          label: parts.join(" · "),
        });
      })
      .catch(() => {
        if (!c.signal.aborted) setSummary({ initials: "", label: "" });
      });
    return () => c.abort();
  }, [profileId]);
  return summary;
}

export function MobileHeader({ unread = 0 }: { unread?: number }) {
  const { lang, setLang, profileId } = useApp();
  const profileSummary = useNavProfileSummary(profileId);
  return (
    <header className="sticky top-0 z-30 flex items-center justify-between gap-2 border-b border-line/60 bg-paper/95 px-4 pb-2 pt-3 backdrop-blur-md md:hidden">
      <BrandWordmark compact />
      <div className="flex items-center gap-1.5">
        <label className="m-0">
          <span className="sr-only">{tt(lang, "profileLanguage")}</span>
          <select
            value={lang}
            onChange={(e) => setLang(e.target.value as Lang)}
            className="!m-0 !min-h-11 !w-auto !max-w-28 !rounded-full !px-2.5 !py-1 text-xs font-semibold"
          >
            {Object.entries(languages).map(([value, name]) => (
              <option key={value} value={value}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <TextSizeToggle />
        <Link
          to="/profile"
          aria-label={tt(lang, "navProfile")}
          style={{ color: "#17140f" }}
          className="relative inline-flex min-h-11 items-center gap-1.5 rounded-full border border-line bg-white px-3 text-xs font-semibold text-ink no-underline shadow-xs"
        >
          {profileId ? (
            <span className="grid h-6 w-6 place-items-center rounded-full bg-peach text-[11px] font-bold text-saffron-text">
              {profileSummary.initials || <UserCheck size={14} aria-hidden="true" />}
            </span>
          ) : (
            <UserPlus size={15} aria-hidden="true" className="text-saffron-text" />
          )}
          <span className="max-w-[76px] truncate">
            {profileId
              ? profileSummary.label || tt(lang, "navProfile")
              : tt(lang, "setProfile")}
          </span>
          {unread > 0 && (
            <span className="h-2 w-2 rounded-full bg-saffron" aria-hidden="true" />
          )}
        </Link>
      </div>
    </header>
  );
}

const phoneItems = [
  { to: "/talk", key: "navTalk", Icon: Mic },
  { to: "/schemes", key: "navSchemes", Icon: ListChecks },
  { to: "/explain", key: "navExplain", Icon: FileSearch },
  { to: "/civic", key: "navCivic", Icon: MapPin },
  { to: "/profile", key: "navProfile", Icon: UserCheck },
];
export function BottomNav({ unread = 0 }: { unread?: number }) {
  const { lang } = useApp();
  return (
    <nav
      aria-label={tt(lang, "mainNav")}
      className="fixed bottom-[max(0.75rem,env(safe-area-inset-bottom))] left-1/2 z-40 flex w-[calc(100%-1.5rem)] max-w-md -translate-x-1/2 justify-between rounded-full bg-ink px-2 py-1.5 text-paper shadow-xl md:hidden"
    >
      {phoneItems.map(({ to, key, Icon }) => (
        <NavLink
          key={to}
          to={to}
          aria-label={tt(lang, key)}
          style={({ isActive }) => ({ color: isActive ? "#17140f" : "#fbf6ee" })}
          className={({ isActive }) =>
            cx(
              "relative flex min-h-12 min-w-[44px] flex-1 flex-col items-center justify-center gap-1 rounded-full px-1 py-1.5 no-underline transition-transform active:scale-[0.98] motion-reduce:transition-none",
              isActive ? "bg-lime" : "hover:bg-white/10",
            )
          }
        >
          <Icon size={18} aria-hidden="true" className="shrink-0" />
          <span className="text-[0.68rem] font-semibold leading-snug">{tt(lang, key)}</span>
          {key === "navProfile" && unread > 0 && (
            <span className="absolute right-1.5 top-0.5 rounded-full bg-saffron px-1.5 text-[10px] font-bold text-ink">
              {unread}
            </span>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

const desktopItems = [
  { to: "/schemes", key: "navForYou" },
  { to: "/explain", key: "navExplain" },
  { to: "/runs", key: "navApplications" },
  { to: "/locker", key: "navLocker" },
  { to: "/civic", key: "navCivicMap" },
  { to: "/profile", key: "navProfile" },
];
export function PillNav({ unread = 0 }: { unread?: number }) {
  const { lang, setLang, profileId } = useApp();
  const profileSummary = useNavProfileSummary(profileId);
  return (
    <header className="sticky top-0 z-30 hidden flex-wrap items-center justify-between gap-3 border-b border-line/50 bg-paper/95 px-8 py-3 backdrop-blur md:flex">
      <BrandWordmark />
      <nav
        aria-label={tt(lang, "mainNav")}
        className="flex max-w-full flex-wrap gap-1 rounded-full bg-white p-1 shadow-[inset_0_0_0_1px_#ede5da]"
      >
        {desktopItems.map(({ to, key }) => (
          <NavLink
            key={to}
            to={to}
            style={({ isActive }) => ({ color: isActive ? "#fbf6ee" : "#17140f" })}
            className={({ isActive }) =>
              cx(
                "flex min-h-11 items-center gap-1.5 rounded-full px-3.5 text-sm font-semibold no-underline",
                isActive ? "bg-ink text-paper" : "text-ink hover:bg-paper",
              )
            }
          >
            {key === "navProfile" && <PersonIcon size={18} />}
            {tt(lang, key)}
          </NavLink>
        ))}
      </nav>
      <div className="flex items-center gap-2">
        <label className="m-0">
          <span className="sr-only">{tt(lang, "profileLanguage")}</span>
          <select value={lang} onChange={(e) => setLang(e.target.value as Lang)} className="!m-0 !min-h-11 !w-auto !max-w-32 !rounded-full !px-3 !py-1 text-sm">
            {Object.entries(languages).map(([value, name]) => <option key={value} value={value}>{name}</option>)}
          </select>
        </label>
        <TextSizeToggle />
        <Link
          to="/profile"
          style={{ color: "#17140f" }}
          className="inline-flex min-h-11 items-center gap-2 rounded-full bg-white px-3.5 py-1.5 text-xs font-semibold text-ink no-underline shadow-[inset_0_0_0_1px_#ede5da]"
        >
          {profileId ? (
            <>
              <span className="grid h-7 w-7 place-items-center rounded-full bg-peach text-xs font-bold text-saffron-text">
                {profileSummary.initials || <PersonIcon size={15} />}
              </span>
              <span className="max-w-36 truncate">
                {profileSummary.label || tt(lang, "navProfile")}
              </span>
            </>
          ) : (
            <>
              <UserPlus size={16} aria-hidden="true" className="text-saffron-text" />
              <span>{tt(lang, "setProfile")}</span>
            </>
          )}
        </Link>
        <Link
          to="/alerts"
          aria-label={tt(lang, "navAlerts")}
          className="relative grid h-11 w-11 place-items-center rounded-full bg-white shadow-[inset_0_0_0_1px_#ede5da]"
          style={{ color: "inherit" }}
        >
          <Bell size={19} aria-hidden="true" />
          {unread > 0 && (
            <span className="absolute right-2 top-2 h-2.5 w-2.5 rounded-full bg-saffron" />
          )}
        </Link>
        <PillLink to="/talk" tone="saffron">
          <Mic size={18} aria-hidden="true" />
          {tt(lang, "talkMode")}
        </PillLink>
      </div>
    </header>
  );
}
