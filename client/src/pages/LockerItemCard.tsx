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

const swatches = ["bg-[#FFE7D3]", "bg-[#D7E4FF]", "bg-[#E2F2B8]"];

export default function LockerItemCard({
  item: d,
  index = 0,
  isNew = false,
  onDelete,
}: {
  item: LockerItem;
  index?: number;
  isNew?: boolean;
  onDelete: () => void;
}) {
  const variants = variantSizes(d);
  const summary = variantSummary(d);
  const swatch = swatches[index % swatches.length];
  return (
    <Card className="flex flex-col gap-3 !rounded-[20px] !p-4">
      <div className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className={`grid h-12 w-10 shrink-0 place-items-center rounded-[10px] ${swatch}`}
        >
          <FileText size={18} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <strong className="font-serif text-2xl font-normal capitalize">
              {d.title || label(d.doc_type)}
            </strong>
            {isNew && (
              <span className="rounded-full bg-[#FFE7D3] px-2.5 py-1 text-xs font-semibold text-[#9A4A12]">
                New · नया
              </span>
            )}
            {d.meta?.readable === true && (
              <span className="rounded-full bg-ok-soft px-2.5 py-1 text-xs font-semibold text-ok">
                Readable
              </span>
            )}
            {d.meta?.readable === false && (
              <span className="rounded-full bg-warn-soft px-2.5 py-1 text-xs font-semibold text-warn">
                Needs rescan
              </span>
            )}
          </div>
          <div className="text-sm text-ink-soft">
            <span className="capitalize">{label(d.doc_type)}</span>
            {summary && ` · ${summary} ready`}
          </div>
        </div>
        <button
          type="button"
          aria-label={"Delete " + (d.title || d.doc_type)}
          onClick={onDelete}
          className="secondary !min-h-11 !w-11 shrink-0 !rounded-full !p-0"
        >
          <Trash2 size={18} />
        </button>
      </div>
      {!!d.meta?.issues?.length && (
        <p className="m-0 rounded-2xl bg-warn-soft p-2.5 text-sm text-warn">
          {d.meta.issues.join(" · ")}
        </p>
      )}
      {variants.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {variants.map(([name, size]) => (
            <a
              key={name}
              href={lockerFileUrl(d.id, name.toLowerCase())}
              target="_blank"
              rel="noreferrer"
              className="inline-flex min-h-11 items-center gap-1.5 rounded-full bg-ok-soft px-4 text-sm font-semibold no-underline"
              style={{ color: "#155c42" }}
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
