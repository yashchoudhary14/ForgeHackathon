import { useTranslation, Text } from "../context";
import { Download, FileText, Trash2 } from "lucide-react";
import {
  formatKb,
  lockerFileUrl,
  variantSizes,
  variantSummary,
} from "../api/locker";
import type { LockerItem } from "../api/locker";
import { Card } from "../ui";

export const label = (s: string) => s.replaceAll("_", " ");

const swatches = ["bg-peach text-saffron-text", "bg-act-soft text-act", "bg-ok-soft text-ok"];
const spines = ["border-l-saffron", "border-l-act", "border-l-ok"];

export default function LockerItemCard({
  item: d,
  index = 0,
  isNew = false,
  onDelete,
  profileId = "",
}: {
  item: LockerItem;
  index?: number;
  isNew?: boolean;
  onDelete: () => void;
  profileId?: string;
}) {
  const tr = useTranslation();
  const variants = variantSizes(d);
  const summary = variantSummary(d);
  const swatch = swatches[index % swatches.length];
  const spine = spines[index % spines.length];
  return (
    <Card className={`flex flex-col gap-3 !rounded-tile border border-l-[8px] border-line !bg-card !p-4 !shadow-none ${spine}`}>
      <div className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className={`relative grid h-14 w-11 shrink-0 place-items-center rounded-md rounded-tr-[14px] border border-line ${swatch}`}
        >
          <FileText size={18} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <strong className="font-serif text-xl font-bold leading-tight capitalize">
              {d.title || tr(label(d.doc_type))}
            </strong>
            {isNew && (
              <span className="rounded-lg bg-lime px-2 py-0.5 text-xs font-bold text-ink">
                 <Text value="New" /> </span>
            )}
            {d.meta?.readable === true && (
              <span className="rounded-lg border border-ok px-2 py-0.5 text-xs font-bold text-ok">
                 <Text value="Readable" /> </span>
            )}
            {d.meta?.readable === false && (
              <span className="rounded-lg border border-warn bg-warn-soft px-2 py-0.5 text-xs font-bold text-warn">
                 <Text value="Needs rescan" /> </span>
            )}
          </div>
          <div className="text-sm text-ink-soft">
            <span className="capitalize"><Text value={label(d.doc_type)} /></span>
            {summary && ` · ${summary} ${tr("ready")}`}
          </div>
        </div>
        <button
          type="button"
          aria-label={tr("Delete") + " " + (d.title || tr(label(d.doc_type)))}
          onClick={onDelete}
          className="secondary !min-h-11 !w-11 shrink-0 !rounded-full border border-line !bg-card !p-0 !text-ink-soft hover:!text-bad"
        >
          <Trash2 size={18} />
        </button>
      </div>
      {!!d.meta?.issues?.length && (
        <p className="m-0 border-l-4 border-warn bg-warn-soft px-3 py-2 text-sm text-warn">
          {d.meta.issues.map((issue) => tr(label(issue))).join(" · ")}
        </p>
      )}
      {variants.length > 0 && (
        <div className="-mx-4 -mb-4 flex flex-wrap gap-2 border-t border-dashed border-line bg-paper/60 px-4 py-3">
          {variants.map(([name, size]) => (
            <a
              key={name}
              href={profileId ? lockerFileUrl(d.id, name.toLowerCase(), profileId) : undefined}
              target="_blank"
              rel="noreferrer"
              className="inline-flex min-h-11 items-center gap-1.5 rounded-full border border-ok bg-card px-4 text-sm font-semibold no-underline"
              style={{ color: "var(--color-ok, #1E7B4F)" }}
            >
              <Download size={14} aria-hidden="true" /> {name}{" "}
              {formatKb(size)}
            </a>
          ))}
        </div>
      )}
    </Card>
  );
}
