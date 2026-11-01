import { useEffect, useRef, useState } from "react";
import { Camera, X } from "lucide-react";

/** getUserMedia preview with frame corners; takes a still and returns it as a JPEG file. */
export default function CameraCapture({
  onCapture,
  onClose,
  guidance,
  labels,
}: {
  onCapture: (file: File) => void;
  onClose: () => void;
  guidance?: string;
  labels?: { close: string; capture: string; choose: string };
}) {
  const video = useRef<HTMLVideoElement>(null);
  const dialog = useRef<HTMLDivElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let cancelled = false;
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.focus();
    navigator.mediaDevices
      ?.getUserMedia({ video: { facingMode: "environment" } })
      .then((s) => {
        if (cancelled) return s.getTracks().forEach((t) => t.stop());
        stream.current = s;
        if (video.current) {
          video.current.srcObject = s;
          void video.current.play().then(() => setReady(true)).catch(() => setError("Camera preview unavailable. Choose a photo instead."));
        }
      })
      .catch(() => setError("Camera not available. Use the photo button instead."));
    if (!navigator.mediaDevices) setError("Camera not available. Use the photo button instead.");
    return () => {
      cancelled = true;
      stream.current?.getTracks().forEach((t) => t.stop());
      previous?.focus();
    };
  }, []);
  function snap() {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const c = document.createElement("canvas");
    c.width = v.videoWidth;
    c.height = v.videoHeight;
    c.getContext("2d")?.drawImage(v, 0, 0);
    c.toBlob(
      (b) => {
        if (b) onCapture(new File([b], "scan.jpg", { type: "image/jpeg" }));
      },
      "image/jpeg",
      0.92,
    );
  }
  const corner = "absolute h-8 w-8 border-lime";
  return (
    <div
      ref={dialog}
      tabIndex={-1}
      role="dialog"
      aria-modal="true"
      aria-label="Camera"
      className="fixed inset-0 z-50 flex flex-col bg-ink"
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
        if (e.key === "Tab") {
          const controls = dialog.current?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled)");
          const first = controls?.[0], last = controls?.[controls.length - 1];
          if (e.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) { e.preventDefault(); last?.focus(); }
          else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
        }
      }}
    >
      <div className="relative flex-1 overflow-hidden">
        <video
          ref={video}
          playsInline
          muted
          className="h-full w-full object-cover"
        />
        <div className="pointer-events-none absolute inset-x-4 top-4 flex items-center justify-between">
          <span className="w-11" />
          <span className="rounded-full bg-white/15 px-4 py-2 text-sm font-semibold text-paper backdrop-blur">
            {labels?.capture || "Scan document · कागज़ स्कैन करें"}
          </span>
          <span className="w-11" />
        </div>
        <div aria-hidden="true" className="pointer-events-none absolute inset-[12%]">
          <span className={corner + " left-0 top-0 rounded-tl-[14px] border-l-4 border-t-4"} />
          <span className={corner + " right-0 top-0 rounded-tr-[14px] border-r-4 border-t-4"} />
          <span className={corner + " bottom-0 left-0 rounded-bl-[14px] border-b-4 border-l-4"} />
          <span className={corner + " bottom-0 right-0 rounded-br-[14px] border-b-4 border-r-4"} />
        </div>
        {error && (
          <p role="alert" className="absolute inset-x-4 top-16 rounded-2xl bg-white p-3 text-ink">
            {error}
          </p>
        )}
      </div>
      {guidance && <p role="status" className="m-0 bg-ink px-4 py-3 text-paper">{guidance}</p>}
      <div className="flex items-center justify-between p-4">
        <button
          type="button"
          aria-label={labels?.close || "Close"}
          onClick={onClose}
          className="!min-h-12 !w-12 !rounded-full !bg-white !p-0 !text-ink"
        >
          <X />
        </button>
        <button
          type="button"
          aria-label={labels?.capture || "Take photo"}
          disabled={!ready}
          onClick={snap}
          className="!h-16 !w-16 !rounded-full !bg-lime !p-0 !text-ink"
        >
          <Camera />
        </button>
        <label className="inline-flex min-h-12 cursor-pointer items-center rounded-full bg-white px-4 text-ink">
          {labels?.choose || "Choose photo"}
          <input aria-label={labels?.choose || "Choose a photo or PDF"} className="sr-only" type="file" accept="image/*,application/pdf" onChange={(e) => { const file = e.target.files?.[0]; if (file) onCapture(file); }} />
        </label>
      </div>
    </div>
  );
}
