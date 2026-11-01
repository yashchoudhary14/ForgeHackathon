import { Link } from "react-router-dom";
import type { TalkCard } from "../api/talk";
import { VerdictChip } from "../ui";
import { tt } from "../ui-strings";

function safeLink(value: string | null): string | undefined {
  try {
    const url = new URL(value || "");
    return url.protocol === "https:" && !url.username && !url.password
      ? url.href
      : undefined;
  } catch {
    return undefined;
  }
}

const labels: Record<string, string[]> = {
  en: [
    "Official portal",
    "Steps",
    "Documents",
    "Fees",
    "Processing time",
    "Sources",
    "Help me apply",
  ],
  hi: [
    "आधिकारिक पोर्टल",
    "चरण",
    "दस्तावेज़",
    "शुल्क",
    "लगने वाला समय",
    "स्रोत",
    "आवेदन में मदद करें",
  ],
  bn: [
    "সরকারি পোর্টাল",
    "ধাপ",
    "নথি",
    "ফি",
    "প্রক্রিয়ার সময়",
    "সূত্র",
    "আবেদনে সাহায্য করুন",
  ],
  as: [
    "চৰকাৰী পৰ্টেল",
    "পদক্ষেপ",
    "নথি",
    "মাচুল",
    "প্ৰক্ৰিয়াৰ সময়",
    "উৎস",
    "আবেদন কৰাত সহায় কৰক",
  ],
};

export default function CardView({
  card,
  lang,
  disabled,
  onAnswer,
  onApply,
  onCapture,
}: {
  card: TalkCard;
  lang: string;
  disabled: boolean;
  onAnswer: (value: string) => void;
  onApply: (service: string, text: string) => void;
  onCapture?: (docType: string, reason: string) => void;
}) {
  const box =
    "flex w-full flex-col gap-2 self-start rounded-tile border border-line border-t-4 border-t-act bg-card p-4 text-ink";
  const link = "inline-flex min-h-11 items-center gap-1 self-start rounded-full border-2 border-act px-4 text-sm font-semibold text-act no-underline hover:bg-act-soft";
  const l = labels[lang] || labels.en;
  const sources = (items: { url: string; title: string }[]) => (
    <div className="flex flex-col gap-1">
      <strong className="text-sm text-ink-soft">{l[5]}</strong>
      {items.map(
        (source, index) =>
          safeLink(source.url) && (
            <a
              key={source.url + index}
              href={safeLink(source.url)}
              target="_blank"
              rel="noopener noreferrer"
              className="break-words underline"
            >
              {source.title}
            </a>
          ),
      )}
    </div>
  );
  if (card.kind === "sources")
    return <div className={box}>{sources(card.sources)}</div>;
  if (card.kind === "service")
    return (
      <div className={box}>
        <span className="font-serif text-xl font-bold leading-tight">{card.service}</span>
        {safeLink(card.official_portal_url) && (
          <a
            className={link}
            href={safeLink(card.official_portal_url)}
            target="_blank"
            rel="noopener noreferrer"
          >
            {l[0]} ↗
          </a>
        )}
        {card.steps.length > 0 && (
          <>
            <strong className="mt-1 text-sm text-ink-soft">{l[1]}</strong>
            <ol className="m-0 list-decimal pl-5">
              {card.steps.map((step, index) => (
                <li key={index}>{step}</li>
              ))}
            </ol>
          </>
        )}
        {card.documents.length > 0 && (
          <>
            <strong className="mt-1 text-sm text-ink-soft">{l[2]}</strong>
            <ul className="m-0 list-disc pl-5">
              {card.documents.map((doc, index) => (
                <li key={index}>{doc}</li>
              ))}
            </ul>
          </>
        )}
        {card.fees && (
          <p className="m-0">
            <strong>{l[3]}: </strong>
            {card.fees}
          </p>
        )}
        {card.time && (
          <p className="m-0">
            <strong>{l[4]}: </strong>
            {card.time}
          </p>
        )}
        {card.notes.map((note, index) => (
          <p className="m-0 text-sm" key={index}>
            {note}
          </p>
        ))}
        {card.sources.length > 0 && sources(card.sources)}
        {safeLink(card.official_portal_url) && (
          <button
            type="button"
            disabled={disabled}
            onClick={() => onApply(card.service_id, `${l[6]}: ${card.service}`)}
          >
            {l[6]}
          </button>
        )}
      </div>
    );
  if (card.kind === "scheme")
    return (
      <div className={box}>
        <div className="flex flex-wrap items-center gap-2">
          <VerdictChip verdict={card.verdict} />
          <span className="font-serif text-xl font-bold leading-tight">{card.name}</span>
        </div>
        {card.summary && <p className="m-0 text-[15px]">{card.summary}</p>}
        <Link className={link} to={"/schemes/" + encodeURIComponent(card.slug)}>
          {tt(lang, "openScheme")} →
        </Link>
      </div>
    );
  if (card.kind === "run")
    return (
      <div className={box}>
        <span className="font-serif text-xl font-bold leading-tight">{card.title || "—"}</span>
        <Link className={link} to={"/runs/" + encodeURIComponent(card.run_id)}>
          {tt(lang, "openRun")} →
        </Link>
      </div>
    );
  if (card.kind === "report")
    return (
      <div className={box}>
        <span className="font-serif text-xl font-bold leading-tight">{card.title || "—"}</span>
        {card.report_id ? (
          <Link
            className={link}
            to={"/civic/" + encodeURIComponent(card.report_id)}
          >
            {tt(lang, "openReport")} →
          </Link>
        ) : (
          <Link className={link} to="/civic/new">
            {tt(lang, "startReport")} →
          </Link>
        )}
      </div>
    );
  if (card.kind === "question")
    return (
      <div className={box} role="group" aria-label={card.label || card.field}>
        <div className="flex flex-wrap gap-2">
          {card.options.map((o) => (
            <button
              key={o}
              type="button"
              disabled={disabled}
              onClick={() => onAnswer(o)}
              className="!min-h-12 !rounded-full !border-2 !border-act !bg-card !text-act hover:!bg-act-soft"
            >
              {o}
            </button>
          ))}
        </div>
      </div>
    );
  return (
    <div className={box}>
      <strong>{card.doc_type}</strong>
      {card.reason && <p className="m-0 text-[15px]">{card.reason}</p>}
      {onCapture ? (
        <button
          disabled={disabled}
          onClick={() => onCapture(card.doc_type, card.reason || "")}
        >
          {tt(lang, "sendDocument")}
        </button>
      ) : (
        <Link className={link} to="/locker">
          {tt(lang, "sendDocument")} →
        </Link>
      )}
    </div>
  );
}
