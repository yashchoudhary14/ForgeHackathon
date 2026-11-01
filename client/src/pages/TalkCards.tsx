import { Link } from "react-router-dom";
import type { TalkCard } from "../api/talk";
import { VerdictChip } from "../ui";
import { tt } from "../ui-strings";

export default function CardView({
  card,
  lang,
  disabled,
  onAnswer,
}: {
  card: TalkCard;
  lang: string;
  disabled: boolean;
  onAnswer: (value: string) => void;
}) {
  const box =
    "flex w-full max-w-[92%] flex-col gap-2 self-start rounded-[22px] bg-white p-4 shadow-[inset_0_0_0_1px_#ede5da]";
  const link = "inline-flex min-h-11 items-center font-semibold";
  if (card.kind === "scheme")
    return (
      <div className={box}>
        <div className="flex items-center gap-2">
          <VerdictChip verdict={card.verdict} />
          <span className="font-serif text-xl">{card.name}</span>
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
        <span className="font-serif text-xl">{card.title || "—"}</span>
        <Link className={link} to={"/runs/" + encodeURIComponent(card.run_id)}>
          {tt(lang, "openRun")} →
        </Link>
      </div>
    );
  if (card.kind === "report")
    return (
      <div className={box}>
        <span className="font-serif text-xl">{card.title || "—"}</span>
        {card.report_id ? (
          <Link className={link} to={"/civic/" + encodeURIComponent(card.report_id)}>
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
              className="!bg-peach !text-saffron-text"
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
      <Link className={link} to="/locker">
        {tt(lang, "sendDocument")} →
      </Link>
    </div>
  );
}
