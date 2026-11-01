import { createContext, useContext, useEffect, useState } from "react";
import type { Dispatch, ReactNode, SetStateAction } from "react";
import type { TalkMessage } from "../api/talk";
import { persist, useApp } from "../context";

function read<T>(key: string, fallback: T): T {
  try {
    return JSON.parse(localStorage.getItem(key) || "null") ?? fallback;
  } catch {
    return fallback;
  }
}
interface BuddyState {
  messages: TalkMessage[];
  setMessages: Dispatch<SetStateAction<TalkMessage[]>>;
  open: boolean;
  setOpen: (value: boolean) => void;
  runId: string;
  setRunId: (id: string) => void;
  onboarding: boolean;
  setOnboarding: (value: boolean) => void;
}
const Context = createContext<BuddyState | null>(null);
export function BuddyProvider({ children }: { children: ReactNode }) {
  const { profileId } = useApp();
  const initial = read<{ messages?: TalkMessage[]; runId?: string }>(
    `buddy-session:${profileId}`,
    {},
  );
  const [messages, setMessages] = useState<TalkMessage[]>(() =>
    Array.isArray(initial.messages) ? initial.messages.slice(-24) : [],
  );
  const [runId, setRunId] = useState(initial.runId || "");
  const [open, setOpen] = useState(false);
  const [onboarding, setOnboardingState] = useState(() =>
    read("buddy-onboarding", false),
  );
  const [sessionProfile, setSessionProfile] = useState(profileId);
  useEffect(() => {
    if (sessionProfile === profileId) return;
    if (sessionProfile) {
      const next = read<{ messages?: TalkMessage[]; runId?: string }>(
        `buddy-session:${profileId}`,
        {},
      );
      setMessages(next.messages || []);
      setRunId(next.runId || "");
    }
    setSessionProfile(profileId);
  }, [profileId, sessionProfile]);
  useEffect(() => {
    if (sessionProfile !== profileId) return;
    // Raw citizen transcripts and human answers stay in memory. The server stores
    // redacted conversation history; only Buddy's replies are cached here.
    persist(
      `buddy-session:${profileId}`,
      JSON.stringify({
        runId,
        messages: messages.filter((m) => m.from === "bot").slice(-24),
      }),
    );
  }, [profileId, sessionProfile, messages, runId]);
  function setOnboarding(value: boolean) {
    setOnboardingState(value);
    persist("buddy-onboarding", JSON.stringify(value));
  }
  return (
    <Context.Provider
      value={{
        messages,
        setMessages,
        runId,
        setRunId,
        open,
        setOpen,
        onboarding,
        setOnboarding,
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useBuddy() {
  const value = useContext(Context);
  if (!value) throw new Error("BuddyProvider is missing");
  return value;
}
