import { Text } from "../context";
import { useEffect, useState, useRef } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { request, post, safeUrl } from "../api/client";
import type { ExplainOut, RunOut, SchemeDetail } from "../api/types";
import { useApp } from "../context";
import { ErrorBox, Explanation, Loading, Markdown } from "../components";
import { Bot, Landmark, Mic, Volume2 } from "lucide-react";
import { Card, PillButton, SourceLink } from "../ui";
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
      setPortal("");
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
  async function run(useAnother = false) {
    retryAction.current = () => void run(useAnother);
    if (!profileId) {
      navigate("/profile");
      return;
    }
    if (useAnother && !safeUrl(portal)) return;
    setBusy("run");
    setError("");
    try {
      const resolved = useAnother
        ? portal
        : (await request<{ portal_url: string }>(
            `/schemes/${encodeURIComponent(slug)}/application-url`,
          )).portal_url;
      const out = await post<RunOut>("/agent/runs", {
        profile_id: profileId,
        portal_url: resolved,
        goal: `Apply for ${scheme?.name || slug}`,
        scheme_slug: slug,
      });
      navigate("/runs/" + encodeURIComponent(out.id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  const fallbackTitle = slug
    .replace(/[-_]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
  return (
    <>
      {loading && (
        <>
          <Card tint="peach" className="mb-6 flex flex-col gap-3">
            <Link
              to="/schemes"
              className="inline-flex min-h-11 items-center self-start font-semibold"
            >
              <Text value={"← My schemes"} />
            </Link>
            <p className="m-0 inline-flex items-center gap-1.5 self-start rounded-full bg-white px-3 py-1 text-xs font-semibold text-ink-soft">
              <Landmark size={14} aria-hidden="true" className="shrink-0" />
              GOVERNMENT SCHEME
            </p>
            <h1>{fallbackTitle || "Scheme details"}</h1>
          </Card>
          <Loading message="Loading benefits, eligibility and official application steps…" />
        </>
      )}
      {error && <ErrorBox error={error} retry={() => retryAction.current()} />}{" "}
      {scheme && (
        <>
          <Card tint="peach" className="mb-6 flex flex-col gap-3">
            <Link to="/schemes" className="inline-flex min-h-11 items-center self-start font-semibold">
              <Text value={"← My schemes"} />
            </Link>
            <p className="m-0 inline-flex items-center gap-1.5 self-start rounded-full bg-white px-3 py-1 text-xs font-semibold text-ink-soft">
              <Landmark size={14} aria-hidden="true" className="shrink-0" />
              {scheme.ministry || scheme.state || "GOVERNMENT SCHEME"}
            </p>
            <h1>{scheme.name}</h1>
            <p className="m-0 max-w-[65ch]">{scheme.brief}</p>
            <div><SourceLink url={scheme.source_url}>
              <Text value={"Read official source ↗"} />
            </SourceLink></div>
            <div className="mt-1 flex flex-wrap items-center justify-between gap-3 border-t border-[#f3d2b8] pt-4">
              <div className="flex flex-wrap gap-2.5">
                <PillButton
                  tone="saffron"
                  onClick={() => void run()}
                  disabled={!!busy}
                >
                  <Bot size={18} aria-hidden="true" className="shrink-0" />
                  <Text value={"Apply for me"} />
                </PillButton>
                <PillButton disabled={!!busy} onClick={explain}>
                  <Volume2 size={18} aria-hidden="true" className="shrink-0" />
                  <Text
                    value={busy === "explain" ? "Explaining…" : "Explain to me"}
                  />
                </PillButton>
              </div>
              <PillButton
                tone="light"
                onClick={() =>
                  window.dispatchEvent(
                    new CustomEvent("buddy:prompt", {
                      detail: {
                        text: `Am I eligible for ${scheme.name}? Summarize its benefits aloud.`,
                      },
                    }),
                  )
                }
              >
                <Mic size={16} aria-hidden="true" className="shrink-0 text-saffron-text" />
                <Text value="Ask Buddy to summarize aloud" />
              </PillButton>
            </div>
          </Card>
          {busy === "explain" && (
            <Loading message="Reading the official scheme and preparing your explanation…" />
          )}
          {busy === "run" && (
            <Loading message="Opening the portal and starting your assisted application…" />
          )}
          <button
            type="button"
            className="mb-4 !bg-transparent !text-sm !text-ink-soft underline"
            onClick={() => setApply(!apply)}
            aria-expanded={apply}
            disabled={!!busy}
          >
            <Text value="Use another official portal" />
          </button>
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
                  <Link to="/profile" className="inline-flex min-h-11 items-center font-semibold">
                    <Text value={"Create a profile first →"} />
                  </Link>
                </p>
              ) : (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void run(true);
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
                  <p>{goal}</p>
                  <button disabled={!!busy || !safeUrl(portal)}>
                    <Text
                      value={busy === "run" ? "Starting…" : "Start application"}
                    />
                  </button>
                </form>
              )}
            </section>
          )}
          <div
            className="tabs flex gap-2 overflow-x-auto pb-1"
            role="tablist"
            aria-label="Scheme information"
          >
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
          <div role="tabpanel" id="scheme-tab" aria-labelledby={"tab-" + tab.replaceAll(" ", "-")}>
          <Card className="mb-6">
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
                      <SourceLink url={a.url}>
                        <Text value={"Open application portal ↗"} />
                      </SourceLink>
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
          </Card>
          </div>
          {explanation && <Explanation data={explanation} />}
        </>
      )}
    </>
  );
}
