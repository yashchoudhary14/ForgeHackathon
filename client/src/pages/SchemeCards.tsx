import { Link } from "react-router-dom";
import type { MatchResult } from "../api/types";
import { Citations } from "../components";
import { Text, useApp } from "../context";
import { Card, StatTile, VerdictChip } from "../ui";
import { PillLink } from "../nav";
import { tt } from "../ui-strings";
import { CheckCircle2, HelpCircle, Landmark, XCircle } from "lucide-react";

export function MatchStats({ matches }: { matches: MatchResult[] }) {
  const eligible = matches.filter((m) => m.verdict === "eligible").length;
  const likely = matches.filter((m) => m.verdict === "likely").length;
  return (
    <div className="grid grid-cols-3 gap-3">
      <StatTile accent value={eligible} label={tt("en", "verdictEligible")} />
      <StatTile value={likely} label={tt("en", "verdictLikely")} />
      <StatTile value={matches.length} label="checked" />
    </div>
  );
}

export function MatchCards({ matches }: { matches: MatchResult[] }) {
  const { lang } = useApp();
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {matches.map((m) => {
        const pct = Math.round(Math.max(0, Math.min(1, m.confidence)) * 100);
        const slug = encodeURIComponent(m.scheme.slug);
        return (
          <Card as="article" key={m.scheme.slug} className="stream-entry flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <VerdictChip verdict={m.verdict} />
              <span className="rounded-full bg-paper px-2.5 py-1 text-xs font-semibold text-ink-soft" aria-label={`Match confidence: ${pct}%`}>{pct}%</span>
            </div>
            {(m.scheme.ministry || m.scheme.state) && <small className="inline-flex items-center gap-1.5 self-start rounded-full bg-paper px-3 py-1 text-xs font-semibold text-[#5c5346]"><Landmark size={14} aria-hidden="true" className="shrink-0" />{m.scheme.ministry || m.scheme.state}</small>}
            <h2 className="m-0 text-[1.65rem]">
              <Link
                to={"/schemes/" + slug}
                className="inline-flex min-h-11 items-center"
                style={{ color: "inherit", textDecoration: "none" }}
              >
                {m.scheme.name}
              </Link>
            </h2>
            {m.scheme.brief && <p className="m-0">{m.scheme.brief}</p>}
            <details open={m.reasons.length > 0 && m.reasons.length < 4}>
              <summary><Text value="Why this matches you" /></summary>
              {m.reasons.map((r, i) => (
                <div key={i} className="mb-2">
                  <p className="m-0">
                    <span
                      aria-label={
                        r.met === true
                          ? "Met"
                          : r.met === false
                            ? "Not met"
                            : "Unknown"
                      }
                    >
                      <span className="sr-only">{r.met === true ? "Met" : r.met === false ? "Not met" : "Unknown"}</span>
                      {r.met === true ? <CheckCircle2 size={16} aria-hidden="true" className="mr-1.5 inline shrink-0 text-ok" /> : r.met === false ? <XCircle size={16} aria-hidden="true" className="mr-1.5 inline shrink-0 text-bad" /> : <HelpCircle size={16} aria-hidden="true" className="mr-1.5 inline shrink-0 text-warn" />}
                    </span>{" "}
                    {r.claim}
                  </p>
                  {r.citation && <Citations items={[r.citation]} />}
                </div>
              ))}
            </details>
            {m.documents_needed.length > 0 && (
              <div className="flex flex-col gap-2 text-sm">
                <strong><Text value="Documents you’ll need" /></strong>
                <ul className="m-0 flex list-none flex-wrap gap-2 p-0">{m.documents_needed.map((doc, i) => <li key={`${doc}-${i}`} className="rounded-full bg-paper px-3 py-1 text-xs font-medium text-ink shadow-[inset_0_0_0_1px_#ede5da]">{doc}</li>)}</ul>
              </div>
            )}
            {m.missing_info.length > 0 && (
              <p className="m-0 rounded-2xl bg-warn-soft p-3 text-sm text-warn">
                {m.missing_info.join(", ")}.{" "}
                <Link to="/" className="inline-flex min-h-11 items-center font-semibold">{tt(lang, "navForYou")}</Link>
              </p>
            )}
            <div className="mt-auto flex flex-wrap gap-2">
              <PillLink to={"/schemes/" + slug}>Apply with agent</PillLink>
              <PillLink to={"/explain?scheme=" + slug} tone="light">
                Explain
              </PillLink>
            </div>
          </Card>
        );
      })}
    </div>
  );
}
