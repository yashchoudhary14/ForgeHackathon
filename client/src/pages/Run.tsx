import { Text, useApp } from "../context";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { request, websocketUrl, withOwner } from "../api/client";
import { applyRunEvent, isTerminal, mergeRunSnapshot } from "../api/run-state";
import type {
  ClientMessage,
  Human,
  RunOut,
  ServerMessage,
} from "../api/types";
import { ErrorBox, Loading } from "../components";
import HumanStep from "./HumanStep";
import { ReceiptView } from "../ReceiptView";
import { Globe, Monitor, ShieldCheck } from "lucide-react";

const actionLabels: Record<string, string> = {
  click: "Selecting a field or button",
  type: "Filling in your details",
  select: "Choosing an option",
  scroll: "Checking the next section",
  navigate: "Opening a portal page",
  goto: "Opening a portal page",
  wait: "Waiting for the portal",
  ask_human: "Waiting for your help",
  request_approval: "Waiting for your approval",
  done: "Finishing the application",
};
export default function Run() {
  const { id = "" } = useParams();
  const { profileId } = useApp();
  const [run, setRun] = useState<RunOut | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [connection, setConnection] = useState("Connecting"),
    [human, setHuman] = useState<Human | null>(null),
    [answer, setAnswer] = useState(""),
    [typing, setTyping] = useState(""),
    [takeover, setTakeover] = useState(false),
    [hasFrame, setHasFrame] = useState(false),
    [epoch, setEpoch] = useState(0);
  const socket = useRef<WebSocket | null>(null),
    canvas = useRef<HTMLCanvasElement>(null),
    timeline = useRef<HTMLElement>(null),
    humanPanel = useRef<HTMLElement>(null),
    lastFrame = useRef<HTMLImageElement | null>(null),
    frameVersion = useRef(0);
  useEffect(() => {
    let disposed = false,
      retry: ReturnType<typeof setTimeout> | undefined,
      attempts = 0,
      finished = false,
      revision = 0;
    const abort = new AbortController();
    setLoading(true);
    setRun(null);
    setHuman(null);
    setTakeover(false);
    setError("");
    setHasFrame(false);
    lastFrame.current = null;
    frameVersion.current++;
    const connect = () => {
      if (disposed || finished) return;
      setConnection(attempts ? "Reconnecting…" : "Connecting…");
      const ws = new WebSocket(
        websocketUrl(withOwner(`/agent/runs/${encodeURIComponent(id)}/ws`, profileId)),
      );
      const liveSteps = new Set<number>();
      socket.current = ws;
      ws.onopen = () => {
        if (disposed) return;
        if (attempts > 0) {
          const snapshotRevision = revision;
          void request<RunOut>(withOwner(`/agent/runs/${encodeURIComponent(id)}`, profileId), {
            signal: abort.signal,
          })
            .then((snapshot) => {
              if (disposed || socket.current !== ws) return;
              setRun((current) =>
                mergeRunSnapshot(
                  snapshot,
                  current,
                  liveSteps,
                  revision !== snapshotRevision,
                ),
              );
              if (
                isTerminal(snapshot.status) &&
                revision === snapshotRevision
              ) {
                finished = true;
                setHuman(null);
                setTakeover(false);
                setConnection("Finished");
                ws.close();
              }
            })
            .catch(() => {});
        }
        attempts = 0;
        setConnection("Connected");
      };
      ws.onmessage = (e) => {
        if (disposed) return;
        try {
          const msg = JSON.parse(e.data) as ServerMessage;
          if (msg.type !== "frame") {
            if (
              msg.type === "status" ||
              msg.type === "needs_human" ||
              msg.type === "done"
            )
              revision++;
            if (msg.type === "step") liveSteps.add(msg.step.idx);
            setRun((r) => (r ? applyRunEvent(r, msg) : r));
          }
          if (msg.type === "frame") {
            const img = new Image(),
              version = ++frameVersion.current;
            img.onload = () => {
              if (disposed || version !== frameVersion.current) return;
              lastFrame.current = img;
              setHasFrame(true);
              const c = canvas.current;
              if (c) {
                c.width = img.naturalWidth;
                c.height = img.naturalHeight;
                c.getContext("2d")?.drawImage(img, 0, 0);
              }
            };
            img.src = "data:image/jpeg;base64," + msg.jpeg;
          } else if (msg.type === "status") {
            if (
              msg.status !== "needs_human" &&
              msg.status !== "awaiting_approval"
            ) {
              setHuman(null);
              setTakeover(false);
            }
            if (isTerminal(msg.status)) {
              finished = true;
              setHuman(null);
              setTakeover(false);
              setConnection("Finished");
              void request<RunOut>(withOwner(`/agent/runs/${encodeURIComponent(id)}`, profileId), {
                signal: abort.signal,
              })
                .then((r) => {
                  if (!disposed)
                    setRun((current) =>
                      mergeRunSnapshot(r, current, liveSteps, true),
                    );
                })
                .catch(() => {});
              if (msg.status !== "done") ws.close();
            }
          } else if (msg.type === "needs_human") {
            setHuman(msg);
            setAnswer("");
            setTakeover(false);
          } else if (msg.type === "done") {
            finished = true;
            setHuman(null);
            setTakeover(false);
            setConnection("Finished");
            ws.close();
          } else if (msg.type === "error") {
            if (
              msg.message === "run is not live (finished or server restarted)"
            ) {
              finished = true;
              setConnection("Unavailable");
              setError(
                "This live session has ended. Your saved steps are still available. Start a new application from the scheme page when you’re ready.",
              );
              ws.close();
            } else setError(msg.message);
          }
        } catch {
          setError(
            "Could not read a live update. Reconnect to restore the application view.",
          );
        }
      };
      ws.onerror = () => {
        if (!disposed) setConnection("Connection interrupted");
      };
      ws.onclose = () => {
        if (disposed || finished) return;
        setConnection("Disconnected · reconnecting");
        retry = setTimeout(
          () => {
            attempts++;
            connect();
          },
          Math.min(1000 * 2 ** Math.min(attempts, 5), 30000),
        );
      };
    };
    async function start() {
      try {
        const result = await request<RunOut>(
          withOwner(`/agent/runs/${encodeURIComponent(id)}`, profileId),
          { signal: abort.signal },
        );
        if (disposed) return;
        setRun(result);
        finished = isTerminal(result.status);
        setConnection(finished ? "Finished" : "Connecting…");
        setLoading(false);
        if (!finished) connect();
      } catch (e) {
        if (!disposed) {
          setError((e as Error).message);
          setLoading(false);
          setConnection("Unavailable");
        }
      }
    }
    void start();
    return () => {
      disposed = true;
      abort.abort();
      clearTimeout(retry);
      socket.current?.close();
    };
  }, [id, epoch, profileId]);
  useEffect(() => {
    const list = timeline.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [run?.steps]);
  useEffect(() => {
    if (human) {
      humanPanel.current?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        block: "nearest",
      });
      humanPanel.current?.focus({ preventScroll: true });
    }
  }, [human]);
  useEffect(() => {
    const c = canvas.current,
      img = lastFrame.current;
    if (c && img) {
      c.width = img.naturalWidth;
      c.height = img.naturalHeight;
      c.getContext("2d")?.drawImage(img, 0, 0);
    }
  }, [hasFrame]);
  function send(message: ClientMessage) {
    if (socket.current?.readyState !== WebSocket.OPEN) {
      setError(
        "The live connection is unavailable. Wait for reconnection before continuing.",
      );
      return false;
    }
    socket.current.send(JSON.stringify({ ...message, ...(human?.request_id ? { request_id: human.request_id } : {}) }));
    setError("");
    return true;
  }
  function humanAction(type: "resume" | "approve" | "approve_duplicate" | "abort") {
    if (send({ type })) {
      setHuman(null);
      setTakeover(false);
      setAnswer("");
    }
  }
  function takeOver() {
    setTakeover(true);
    canvas.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
    canvas.current?.focus({ preventScroll: true });
  }
  return (
    <>
      <div className="page-heading">
        <Link to="/runs">
          <Text value={"← My applications"} />
        </Link>
        <h1>
          <Text value={"Applying, together."} />
        </h1>
        <p className="muted">
          <Text
            value={
              "Watch each step. Take over when needed. You decide before final submission."
            }
          />
        </p>
      </div>
      {loading && (
        <Loading message="Restoring your application and connecting to the live browser…" />
      )}
      {error && !run ? (
        <section
          role="alert"
          className="mb-6 flex flex-col gap-4 rounded-[28px] border border-[#f3d2b8] bg-peach/70 p-6"
        >
          <div className="flex flex-col gap-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-saffron-text">
              SESSION NOT FOUND · आवेदन सत्र उपलब्ध नहीं
            </span>
            <h2 className="m-0 font-serif text-2xl font-normal text-ink">
              We couldn’t find that live application session
            </h2>
            <p className="m-0 text-sm text-ink-soft">{error}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2.5">
            <Link
              to="/schemes"
              style={{ color: "#17140f" }}
              className="inline-flex min-h-12 items-center gap-2 rounded-full bg-saffron px-5 text-sm font-semibold text-ink no-underline"
            >
              Start a new application →
            </Link>
            <Link
              to="/runs"
              style={{ color: "#17140f" }}
              className="inline-flex min-h-12 items-center gap-2 rounded-full border border-line bg-white px-5 text-sm font-semibold text-ink no-underline"
            >
              View my activity
            </Link>
            <button
              type="button"
              className="secondary !min-h-12 !rounded-full !px-5 text-sm"
              onClick={() => setEpoch((e) => e + 1)}
            >
              <Text value={"Try again"} />
            </button>
          </div>
        </section>
      ) : (
        error && <ErrorBox error={error} retry={() => setEpoch((e) => e + 1)} />
      )}{" "}
      {run && (
        <>
          <div className="card-top">
            <h2>{run.goal}</h2>
            <span className={"badge " + run.status}>
              <Text value={run.status.replaceAll("_", " ")} />
            </span>
          </div>
          <div
            className={
              "connection " + (connection === "Connected" ? "online" : "")
            }
            role="status"
            data-ended={connection === "Finished" || connection === "Unavailable"}
          >
            <Text value={connection} />
          </div>
          {run.error && (
            <ErrorBox error={run.error} retry={() => setEpoch((e) => e + 1)} />
          )}{" "}
          {!isTerminal(run.status) && connection !== "Unavailable" && (
            <div className="run-guidance">
              <ShieldCheck size={20} aria-hidden="true" />
              <p>
                <strong>
                  <Text value="You stay in control" />
                </strong>
                <br />
                <Text value="The agent pauses for CAPTCHA, OTP and your approval before submission." />
              </p>
            </div>
          )}
          {!human &&
            !isTerminal(run.status) &&
            connection !== "Unavailable" && (
              <section className="panel control-status" aria-live="polite">
                <h2>
                  <Text
                    value={
                      run.status === "needs_human" ||
                      run.status === "awaiting_approval"
                        ? "Restoring your next action…"
                        : "No action needed from you yet"
                    }
                  />
                </h2>
                <p>
                  <Text
                    value={
                      run.status === "needs_human" ||
                      run.status === "awaiting_approval"
                        ? "Reconnecting to retrieve the request. If it does not appear, try again."
                        : "Watch the browser and steps below. We’ll show your next action here."
                    }
                  />
                </p>
                {(run.status === "needs_human" ||
                  run.status === "awaiting_approval") && (
                  <button
                    className="secondary"
                    onClick={() => setEpoch((e) => e + 1)}
                  >
                    <Text value="Try again" />
                  </button>
                )}
              </section>
            )}
          {human && (
            <HumanStep
              human={human}
              connected={connection === "Connected"}
              answer={answer}
              setAnswer={setAnswer}
              takeover={takeover}
              onTakeOver={takeOver}
              send={send}
              onDone={humanAction}
            />
          )}
          <div className="run-grid">
            <section className="panel browser-panel">
              <h2>
                <Text value={"Live browser"} />
              </h2>
              <div className="browser-frame" data-takeover={takeover}>
              <div className="browser-address">
                <Globe size={16} aria-hidden="true" className="shrink-0" />
                <span>{run.portal_url}</span>
                <span className={"inline-flex items-center rounded-full px-3 py-1 font-sans text-xs font-semibold " + (takeover ? "bg-lime text-ink" : "bg-act-soft text-[#1f4fa8]")}>
                  <Text
                    value={takeover ? "You are in control" : "Watch live"}
                  />
                </span>
              </div>
              <div className="browser">
                {!hasFrame && (
                  <p className="browser-wait" role="status">
                    <Monitor size={36} aria-hidden="true" />
                    <Text
                      value={
                        isTerminal(run.status) || connection === "Unavailable"
                          ? "This application has ended. Check the steps and receipt below."
                          : "Opening the portal. The live browser will appear here…"
                      }
                    />
                  </p>
                )}
                <canvas
                  ref={canvas}
                  style={{
                    display: hasFrame ? "block" : "none",
                    cursor: takeover ? "crosshair" : "default",
                  }}
                  tabIndex={takeover ? 0 : -1}
                  aria-label="Live government portal. In takeover mode, click to interact and use the typing controls below."
                  onClick={(e) => {
                    if (!takeover) return;
                    const rect = e.currentTarget.getBoundingClientRect();
                    if (rect.width && rect.height)
                      send({
                        type: "click",
                        x: Math.max(
                          0,
                          Math.min(1, (e.clientX - rect.left) / rect.width),
                        ),
                        y: Math.max(
                          0,
                          Math.min(1, (e.clientY - rect.top) / rect.height),
                        ),
                      });
                  }}
                  onKeyDown={(e) => {
                    if (!takeover || e.key === "Tab") return;
                    if (
                      [
                        "Enter",
                        "Backspace",
                        "Escape",
                        "ArrowUp",
                        "ArrowDown",
                        "ArrowLeft",
                        "ArrowRight",
                        "Delete",
                      ].includes(e.key)
                    ) {
                      e.preventDefault();
                      send({ type: "key", key: e.key });
                    } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) {
                      e.preventDefault();
                      send({ type: "type", text: e.key });
                    }
                  }}
                />
              </div>
              </div>
              {takeover && (
                <div className="takeover">
                  <p>
                    <Text
                      value={
                        "You are in control. Click the live browser to choose a field, then type here."
                      }
                    />
                  </p>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (typing && send({ type: "type", text: typing }))
                        setTyping("");
                    }}
                  >
                    <label htmlFor="remote-type">
                      <Text value={"Text for the selected field"} />
                    </label>
                    <input
                      id="remote-type"
                      autoComplete="off"
                      type="password"
                      value={typing}
                      onChange={(e) => setTyping(e.target.value)}
                    />
                    <button disabled={!typing || connection !== "Connected"}>
                      <Text value={"Type into browser"} />
                    </button>
                  </form>
                  <div className="actions">
                    {["Tab", "Enter", "Backspace", "Escape"].map((key) => (
                      <button
                        className="secondary"
                        key={key}
                        disabled={connection !== "Connected"}
                        onClick={() => send({ type: "key", key })}
                      >
                        {key}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </section>
            <section
              className="panel timeline"
              ref={timeline}
              aria-label="Application steps"
              aria-live="polite"
            >
              <h2>
                <Text value={"Step by step"} />
              </h2>
              {run.steps.length === 0 ? (
                <p className="muted">
                  <Text
                    value={"Steps will appear when the assistant begins."}
                  />
                </p>
              ) : (
                <ol>
                  {run.steps.map((step) => (
                    <li key={step.idx}>
                      <small>
                        <Text value={"Step"} /> {step.idx + 1} ·{" "}
                        <Text value={step.status.replaceAll("_", " ")} />
                      </small>
                      {step.thought && <p>{step.thought}</p>}
                      {step.action && (
                        <span className="tool">
                          <Text
                            value={
                              actionLabels[String(step.action.action)] ||
                              "Working on the portal"
                            }
                          />
                        </span>
                      )}
                      {step.result && (
                        <p className="step-result">
                          <Text value="Result:" /> {step.result}
                        </p>
                      )}
                      {step.url && <small>{step.url}</small>}
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </div>
          {run.receipt && (
            <section className="panel">
              <ReceiptView receipt={run.receipt} />
            </section>
          )}
        </>
      )}
    </>
  );
}
