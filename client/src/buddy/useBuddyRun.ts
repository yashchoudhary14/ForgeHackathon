import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { request, websocketUrl, withOwner } from "../api/client";
import type { ClientMessage, Human, RunOut, ServerMessage } from "../api/types";
import { useApp } from "../context";
import { useBuddy } from "./context";

export function useBuddyRun(
  onHuman: (human: Human) => void,
  onClear: () => void,
  onError: (message: string) => void,
) {
  const { profileId } = useApp();
  const { runId, setRunId } = useBuddy();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [human, setHuman] = useState<Human | null>(null);
  const pending = useRef<Human | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const callbacks = useRef({ onHuman, onClear, onError, navigate });
  callbacks.current = { onHuman, onClear, onError, navigate };
  useEffect(() => {
    const match = /^\/runs\/([\w-]+)$/.exec(pathname);
    if (match) setRunId(match[1]);
  }, [pathname, setRunId]);
  useEffect(() => {
    let disposed = false,
      finished = false,
      attempt = 0;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const abort = new AbortController();
    pending.current = null;
    setHuman(null);
    callbacks.current.onClear();
    if (!runId || !profileId) return;
    function connect() {
      if (disposed || finished) return;
      const ws = new WebSocket(
        websocketUrl(
          withOwner(`/agent/runs/${encodeURIComponent(runId)}/ws`, profileId),
        ),
      );
      socket.current = ws;
      ws.onopen = () => {
        attempt = 0;
      };
      ws.onmessage = (event) => {
        if (disposed || socket.current !== ws) return;
        try {
          const msg = JSON.parse(event.data) as ServerMessage;
          if (msg.type === "needs_human") {
            const same =
              pending.current?.request_id &&
              pending.current.request_id === msg.request_id;
            pending.current = msg;
            setHuman(msg);
            if (!same) {
              callbacks.current.navigate(`/runs/${encodeURIComponent(runId)}`);
              callbacks.current.onHuman(msg);
            }
          } else if (
            msg.type === "done" ||
            (msg.type === "status" &&
              !["needs_human", "awaiting_approval"].includes(msg.status))
          ) {
            pending.current = null;
            setHuman(null);
            callbacks.current.onClear();
            if (
              msg.type === "done" ||
              ["done", "failed", "aborted"].includes(msg.status)
            ) {
              finished = true;
              setRunId("");
              ws.close();
            }
          } else if (msg.type === "error") {
            callbacks.current.onError(msg.message);
            if (msg.message.includes("not live")) {
              finished = true;
              setRunId("");
              ws.close();
            }
          }
        } catch {
          callbacks.current.onError("Could not read an application update.");
        }
      };
      ws.onclose = () => {
        if (!disposed && !finished)
          retry = setTimeout(connect, Math.min(1000 * 2 ** attempt++, 15000));
      };
    }
    void request<RunOut>(
      withOwner(`/agent/runs/${encodeURIComponent(runId)}`, profileId),
      { signal: abort.signal },
    )
      .then((run) => {
        if (disposed) return;
        if (["done", "failed", "aborted"].includes(run.status)) {
          setRunId("");
          return;
        }
        callbacks.current.navigate(`/runs/${encodeURIComponent(runId)}`);
        connect();
      })
      .catch((error: Error) => {
        if (!disposed) callbacks.current.onError(error.message);
      });
    return () => {
      disposed = true;
      abort.abort();
      clearTimeout(retry);
      socket.current?.close();
      socket.current = null;
    };
  }, [profileId, runId, setRunId]);
  function send(message: ClientMessage, requestId?: string) {
    if (
      socket.current?.readyState !== WebSocket.OPEN ||
      !pending.current ||
      (requestId && pending.current.request_id !== requestId)
    )
      return false;
    socket.current.send(
      JSON.stringify({ ...message, request_id: pending.current.request_id }),
    );
    pending.current = null;
    setHuman(null);
    callbacks.current.onClear();
    return true;
  }
  return { human, pending, send };
}
