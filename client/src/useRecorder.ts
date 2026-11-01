import { useEffect, useRef, useState } from "react";

/** Hold-to-talk microphone recorder (MediaRecorder). onBlob gets the finished clip. */
export function useRecorder(
  onBlob: (blob: Blob) => void,
  onError: (kind: "denied") => void,
) {
  const [recording, setRecording] = useState(false);
  const rec = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);
  const holding = useRef(false);
  const cb = useRef(onBlob);
  cb.current = onBlob;
  useEffect(
    () => () => {
      holding.current = false;
      stream.current?.getTracks().forEach((t) => t.stop());
    },
    [],
  );
  async function start() {
    if (holding.current) return;
    holding.current = true;
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!holding.current) {
        s.getTracks().forEach((t) => t.stop());
        return;
      }
      stream.current = s;
      chunks.current = [];
      const r = new MediaRecorder(s);
      rec.current = r;
      r.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      r.onstop = () => {
        s.getTracks().forEach((t) => t.stop());
        setRecording(false);
        const blob = new Blob(chunks.current, {
          type: r.mimeType || "audio/webm",
        });
        if (blob.size > 0) cb.current(blob);
      };
      r.start();
      setRecording(true);
    } catch {
      holding.current = false;
      onError("denied");
    }
  }
  function stop() {
    holding.current = false;
    if (rec.current?.state === "recording") rec.current.stop();
  }
  return { recording, start, stop };
}
