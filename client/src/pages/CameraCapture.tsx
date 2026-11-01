import { useEffect, useRef, useState } from "react";
import { Camera, X } from "lucide-react";

/** getUserMedia preview with frame corners; takes a still and returns it as a JPEG file. */
export default function CameraCapture({
  onCapture,
  onClose,
}: {
  onCapture: (file: File) => void;
  onClose: () => void;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let cancelled = false;
    navigator.mediaDevices
      ?.getUserMedia({ video: { facingMode: "environment" } })
      .then((s) => {
        if (cancelled) return s.getTracks().forEach((t) => t.stop());
        stream.current = s;
        if (video.current) {
          video.current.srcObject = s;
          void video.current.play().then(() => setReady(true));
        }
      })
      .catch(() => setError("Camera not available. Use the photo button instead."));
    if (!navigator.mediaDevices) setError("Camera not available. Use the photo button instead.");
    return () => {
      cancelled = true;
      stream.current?.getTracks().forEach((t) => t.stop());
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
      role="dialog"
      aria-label="Camera"
      className="fixed inset-0 z-50 flex flex-col bg-ink"
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
            Scan document · कागज़ स्कैन करें
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
      <div className="flex items-center justify-between p-4">
        <button
          type="button"
          aria-label="Close"
          onClick={onClose}
          className="!min-h-12 !w-12 !rounded-full !bg-white !p-0 !text-ink"
        >
          <X />
        </button>
        <button
          type="button"
          aria-label="Take photo"
          disabled={!ready}
          onClick={snap}
          className="!h-16 !w-16 !rounded-full !bg-lime !p-0 !text-ink"
        >
          <Camera />
        </button>
        <span className="w-12" />
      </div>
    </div>
  );
}
