import { Text } from "../context";
import { useEffect, useState, useRef } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { request, post, safeUrl } from "../api/client";
import type { ExplainOut, RunOut, SchemeDetail } from "../api/types";
import { useApp } from "../context";
import { ErrorBox, Explanation, Loading, Markdown } from "../components";
export default function Scheme() {
  const { slug = "" } = useParams(),
    { lang, profileId } = useApp(),
    navigate = useNavigate();
  const [scheme, setScheme] = useState<SchemeDetail | null>(null),
    [tab, setTab] = useState("Benefits"),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(""),
    [explanation, setExplanation] = useState<ExplainOut | null>(null),
    [apply, setApply] = useState(false),
    [portal, setPortal] = useState(""),
    [goal, setGoal] = useState("");
  const retryAction = useRef<() => void>(() => {});
  async function load() {
    retryAction.current = () => void load();
    setLoading(true);
    setError("");
    setScheme(null);
    setExplanation(null);
    setApply(false);
    try {
      const out = await request<SchemeDetail>(
        `/schemes/${encodeURIComponent(slug)}?lang=${lang === "hi" ? "hi" : "en"}`,
      );
      setScheme(out);
      setGoal(`Apply for ${out.name}`);
      setPortal(out.application.find((a) => a.url)?.url || "");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, [slug, lang]);
  async function explain() {
    retryAction.current = () => void explain();
    setBusy("explain");
    setError("");
    try {
      setExplanation(
        await post<ExplainOut>("/explain", {
          source: { type: "scheme", slug },
          language: lang,
          profile_id: profileId || null,
          with_audio: true,
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function run() {
    retryAction.current = () => void run();
    if (!safeUrl(portal) || !profileId) return;
    setBusy("run");
    setError("");
    try {
      const out = await post<RunOut>("/agent/runs", {
        profile_id: profileId,
        portal_url: portal,
        goal: goal.trim(),
        scheme_slug: slug,
      });
      navigate("/runs/" + encodeURIComponent(out.id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  if (loading) return <Loading />;
  return (
    <>
      {error && <ErrorBox error={error} retry={() => retryAction.current()} />}{" "}
      {scheme && (
        <>
          <div className="page-heading">
            <Link to="/schemes">
              <Text value={"← My schemes"} />
            </Link>
            <p className="eyebrow">
              {scheme.ministry || scheme.state || "GOVERNMENT SCHEME"}
            </p>
            <h1>{scheme.name}</h1>
            <p>{scheme.brief}</p>
            <a
              href={safeUrl(scheme.source_url)}
              target="_blank"
              rel="noreferrer"
            >
              <Text value={"Read official source ↗"} />
            </a>
            <div className="actions">
              <button disabled={!!busy} onClick={explain}>
                <Text
                  value={busy === "explain" ? "Explaining…" : "Explain to me"}
                />
              </button>
              <button
                className="secondary"
                onClick={() => setApply(!apply)}
                disabled={!!busy}
              >
                <Text value={"Apply for me"} />
              </button>
            </div>
          </div>
          {busy === "explain" && <Loading message="Explaining…" />}
          {apply && (
            <section className="panel">
              <h2>
                <Text value={"Choose the application portal"} />
              </h2>
              <p>
                <Text
                  value={
                    "The assistant will fill the application while you watch. You approve the final submission."
                  }
                />
              </p>
              {!profileId ? (
                <p>
                  <Link to="/">
                    <Text value={"Create a profile first →"} />
                  </Link>
                </p>
              ) : (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void run();
                  }}
                >
                  {scheme.application.filter((a) => a.url).length > 0 && (
                    <label>
                      <Text value={"Official application options"} />
                      <select
                        onChange={(e) => setPortal(e.target.value)}
                        value={
                          scheme.application.some((a) => a.url === portal)
                            ? portal
                            : ""
                        }
                      >
                        <option value="">
                          <Text value={"Enter another portal below"} />
                        </option>
                        {scheme.application
                          .filter((a) => a.url)
                          .map((a, i) => (
                            <option key={i} value={a.url!}>
                              {a.mode} — {a.url}
                            </option>
                          ))}
                      </select>
                    </label>
                  )}
                  <label htmlFor="portal">
                    <Text value={"Portal URL"} />
                  </label>
                  <input
                    id="portal"
                    type="url"
                    required
                    value={portal}
                    onChange={(e) => setPortal(e.target.value)}
                    placeholder="https://…"
                  />
                  <label htmlFor="application-goal">What should the assistant do?</label>
                  <textarea
                    id="application-goal"
                    required
                    value={goal}
                    onChange={(e) => setGoal(e.target.value)}
                    disabled={!!busy}
                  />
                  <button disabled={!!busy || !safeUrl(portal) || !goal.trim()}>
                    <Text
                      value={busy === "run" ? "Starting…" : "Start application"}
                    />
                  </button>
                </form>
              )}
            </section>
          )}
          <div className="tabs" role="tablist" aria-label="Scheme information">
            {[
              "Benefits",
              "Eligibility",
              "Documents",
              "How to apply",
              "FAQs",
            ].map((s) => (
              <button
                role="tab"
                aria-selected={tab === s}
                aria-controls="scheme-tab"
                id={"tab-" + s.replaceAll(" ", "-")}
                key={s}
                onClick={() => setTab(s)}
                tabIndex={tab === s ? 0 : -1}
                onKeyDown={(e) => {
                  const buttons = Array.from(
                    e.currentTarget.parentElement!.querySelectorAll("button"),
                  );
                  const index = buttons.indexOf(e.currentTarget);
                  const next =
                    e.key === "ArrowRight"
                      ? (index + 1) % buttons.length
                      : e.key === "ArrowLeft"
                        ? (index + buttons.length - 1) % buttons.length
                        : e.key === "Home"
                          ? 0
                          : e.key === "End"
                            ? buttons.length - 1
                            : -1;
                  if (next >= 0) {
                    e.preventDefault();
                    buttons[next].click();
                    buttons[next].focus();
                  }
                }}
              >
                <Text value={s} />
              </button>
            ))}
          </div>
          <section
            className="panel"
            role="tabpanel"
            id="scheme-tab"
            aria-labelledby={"tab-" + tab.replaceAll(" ", "-")}
          >
            {tab === "Benefits" ? (
              <>
                <Markdown text={scheme.details_md} />
                <h2>
                  <Text value={"Benefits"} />
                </h2>
                <Markdown text={scheme.benefits_md} />
              </>
            ) : tab === "Eligibility" ? (
              <>
                <Markdown text={scheme.eligibility_md} />
                {scheme.exclusions_md && (
                  <>
                    <h3>
                      <Text value={"Exclusions"} />
                    </h3>
                    <Markdown text={scheme.exclusions_md} />
                  </>
                )}
              </>
            ) : tab === "Documents" ? (
              <Markdown text={scheme.documents_md} />
            ) : tab === "How to apply" ? (
              scheme.application.length ? (
                scheme.application.map((a, i) => (
                  <section key={i}>
                    <h2>{a.mode}</h2>
                    <Markdown text={a.steps_md} />
                    {a.url && (
                      <a href={safeUrl(a.url)} target="_blank" rel="noreferrer">
                        <Text value={"Open application portal ↗"} />
                      </a>
                    )}
                  </section>
                ))
              ) : (
                <p>
                  <Text value={"No application steps available."} />
                </p>
              )
            ) : scheme.faqs.length ? (
              scheme.faqs.map((faq, i) => (
                <details key={i}>
                  <summary>
                    {String(faq.question ?? faq.q ?? "Question")}
                  </summary>
                  <Markdown
                    text={String(faq.answer ?? faq.a ?? "No answer available.")}
                  />
                </details>
              ))
            ) : (
              <p>
                <Text value={"No frequently asked questions available."} />
              </p>
            )}
          </section>
          {explanation && <Explanation data={explanation} />}
        </>
      )}
    </>
  );
}
