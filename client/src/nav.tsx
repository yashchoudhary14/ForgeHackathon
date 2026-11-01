import { Link, NavLink } from "react-router-dom";
import { Bell, FileText, MapPin, Mic, ListChecks } from "lucide-react";
import { tt } from "./ui-strings";
import { languages, useApp } from "./context";
import type { Lang } from "./api/types";
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

const phoneItems = [
  { to: "/talk", key: "navTalk", Icon: Mic },
  { to: "/schemes", key: "navSchemes", Icon: ListChecks },
  { to: "/locker", key: "navLocker", Icon: FileText },
  { to: "/civic", key: "navCivic", Icon: MapPin },
  { to: "/alerts", key: "navAlerts", Icon: Bell },
];
export function BottomNav({ unread = 0 }: { unread?: number }) {
  const { lang } = useApp();
  return (
    <nav
      aria-label={tt(lang, "mainNav")}
      className="fixed bottom-[max(1rem,env(safe-area-inset-bottom))] left-1/2 z-40 flex w-[calc(100%-1.5rem)] max-w-md -translate-x-1/2 justify-between gap-1 rounded-full bg-ink px-2 py-1.5 text-paper shadow-xl md:hidden"
    >
      {phoneItems.map(({ to, key, Icon }) => (
        <NavLink
          key={to}
          to={to}
          aria-label={tt(lang, key)}
          style={({ isActive }) => ({ color: isActive ? "#17140f" : "#fbf6ee" })}
          className={({ isActive }) =>
            cx(
              "relative flex min-h-12 min-w-11 flex-1 flex-col items-center justify-center gap-1 rounded-full px-1 py-1.5 no-underline transition-transform active:scale-[0.98] motion-reduce:transition-none",
              isActive ? "bg-lime" : "hover:bg-white/10",
            )
          }
        >
          <Icon size={18} aria-hidden="true" className="shrink-0" />
          <span className="text-[0.65rem] font-semibold leading-snug">{tt(lang, key)}</span>
          {key === "navAlerts" && unread > 0 && (
            <span className="absolute right-1 top-0 rounded-full bg-white px-1 text-[10px] font-bold text-ink">{unread}</span>
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
];
export function PillNav({ unread = 0 }: { unread?: number }) {
  const { lang, setLang, t } = useApp();
  return (
    <header className="sticky top-0 z-30 hidden flex-wrap items-center justify-between gap-3 bg-paper/95 px-8 py-3 backdrop-blur md:flex">
      <Link
        to="/"
        className="inline-flex min-h-11 items-center px-2 font-serif text-3xl no-underline"
        style={{ color: "inherit" }}
      >
        Adhikaar
      </Link>
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
                "flex min-h-11 items-center rounded-full px-3 text-sm font-semibold no-underline",
                isActive ? "bg-ink text-paper" : "text-ink",
              )
            }
          >
            {tt(lang, key)}
          </NavLink>
        ))}
      </nav>
      <div className="flex items-center gap-2">
        <label className="m-0">
          <span className="sr-only">{t.language}</span>
          <select value={lang} onChange={(e) => setLang(e.target.value as Lang)} className="!m-0 !min-h-11 !w-auto !max-w-32 !rounded-full !px-3 !py-1 text-sm">
            {Object.entries(languages).map(([value, name]) => <option key={value} value={value}>{name}</option>)}
          </select>
        </label>
        <TextSizeToggle />
        <Link
          to="/alerts"
          aria-label={tt(lang, "navAlerts")}
          className="relative grid h-12 w-12 place-items-center rounded-full bg-white shadow-[inset_0_0_0_1px_#ede5da]"
          style={{ color: "inherit" }}
        >
          <Bell size={20} aria-hidden="true" />
          {unread > 0 && (
            <span className="absolute right-2 top-2 h-3 w-3 rounded-full bg-saffron" />
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
