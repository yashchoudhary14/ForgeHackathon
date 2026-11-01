import { Text } from "../context";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Search } from "lucide-react";
import { request, streamMatches } from "../api/client";
import { applyMatchEvent } from "../api/match-state";
import type { MatchResult, SearchOut } from "../api/types";
import { useApp } from "../context";
import { Empty, ErrorBox, Loading } from "../components";
import { MatchCards, MatchStats } from "./SchemeCards";
import { AlertsPanel } from "./Alerts";
import { Card, Eyebrow } from "../ui";
export default function Schemes() {
  const { profileId, t, lang } = useApp();
  const [matches, setMatches] = useState<MatchResult[]>([]),
    [results, setResults] = useState<SearchOut | null>(null),
    [keyword, setKeyword] = useState(""),
    [state, setState] = useState(""),
    [offset, setOffset] = useState(0),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [mode, setMode] = useState<"match" | "search">("match");
  const activeMatch = useRef<AbortController | null>(null);
  const [progress, setProgress] = useState("");
  async function load() {
    activeMatch.current?.abort();
    if (!profileId) {
      setMatches([]);
      setProgress("");
      setBusy(false);
      return;
    }
    const controller = new AbortController();
    activeMatch.current = controller;
    setBusy(true);
    setError("");
    setMatches([]);
    setProgress("Checking your profile against official scheme rules…");
    setMode("match");
    try {
      await streamMatches(
        { profile_id: profileId, limit: 8 },
        (event) => {
          if (controller.signal.aborted) return;
          if (event.type === "progress") setProgress(event.message);
          setMatches((current) => applyMatchEvent(current, event));
        },
        controller.signal,
      );
    } catch (e) {
      if (!controller.signal.aborted) setError((e as Error).message);
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  useEffect(() => {
    void load();
    return () => activeMatch.current?.abort();
  }, [profileId]);
  async function search(from = 0) {
    activeMatch.current?.abort();
    setProgress("");
    setBusy(true);
    setError("");
    setMode("search");
    setOffset(from);
    try {
      setResults(
        await request<SearchOut>(
          "/schemes/search?" +
            new URLSearchParams({
              keyword,
              state,
              offset: String(from),
              size: "10",
            }),
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="mb-6 flex flex-col gap-2">
        <Eyebrow>{t.schemes}</Eyebrow>
        <h1>{t.schemes}</h1>
        <p className="muted m-0">
          <Text
            value={
              "Find support for your next step, with reasons from official sources."
            }
          />
        </p>
      </div>
      <div className="mb-6 grid gap-4 lg:grid-cols-[1fr_340px]">
        <MatchStats matches={matches} />
        <Card>
          <h2 className="mb-2">Alerts</h2>
          <AlertsPanel compact />
        </Card>
      </div>
      <section className="panel">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void search();
          }}
        >
          <label htmlFor="search">
            <Text value={"Search all government schemes"} />
          </label>
          <div className="search">
            <input
              id="search"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder={
                lang === "hi"
                  ? "ज़रूरत या योजना का नाम"
                  : "Search by need or scheme name"
              }
            />
            <label>
              <Text value={"State"} />
              <input
                value={state}
                onChange={(e) => setState(e.target.value)}
                placeholder={lang === "hi" ? "कोई भी राज्य" : "Any state"}
              />
            </label>
            <button disabled={busy}>
              <Search size={18} />
              <Text value={"Search"} />
            </button>
          </div>
        </form>
        {profileId && (
          <button className="secondary" disabled={busy} onClick={load}>
            <Text value={"Show my matches"} />
          </button>
        )}
      </section>
      {error && (
        <ErrorBox
          error={error}
          retry={() => void (mode === "search" ? search(offset) : load())}
        />
      )}{" "}
      {busy && mode === "search" ? (
        <Loading message="Searching official government schemes…" />
      ) : mode === "match" ? (
        <MatchResults
          matches={matches}
          profileId={profileId}
          busy={busy}
          error={error}
          progress={progress}
        />
      ) : (
        <>
          {results && (
            <p className="muted">
              {results.total} <Text value={"schemes found"} />
            </p>
          )}
          {!results?.items.length && !error ? (
            <Empty>
              <Text value={"No schemes found. Try a different search."} />
            </Empty>
          ) : (
            results?.items.map((s) => (
              <article className="panel" key={s.slug}>
                <small>{s.ministry || s.state}</small>
                <h2>
                  <Link to={"/schemes/" + encodeURIComponent(s.slug)}>
                    {s.name}
                  </Link>
                </h2>
                <p>{s.brief}</p>
                <div>
                  {s.tags.map((tag) => (
                    <span className="tool" key={tag}>
                      {tag}
                    </span>
                  ))}
                </div>
              </article>
            ))
          )}
          {results && (
            <div className="actions">
              <button
                className="secondary"
                disabled={offset === 0}
                onClick={() => void search(Math.max(0, offset - 10))}
              >
                <Text value={"Previous"} />
              </button>
              <button
                disabled={offset + results.items.length >= results.total}
                onClick={() => void search(offset + 10)}
              >
                <Text value={"Next"} />
              </button>
            </div>
          )}
        </>
      )}
    </>
  );
}

export function MatchResults({
  matches,
  profileId,
  busy,
  error,
  progress,
}: {
  matches: MatchResult[];
  profileId: string;
  busy: boolean;
  error: string;
  progress: string;
}) {
  return (
    <>
      {progress && (
        <p className="muted" role="status" aria-live="polite">
          {progress}
        </p>
      )}
      {!profileId ? (
        <Empty>
          <p>
            <Text
              value={"Tell us about yourself to see schemes matched to you."}
            />
          </p>
          <Link to="/">
            <Text value={"Create your profile →"} />
          </Link>
        </Empty>
      ) : matches.length === 0 && !error && !busy ? (
        <Empty>
          <Text
            value={
              "No matching schemes were returned. Update your profile or search above."
            }
          />
        </Empty>
      ) : (
        <MatchCards matches={matches} />
      )}
    </>
  );
}
