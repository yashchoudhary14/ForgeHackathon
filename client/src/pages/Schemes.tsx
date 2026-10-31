import { Text } from "../context";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Search } from "lucide-react";
import { post, request } from "../api/client";
import type { MatchResult, SearchOut } from "../api/types";
import { useApp } from "../context";
import { Citations, Empty, ErrorBox, Loading } from "../components";
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
  async function load() {
    if (!profileId) return;
    setBusy(true);
    setError("");
    setMode("match");
    try {
      setMatches(
        await post<MatchResult[]>("/schemes/match", {
          profile_id: profileId,
          limit: 8,
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    void load();
  }, [profileId]);
  async function search(from = 0) {
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
  const verdicts = {
    eligible: "Eligible",
    likely: "Likely eligible",
    not_eligible: "Not eligible",
    unknown: "Need more information",
  };
  return (
    <>
      <div className="page-heading">
        <span className="eyebrow">
          <Text value={"DISCOVER / सरकारी योजनाएँ"} />
        </span>
        <h1>{t.schemes}</h1>
        <p className="muted">
          <Text
            value={
              "Find support for your next step, with reasons from official sources."
            }
          />
        </p>
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
      {busy ? (
        <Loading
          message={
            mode === "match"
              ? "Checking your profile against official scheme rules…"
              : "Searching official government schemes…"
          }
        />
      ) : mode === "match" ? (
        !profileId ? (
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
        ) : matches.length === 0 && !error ? (
          <Empty>
            <Text
              value={
                "No matching schemes were returned. Update your profile or search above."
              }
            />
          </Empty>
        ) : (
          <div className="cards">
            {matches.map((m) => (
              <article className="panel" key={m.scheme.slug}>
                <div className="card-top">
                  <div>
                    <small>{m.scheme.ministry || m.scheme.state}</small>
                    <h2>
                      <Link
                        to={"/schemes/" + encodeURIComponent(m.scheme.slug)}
                      >
                        {m.scheme.name}
                      </Link>
                    </h2>
                  </div>
                  <span className={"badge " + m.verdict}>
                    <Text value={verdicts[m.verdict]} />
                  </span>
                </div>
                <p>{m.scheme.brief}</p>
                <label>
                  <Text value={"Match confidence ·"} />{" "}
                  {Math.round(Math.max(0, Math.min(1, m.confidence)) * 100)}%
                  <progress
                    value={Math.max(0, Math.min(1, m.confidence))}
                    max={1}
                  />
                </label>
                <details open>
                  <summary>
                    <Text value={"Why this matches you"} />
                  </summary>
                  {m.reasons.map((r, i) => (
                    <div key={i}>
                      <p>
                        <span
                          aria-label={
                            r.met === true
                              ? "Met"
                              : r.met === false
                                ? "Not met"
                                : "Unknown"
                          }
                        >
                          {r.met === true ? "✓" : r.met === false ? "✗" : "?"}
                        </span>{" "}
                        {r.claim}
                      </p>
                      {r.citation && <Citations items={[r.citation]} />}
                    </div>
                  ))}
                </details>
                {m.documents_needed.length > 0 && (
                  <>
                    <h3>
                      <Text value={"Documents you’ll need"} />
                    </h3>
                    <ul>
                      {m.documents_needed.map((d) => (
                        <li key={d}>• {d}</li>
                      ))}
                    </ul>
                  </>
                )}
                {m.missing_info.length > 0 && (
                  <p className="muted">
                    <Text value={"More information needed:"} />
                    {m.missing_info.join(", ")}.{" "}
                    <Link to="/">
                      <Text value={"Update profile"} />
                    </Link>
                  </p>
                )}
                <Link to={"/schemes/" + encodeURIComponent(m.scheme.slug)}>
                  <Text value={"See benefits & apply →"} />
                </Link>
              </article>
            ))}
          </div>
        )
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
