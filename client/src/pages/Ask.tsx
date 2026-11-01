import { Text } from "../context";
import { useEffect, useRef, useState } from "react";
import { streamChat } from "../api/client";
import type { Citation } from "../api/types";
import { useApp } from "../context";
import { tt } from "../ui-strings";
import { Citations, Empty, ErrorBox, Markdown, MicButton } from "../components";
type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations: Citation[];
  tools: string[];
};
export default function Ask() {
  const { lang, profileId, t } = useApp();
  const [session] = useState(() => crypto.randomUUID()),
    [messages, setMessages] = useState<Message[]>([]),
    [input, setInput] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [last, setLast] = useState("");
  const abort = useRef<AbortController | null>(null),
    bottom = useRef<HTMLDivElement>(null);
  useEffect(() => () => abort.current?.abort(), []);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages]);
  async function send(text = input) {
    if (!text.trim() || busy) return;
    setInput("");
    setError("");
    setLast(text);
    setBusy(true);
    const id = crypto.randomUUID();
    setMessages((m) => [
      ...m,
      { id: crypto.randomUUID(), role: "user", text, citations: [], tools: [] },
      { id, role: "assistant", text: "", citations: [], tools: [] },
    ]);
    const controller = new AbortController();
    abort.current = controller;
    let timer = window.setTimeout(() => controller.abort(), 60000);
    const touch = () => {
      clearTimeout(timer);
      timer = window.setTimeout(() => controller.abort(), 60000);
    };
    try {
      await streamChat(
        {
          session_id: session,
          message: text,
          language: lang,
          profile_id: profileId || null,
          document_ids: [],
        },
        (event) => {
          touch();
          setMessages((messages) =>
            messages.map((m) =>
              m.id !== id
                ? m
                : event.type === "token"
                  ? { ...m, text: m.text + event.text }
                  : event.type === "citation"
                    ? { ...m, citations: [...m.citations, event.citation] }
                    : event.type === "tool_call"
                      ? {
                          ...m,
                          tools: [
                            ...m.tools,
                            event.name === "search_schemes"
                              ? "Searching schemes…"
                              : event.name.replaceAll("_", " ") + "…",
                          ],
                        }
                      : event.type === "tool_result"
                        ? { ...m, tools: [...m.tools, event.summary] }
                        : m,
            ),
          );
        },
        controller.signal,
      );
    } catch (e) {
      setError(
        controller.signal.aborted
          ? "The answer was interrupted or timed out. You can retry."
          : (e as Error).message,
      );
    } finally {
      clearTimeout(timer);
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <span className="eyebrow">
          <Text value={"ASK / बेझिझक पूछें"} />
        </span>
        <h1>{t.ask}</h1>
        <p className="muted">
          <Text
            value={
              "Questions about schemes, documents, or your next step? Start here."
            }
          />
        </p>
      </div>
      <section className="panel">
        <div className="chat" aria-live="polite" aria-relevant="additions text">
          {messages.length === 0 && (
            <Empty>
              <Text
                value={
                  "Type or speak a question in your language. Answers will include available sources."
                }
              />
            </Empty>
          )}
          {messages.map((m) => (
            <article className={"message " + m.role} key={m.id}>
              <small>
                {m.role === "user" ? <Text value="You" /> : tt(lang, "brandName")}
              </small>
              <div>
                {m.tools.map((tool, i) => (
                  <span className="tool" key={i}>
                    {tool}
                  </span>
                ))}
              </div>
              <Markdown
                text={
                  m.text ||
                  (busy && m.role === "assistant"
                    ? lang === "hi"
                      ? "आपका सवाल पढ़ रहे हैं और आधिकारिक स्रोत जाँच रहे हैं…"
                      : "Reading your question and checking official sources…"
                    : "No answer received.")
                }
              />
              {m.citations.length > 0 && <Citations items={m.citations} />}
            </article>
          ))}
          <div ref={bottom} />
        </div>
        {error && <ErrorBox error={error} retry={() => void send(last)} />}
        <form
          className="chat-form"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <label htmlFor="question">
            <Text value={"Your question"} />
          </label>
          <textarea
            id="question"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            rows={3}
            required
            disabled={busy}
          />
          <div className="actions">
            <button disabled={busy || !input.trim()}>
              {busy ? <Text value="Answering…" /> : t.send}
            </button>
            {busy && (
              <button
                type="button"
                className="secondary"
                onClick={() => abort.current?.abort()}
              >
                <Text value={"Stop"} />
              </button>
            )}
          </div>
        </form>
        <MicButton disabled={busy} onText={setInput} />
      </section>
    </>
  );
}
