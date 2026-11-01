import { useTranslation, Text, useApp } from "../context";
import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import type { MatchResult } from "../api/types";
import { Citations } from "../components";
import { Card, StatTile, VerdictChip } from "../ui";
import { PillLink } from "../nav";
import { tt } from "../ui-strings";
import { CheckCircle2, HelpCircle, Landmark, XCircle } from "lucide-react";

const stampInk: Record<string, string> = {
  eligible: "border-ok text-ok",
  likely: "border-warn text-warn",
  not_eligible: "border-bad text-bad",
  unknown: "border-ink-soft text-ink-soft",
};

/** Rubber-stamp frame around the verdict: double-ruled ink border, slight tilt. */
export function VerdictStamp({ verdict, children }: { verdict: string; children: ReactNode }) {
  return (
    <span
      className={
        "inline-flex shrink-0 -rotate-2 items-center gap-2 rounded-lg border-[4px] border-double bg-card px-2.5 py-1 font-serif motion-reduce:rotate-0 [&>span]:!bg-transparent [&>span]:!px-0 [&>span]:!py-0 [&>span]:!text-[0.95rem] [&>span]:!font-bold [&>span]:!text-current " +
        (stampInk[verdict] || stampInk.unknown)
      }
    >
      {children}
    </span>
  );
}

export function MatchStats({ matches }: { matches: MatchResult[] }) {
  const { lang } = useApp();
  const eligible = matches.filter((m) => m.verdict === "eligible").length;
  const likely = matches.filter((m) => m.verdict === "likely").length;
  return (
    <div className="grid grid-cols-3 overflow-hidden rounded-card border border-line bg-card [&>div]:!rounded-none [&>div]:!shadow-none [&>div+div]:border-l [&>div+div]:border-line">
      <StatTile accent value={eligible} label={tt(lang, "verdictEligible")} />
      <StatTile value={likely} label={tt(lang, "verdictLikely")} />
      <StatTile value={matches.length} label={tt(lang, "checked")} />
    </div>
  );
}

export function MatchCards({ matches }: { matches: MatchResult[] }) {
  const tr = useTranslation();
  const { lang } = useApp();
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {matches.map((m) => {
        const pct = Math.round(Math.max(0, Math.min(1, m.confidence)) * 100);
        const slug = encodeURIComponent(m.scheme.slug);
        return (
          <Card as="article" key={m.scheme.slug} className="stream-entry flex flex-col gap-0 !rounded-card border border-line !bg-card !p-0 !shadow-none">
            <div className="flex flex-col gap-2 px-5 pb-4 pt-5">
              <div className="flex items-start justify-between gap-3">
                {(m.scheme.ministry || m.scheme.state) ? <small className="inline-flex min-w-0 items-center gap-1.5 pt-1 text-xs font-semibold text-ink-soft"><Landmark size={14} aria-hidden="true" className="shrink-0 text-saffron-text" /><span className="line-clamp-2">{m.scheme.ministry || m.scheme.state}</span></small> : <span />}
                <VerdictStamp verdict={m.verdict}>
                  <VerdictChip verdict={m.verdict} />
                  <span className="border-l border-current pl-2 font-sans text-xs" aria-label={`${tr("Match confidence:")} ${pct}%`}>{pct}%</span>
                </VerdictStamp>
              </div>
              <h2 className="m-0 font-serif text-[1.55rem] font-bold leading-tight">
                <Link
                  to={"/schemes/" + slug}
                  className="inline-flex min-h-11 items-center"
                  style={{ color: "inherit", textDecoration: "none" }}
                >
                  {m.scheme.name}
                </Link>
              </h2>
              {m.scheme.brief && <p className="m-0 text-ink-soft">{m.scheme.brief}</p>}
            </div>
            <details open={m.reasons.length > 0 && m.reasons.length < 4} className="border-t border-line px-5 py-3 [&>summary]:min-h-11 [&>summary]:cursor-pointer [&>summary]:py-2 [&>summary]:font-semibold [&>summary]:text-ink">
              <summary><Text value="Why this matches you" /></summary>
              <div className="flex flex-col gap-3 pb-1">
              {m.reasons.map((r, i) => (
                <div key={i} className="[&_.citations]:m-0 [&_.citations]:list-none [&_.citations]:p-0 [&_blockquote]:!rounded-none [&_blockquote]:!border-l-[3px] [&_blockquote]:!border-act [&_blockquote]:!bg-act-soft/60 [&_blockquote]:!py-2 [&_blockquote]:!pl-3 [&_blockquote>p]:font-serif [&_blockquote>p]:text-[0.98rem] [&_blockquote>p]:leading-snug [&_blockquote>p]:before:mr-1.5 [&_blockquote>p]:before:font-bold [&_blockquote>p]:before:text-act [&_blockquote>p]:before:content-['§']">
                  <p className="m-0 flex items-start gap-2">
                    <span
                      className="mt-0.5 shrink-0"
                      aria-label={
                        r.met === true
                          ? tr("Met")
                          : r.met === false
                            ? tr("Not met")
                            : tr("Unknown")
                      }
                    >
                      <span className="sr-only">{r.met === true ? tr("Met") : r.met === false ? tr("Not met") : tr("Unknown")}</span>
                      {r.met === true ? <CheckCircle2 size={18} aria-hidden="true" className="inline shrink-0 text-ok" /> : r.met === false ? <XCircle size={18} aria-hidden="true" className="inline shrink-0 text-bad" /> : <HelpCircle size={18} aria-hidden="true" className="inline shrink-0 text-warn" />}
                    </span>{" "}
                    <span>{r.claim}</span>
                  </p>
                  {r.citation && <div className="ml-[26px]"><Citations items={[r.citation]} /></div>}
                </div>
              ))}
              </div>
            </details>
            {m.documents_needed.length > 0 && (
              <div className="flex flex-col gap-2 border-t border-line px-5 py-3 text-sm">
                <strong><Text value="Documents you’ll need" /></strong>
                <ul className="m-0 flex list-none flex-wrap gap-2 p-0">{m.documents_needed.map((doc, i) => <li key={`${doc}-${i}`} className="rounded-lg border border-line bg-paper px-2.5 py-1 text-xs font-medium text-ink">{doc}</li>)}</ul>
              </div>
            )}
            {m.missing_info.length > 0 && (
              <p className="m-0 border-l-4 border-warn bg-warn-soft px-5 py-2 text-sm text-warn">
                {m.missing_info.join(", ")}.{" "}
                <Link to="/" className="inline-flex min-h-11 items-center font-semibold">{tt(lang, "navForYou")}</Link>
              </p>
            )}
            <div className="mt-auto flex flex-wrap gap-2 border-t border-line bg-paper/60 px-5 py-4 [&>a:first-child]:flex-1">
              <PillLink to={"/schemes/" + slug}> <Text value="Apply with agent" /> </PillLink>
              <PillLink to={"/explain?scheme=" + slug} tone="light">
                 <Text value="Explain" /> </PillLink>
            </div>
          </Card>
        );
      })}
    </div>
  );
}
