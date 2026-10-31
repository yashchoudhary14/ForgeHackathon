import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router-dom";
import { tt } from "./ui-strings";
import { useApp } from "./context";

export const cx = (...parts: (string | false | undefined | null)[]) =>
  parts.filter(Boolean).join(" ");

export type PillTone = "dark" | "saffron" | "act" | "lime" | "light" | "ghost";
const tones: Record<PillTone, string> = {
  dark: "bg-ink text-paper",
  saffron: "bg-saffron text-ink",
  act: "bg-act text-white",
  lime: "bg-lime text-ink",
  light: "bg-white text-ink shadow-[inset_0_0_0_1px_#d9cfc0]",
  ghost: "bg-transparent text-ink shadow-[inset_0_0_0_1px_#17140f]",
};
const pillBase =
  "inline-flex min-h-12 items-center justify-center gap-2 rounded-full px-6 text-[15px] font-semibold no-underline disabled:cursor-not-allowed disabled:opacity-50";

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

export function Card({
  children,
  className,
  tint,
}: {
  children: ReactNode;
  className?: string;
  tint?: "peach" | "blue";
}) {
  return (
    <section
      className={cx(
        "rounded-[28px] p-5 sm:p-6",
        tint === "peach"
          ? "bg-peach"
          : tint === "blue"
            ? "bg-act-soft"
            : "bg-white shadow-[inset_0_0_0_1px_#ede5da]",
        className,
      )}
    >
      {children}
    </section>
  );
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <span className="block text-xs font-semibold uppercase tracking-[0.06em] text-[#6b6358]">
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
        "max-w-[85%] px-4 py-3 text-[17px]",
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
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div
      role="status"
      className="flex flex-col items-center gap-3 rounded-[22px] border border-dashed border-[#d9cfc0] p-8 text-center text-ink-soft"
    >
      <strong className="font-serif text-2xl font-normal text-ink">
        {title}
      </strong>
      {children && <p className="m-0">{children}</p>}
      {action}
    </div>
  );
}
