import { useEffect, useRef, useState } from "react";
import { assetUrl, BASE } from "../api/client";

/** One audio element and a sentence queue survive all route changes. */
export function useBuddyAudio(onBlocked: () => void) {
  const element = useRef<HTMLAudioElement | null>(null);
  const queue = useRef<string[]>([]),
    last = useRef<string[]>([]);
  const objectUrls = useRef<string[]>([]);
  const generation = useRef(0);
  const [speaking, setSpeaking] = useState(false);
  const blocked = useRef(onBlocked);
  blocked.current = onBlocked;
  const unlocked = useRef(false);
  function player() {
    if (!element.current) element.current = new Audio();
    return element.current;
  }
  function stop() {
    generation.current++;
    queue.current = [];
    element.current?.pause();
    if (element.current) {
      element.current.onended = null;
      element.current.onerror = null;
    }
    setSpeaking(false);
  }
  function unlock() {
    if (unlocked.current) return;
    unlocked.current = true;
    // Prime this same media element synchronously inside the citizen's gesture.
    const a = player();
    a.src =
      "data:audio/wav;base64,UklGRnQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YVAAAACAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgA==";
    void a.play().catch(() => {});
  }
  function next() {
    const src = queue.current.shift();
    if (!src) {
      setSpeaking(false);
      return;
    }
    const a = player();
    a.src = src;
    a.onended = next;
    a.onerror = () => {
      setSpeaking(false);
      blocked.current();
    };
    setSpeaking(true);
    void a.play().catch(() => {
      setSpeaking(false);
      blocked.current();
    });
  }
  function begin() {
    stop();
    last.current = [];
    objectUrls.current.forEach((url) => URL.revokeObjectURL(url));
    objectUrls.current = [];
  }
  function enqueue(url: string) {
    const src = url.startsWith("blob:") ? url : assetUrl(url);
    if (!src) return;
    last.current.push(src);
    queue.current.push(src);
    if (!element.current || element.current.paused || element.current.ended)
      next();
  }
  async function say(text: string, language: string) {
    begin();
    const current = generation.current;
    try {
      const response = await fetch(BASE + "/api/voice/tts", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, language }),
      });
      if (!response.ok) throw new Error("Speech unavailable");
      const blob = await response.blob();
      if (current !== generation.current) return;
      const url = URL.createObjectURL(blob);
      objectUrls.current.push(url);
      enqueue(url);
    } catch {
      if (current === generation.current) blocked.current();
    }
  }
  function replay() {
    unlock();
    stop();
    queue.current = [...last.current];
    next();
  }
  useEffect(
    () => () => {
      generation.current++;
      element.current?.pause();
      objectUrls.current.forEach((url) => URL.revokeObjectURL(url));
    },
    [],
  );
  return { speaking, unlock, stop, begin, enqueue, say, replay };
}
