import type { ButtonHTMLAttributes, ReactNode } from "react";
import { tt } from "./ui-strings";
import { useApp } from "./context";
import { ExternalLink, Landmark } from "lucide-react";
import { safeUrl } from "./api/client";

export const cx = (...parts: (string | false | undefined | null)[]) =>
  parts.filter(Boolean).join(" ");

export type PillTone = "dark" | "saffron" | "act" | "lime" | "light" | "ghost";
export const tones: Record<PillTone, string> = {
  dark: "bg-ink text-paper",
  saffron: "bg-saffron text-ink",
  act: "bg-[#2a5fc4] text-white",
  lime: "bg-lime text-ink",
  light: "bg-white text-ink shadow-[inset_0_0_0_1px_#d9cfc0]",
  ghost: "bg-transparent text-ink shadow-[inset_0_0_0_1px_#17140f]",
};
export const pillBase =
  "pill-control inline-flex min-h-12 min-w-11 items-center justify-center gap-2 rounded-full px-6 text-sm font-semibold no-underline transition-transform duration-150 ease-out active:scale-[0.98] motion-reduce:transition-none disabled:cursor-not-allowed disabled:bg-[#e6dec8] disabled:text-[#5c5346] disabled:opacity-100";

export function TextSizeToggle() {
  const { lang, largeText, setLargeText } = useApp();
  return (
    <button
      type="button"
      aria-label={tt(lang, "largeText")}
      aria-pressed={largeText}
      title={tt(lang, "largeText")}
      onClick={() => setLargeText(!largeText)}
      className={cx(
        "text-size-toggle min-h-11 min-w-11 rounded-full px-3 text-sm font-bold shadow-[inset_0_0_0_1px_#d9cfc0]",
        largeText ? "bg-lime text-ink" : "bg-white text-ink",
      )}
    >
      A+
    </button>
  );
}

/** Identifies the link's government host; this does not certify AI-generated text. */
export function SourceLink({
  url,
  children,
}: {
  url?: string | null;
  children?: ReactNode;
}) {
  const { lang } = useApp();
  const href = safeUrl(url);
  if (!href)
    return <span className="text-sm text-ink-soft">{tt(lang, "sourceUnavailable")}</span>;
  const host = new URL(href).hostname.toLowerCase();
  const official = ["gov.in", "nic.in"].some(
    (domain) => host === domain || host.endsWith(`.${domain}`),
  );
  const Icon = official ? Landmark : ExternalLink;
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="source-link inline-flex min-h-11 min-w-11 max-w-full flex-wrap items-center gap-1.5 rounded-full bg-white px-3 py-1 text-xs font-semibold text-saffron-text shadow-[inset_0_0_0_1px_#d9cfc0]"
    >
      <Icon size={14} aria-hidden="true" className="shrink-0" />
      {official && <span>{tt(lang, "officialSource")}</span>}
      <span className="break-words">{children || host}</span>
    </a>
  );
}

export function PillButton({
  tone = "dark",
  className,
  ...rest
}: { tone?: PillTone } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...rest}
      className={cx(pillBase, tones[tone], className)}
    />
  );
}
export function Card({
  children,
  className,
  tint,
  as: Tag = "section",
}: {
  children: ReactNode;
  className?: string;
  tint?: "peach" | "blue";
  as?: "section" | "article" | "div";
}) {
  return (
    <Tag
      className={cx(
        "min-w-0 rounded-[28px] p-5 sm:p-6",
        tint === "peach"
          ? "bg-peach"
          : tint === "blue"
            ? "bg-act-soft"
            : "bg-white shadow-[inset_0_0_0_1px_#ede5da]",
        className,
      )}
    >
      {children}
    </Tag>
  );
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <span className="eyebrow m-0">
      {children}
    </span>
  );
}

export type Verdict = "eligible" | "likely" | "not_eligible" | "unknown";
const verdictStyle: Record<Verdict, string> = {
  eligible: "bg-ok-soft text-ok",
  likely: "bg-warn-soft text-warn",
  not_eligible: "bg-bad-soft text-bad",
  unknown: "bg-[#efe8dc] text-[#3e372e]",
};
const verdictLabel: Record<Verdict, string> = {
  eligible: "verdictEligible",
  likely: "verdictLikely",
  not_eligible: "verdictNot",
  unknown: "verdictUnknown",
};
export function VerdictChip({
  verdict,
  label,
}: {
  verdict: Verdict | string;
  label?: string;
}) {
  const { lang } = useApp();
  const v = (verdict in verdictStyle ? verdict : "unknown") as Verdict;
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold",
        verdictStyle[v],
      )}
    >
      {label ?? tt(lang, verdictLabel[v])}
    </span>
  );
}

export function StatTile({
  value,
  label,
  accent,
}: {
  value: ReactNode;
  label: string;
  accent?: boolean;
}) {
  return (
    <div
      className={cx(
        "flex flex-col gap-1 rounded-[22px] p-4",
        accent ? "bg-lime" : "bg-white shadow-[inset_0_0_0_1px_#ede5da]",
      )}
    >
      <span className="font-serif text-5xl leading-none">{value}</span>
      <span className="text-sm text-ink-soft">{label}</span>
    </div>
  );
}

export type OrbState = "idle" | "listening" | "speaking";
export function Orb({
  state = "idle",
  size = 120,
}: {
  state?: OrbState;
  size?: number;
}) {
  return (
    <div
      className="orb"
      data-state={state}
      style={{ width: size, height: size }}
      role="img"
      aria-label={state}
    />
  );
}

export function ChatBubble({
  from,
  children,
  lang,
}: {
  from: "user" | "bot";
  children: ReactNode;
  lang?: string;
}) {
  return (
    <div
      lang={lang}
      className={cx(
        "stream-entry max-w-[85%] px-4 py-3 text-base",
        from === "user"
          ? "self-end rounded-[22px_22px_6px_22px] bg-ink text-paper"
          : "self-start rounded-[22px_22px_22px_6px] bg-peach text-ink",
      )}
    >
      {children}
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
  icon,
}: {
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div
      role="status"
      className="flex flex-col items-center gap-3 rounded-[22px] border border-dashed border-[#d9cfc0] p-8 text-center text-ink-soft"
    >
      {icon && (
        <span aria-hidden="true" className="grid h-12 w-12 place-items-center rounded-full bg-peach text-saffron-text">
          {icon}
        </span>
      )}
      {title && (
        <strong className="font-serif text-2xl font-normal text-ink">
          {title}
        </strong>
      )}
      {children && <div className="max-w-[65ch]">{children}</div>}
      {action}
    </div>
  );
}
