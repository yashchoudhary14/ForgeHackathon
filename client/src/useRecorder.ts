import { useEffect, useRef, useState } from "react";
import { silenceExpired } from "./buddy/mic";

/** Tap/hold recorder with a local silence meter and a bounded STT clip. */
export function useRecorder(
  onBlob: (blob: Blob) => void,
  onError: (kind: "denied") => void,
  onPreview?: (blob: Blob) => void,
) {
  const [recording, setRecording] = useState(false);
  const active = useRef(false),
    discard = useRef(false),
    mounted = useRef(true);
  const generation = useRef(0);
  const rec = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const context = useRef<AudioContext | null>(null);
  const frame = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const previewTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const preview = useRef<MediaRecorder | null>(null);
  const previewCallback = useRef(onPreview);
  previewCallback.current = onPreview;
  const cb = useRef(onBlob),
    error = useRef(onError);
  cb.current = onBlob;
  error.current = onError;
  function release() {
    cancelAnimationFrame(frame.current);
    clearTimeout(timer.current);
    clearTimeout(previewTimer.current);
    if (preview.current?.state === "recording") preview.current.stop();
    preview.current = null;
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    void context.current?.close().catch(() => {});
    context.current = null;
  }
  function stop() {
    generation.current++;
    active.current = false;
    if (rec.current?.state === "recording") rec.current.stop();
    release();
    if (mounted.current) setRecording(false);
  }
  function cancel() {
    discard.current = true;
    stop();
  }
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      cancel();
    };
  }, []);
  async function start() {
    if (active.current || rec.current) return;
    const ticket = ++generation.current;
    active.current = true;
    discard.current = false;
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (
        !active.current ||
        !mounted.current ||
        generation.current !== ticket
      ) {
        media.getTracks().forEach((track) => track.stop());
        return;
      }
      stream.current = media;
      const chunks: Blob[] = [];
      const recorder = new MediaRecorder(media);
      rec.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunks.push(event.data);
      };
      recorder.onstop = () => {
        rec.current = null;
        release();
        active.current = false;
        if (mounted.current) setRecording(false);
        const blob = new Blob(chunks, {
          type: recorder.mimeType || "audio/webm",
        });
        if (!discard.current && mounted.current && blob.size) cb.current(blob);
      };
      recorder.onerror = () => {
        cancel();
        error.current("denied");
      };
      recorder.start();
      setRecording(true);
      timer.current = setTimeout(stop, 28000);
      // Independent short clips have their own container headers. The final
      // recording stays intact; drafts never enter the conversation/model.
      function previewClip() {
        if (
          !previewCallback.current ||
          !active.current ||
          generation.current !== ticket
        )
          return;
        try {
          const draft = new MediaRecorder(media),
            parts: Blob[] = [];
          preview.current = draft;
          draft.ondataavailable = (event) => {
            if (event.data.size) parts.push(event.data);
          };
          draft.onstop = () => {
            if (!active.current || generation.current !== ticket) return;
            const blob = new Blob(parts, {
              type: draft.mimeType || "audio/webm",
            });
            if (blob.size) previewCallback.current?.(blob);
            previewClip();
          };
          draft.onerror = () => {
            clearTimeout(previewTimer.current);
            draft.onstop = null;
          };
          draft.start();
          previewTimer.current = setTimeout(() => {
            if (draft.state === "recording") draft.stop();
          }, 2500);
        } catch {
          /* Some browsers allow only one recorder; final STT still works. */
        }
      }
      previewClip();
      try {
        const ac = new AudioContext();
        context.current = ac;
        await ac.resume();
        if (!active.current || generation.current !== ticket) return;
        const analyser = ac.createAnalyser();
        analyser.fftSize = 1024;
        ac.createMediaStreamSource(media).connect(analyser);
        const samples = new Float32Array(analyser.fftSize);
        let lastSound = performance.now();
        const meter = () => {
          if (!active.current) return;
          analyser.getFloatTimeDomainData(samples);
          const rms = Math.sqrt(
            samples.reduce((sum, sample) => sum + sample * sample, 0) /
              samples.length,
          );
          const now = performance.now();
          if (rms >= 0.015) lastSound = now;
          if (silenceExpired(rms, now, lastSound)) {
            stop();
            return;
          }
          frame.current = requestAnimationFrame(meter);
        };
        meter();
      } catch {
        /* Tap/hold and clip deadline still work without AudioContext. */
      }
    } catch {
      if (generation.current !== ticket) return;
      rec.current = null;
      active.current = false;
      release();
      if (mounted.current) {
        setRecording(false);
        error.current("denied");
      }
    }
  }
  return {
    recording,
    start,
    stop,
    cancel,
    isActive: () => active.current,
    toggle: () => (active.current ? stop() : void start()),
  };
}
