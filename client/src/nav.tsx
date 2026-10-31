import { Link, NavLink } from "react-router-dom";
import { Bell, FileText, MapPin, Mic, ListChecks } from "lucide-react";
import { tt } from "./ui-strings";
import { useApp } from "./context";
import type { ReactNode } from "react";
import { cx, pillBase, tones } from "./ui";
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
      style={{ color: "inherit" }}
    >
      {children}
    </Link>
  );
}

const phoneItems = [
  { to: "/talk", key: "navTalk", Icon: Mic },
  { to: "/schemes", key: "navSchemes", Icon: ListChecks },
  { to: "/locker", key: "navDocuments", Icon: FileText },
  { to: "/civic", key: "navCivic", Icon: MapPin },
  { to: "/alerts", key: "navAlerts", Icon: Bell },
];
export function BottomNav({ unread = 0 }: { unread?: number }) {
  const { lang } = useApp();
  return (
    <nav
      aria-label={tt(lang, "mainNav")}
      className="fixed bottom-4 left-1/2 z-40 flex -translate-x-1/2 gap-1 rounded-full bg-ink p-1.5 shadow-xl md:hidden"
    >
      {phoneItems.map(({ to, key, Icon }) => (
        <NavLink
          key={to}
          to={to}
          aria-label={tt(lang, key)}
          style={{ color: "inherit" }}
          className={({ isActive }) =>
            cx(
              "relative grid h-12 w-12 place-items-center rounded-full",
              isActive ? "bg-saffron text-ink" : "text-paper",
            )
          }
        >
          <Icon size={20} aria-hidden="true" />
          {key === "navAlerts" && unread > 0 && (
            <span className="absolute right-1 top-1 h-3 w-3 rounded-full bg-lime" />
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
  const { lang } = useApp();
  return (
    <header className="sticky top-0 z-30 hidden items-center justify-between gap-4 bg-paper/90 px-8 py-4 backdrop-blur md:flex">
      <Link
        to="/"
        className="font-serif text-3xl no-underline"
        style={{ color: "inherit" }}
      >
        Adhikaar
      </Link>
      <nav
        aria-label={tt(lang, "mainNav")}
        className="flex gap-1 rounded-full bg-white p-1 shadow-[inset_0_0_0_1px_#ede5da]"
      >
        {desktopItems.map(({ to, key }) => (
          <NavLink
            key={to}
            to={to}
            style={{ color: "inherit" }}
            className={({ isActive }) =>
              cx(
                "flex min-h-11 items-center rounded-full px-4 text-[15px] font-semibold no-underline",
                isActive ? "bg-ink text-paper" : "text-ink",
              )
            }
          >
            {tt(lang, key)}
          </NavLink>
        ))}
      </nav>
      <div className="flex items-center gap-2">
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
