import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ArrowLeftRight, FileUp, Link2 } from "lucide-react";
import { request } from "../api/client";
import type {
  CompareIn,
  DocumentOut,
  ExplainOut,
  ExplainSource,
  FeedItem,
} from "../api/types";
import { ErrorBox, Explanation, Loading } from "../components";
import { Text, useApp } from "../context";
import { Card, EmptyState, Eyebrow, PillButton, SourceLink } from "../ui";

export default function Explain() {
  const { profileId, lang, t } = useApp();
  const [searchParams] = useSearchParams();
  const schemeSlug = searchParams.get("scheme") || "";
  const [inputTab, setInputTab] = useState<"upload" | "compare">("upload");
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [docs, setDocs] = useState<DocumentOut[]>([]);
  const [url, setUrl] = useState("");
  const [data, setData] = useState<ExplainOut | null>(null);
  const [docA, setDocA] = useState("");
  const [docB, setDocB] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedBusy, setFeedBusy] = useState(true);
  const [feedError, setFeedError] = useState("");
  const [error, setError] = useState("");
  const [lastAction, setLastAction] = useState<(() => Promise<void>) | null>(
    null,
  );
  const explainController = useRef<AbortController | null>(null);

  const feedLang = lang === "hi" ? "hi" : "en";
  const getDocs = (signal?: AbortSignal) =>
    request<DocumentOut[]>("/documents?limit=20", { signal })
      .then((list) => {
        setDocs(list);
        if (list.length >= 2) {
          setDocA((a) => a || list[0].id);
          setDocB((b) => b || list[1].id);
        }
      })
      .catch(() => {});

  async function getFeed(signal?: AbortSignal) {
    setFeedBusy(true);
    setFeedError("");
    try {
      const items = await request<FeedItem[]>(`/feed?lang=${feedLang}`, {
        signal,
      });
      if (!signal?.aborted) setFeed(items);
    } catch (e) {
      if (!signal?.aborted) setFeedError((e as Error).message);
    } finally {
      if (!signal?.aborted) setFeedBusy(false);
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    void getFeed(controller.signal);
    void getDocs(controller.signal);
    return () => controller.abort();
  }, [feedLang]);

  useEffect(() => {
    if (schemeSlug) {
      void runExplain({ type: "scheme", slug: schemeSlug });
    }
    return () => explainController.current?.abort();
  }, [schemeSlug]);

  async function runExplain(source: ExplainSource) {
    explainController.current?.abort();
    const controller = new AbortController();
    explainController.current = controller;
    setLastAction(() => () => runExplain(source));
    setBusy(true);
    setError("");
    try {
      const result = await request<ExplainOut>("/explain", {
        method: "POST",
        body: JSON.stringify({
          source,
          profile_id: profileId || null,
          language: lang,
          with_audio: true,
        }),
        signal: controller.signal,
      });
      if (!controller.signal.aborted) setData(result);
    } catch (e) {
      if (!controller.signal.aborted) setError((e as Error).message);
    } finally {
      if (explainController.current === controller) setBusy(false);
    }
  }

  async function runCompare() {
    if (!docA || !docB || docA === docB) return;
    explainController.current?.abort();
    const controller = new AbortController();
    explainController.current = controller;
    setLastAction(() => () => runCompare());
    setBusy(true);
    setError("");
    try {
      // Server compares old (docB) against new (docA) and returns quoted changes.
      const result = await request<ExplainOut>("/explain/compare", {
        method: "POST",
        body: JSON.stringify({
          old: { type: "document", document_id: docB },
          new: { type: "document", document_id: docA },
          profile_id: profileId || null,
          language: lang,
          with_audio: true,
        } satisfies CompareIn),
        signal: controller.signal,
      });
      if (!controller.signal.aborted) {
        setData(result);
      }
    } catch (e) {
      if (!controller.signal.aborted) setError((e as Error).message);
    } finally {
      if (explainController.current === controller) setBusy(false);
    }
  }

  async function upload(file?: File) {
    if (!file && !url.trim()) return;
    const chosenUrl = url.trim();
    explainController.current?.abort();
    const controller = new AbortController();
    explainController.current = controller;
    setLastAction(() => () => upload(file));
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      if (file) form.append("file", file);
      else form.append("url", chosenUrl);
      const doc = await request<DocumentOut>("/documents", {
        method: "POST",
        body: form,
        signal: controller.signal,
      });
      await getDocs(controller.signal);
      setUrl("");
      const result = await request<ExplainOut>("/explain", {
        method: "POST",
        body: JSON.stringify({
          source: { type: "document", document_id: doc.id },
          profile_id: profileId || null,
          language: lang,
          with_audio: true,
        }),
        signal: controller.signal,
      });
      if (!controller.signal.aborted) setData(result);
    } catch (e) {
      if (!controller.signal.aborted) setError((e as Error).message);
    } finally {
      if (explainController.current === controller) setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <Eyebrow>Understand · आसान भाषा में समझें</Eyebrow>
        <h1>
          <Text value="Make sense of government notices, one clear explanation at a time." />
        </h1>
        <p className="m-0 text-ink-soft">
          <Text value="Upload a circular, PDF or photo, paste a government URL, or compare a new circular against an older one." />
        </p>
      </div>

      <Card className="flex flex-col gap-4">
        <div
          role="tablist"
          aria-label="Explain input mode"
          className="flex flex-wrap gap-2 border-b border-line pb-3"
        >
          {(
            [
              {
                id: "upload",
                label: "Upload PDF / Photo",
                Icon: FileUp,
              },
              {
                id: "compare",
                label: "Compare Old vs New Circular",
                Icon: ArrowLeftRight,
              },
            ] as const
          ).map(({ id, label, Icon }) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={inputTab === id}
              onClick={() => setInputTab(id)}
              className={
                "inline-flex !min-h-11 items-center gap-2 !rounded-full !px-4 !py-2 text-xs font-semibold " +
                (inputTab === id
                  ? "!bg-ink !text-paper"
                  : "secondary !bg-paper !text-ink")
              }
            >
              <Icon size={16} aria-hidden="true" />
              <span>{label}</span>
            </button>
          ))}
        </div>

        {inputTab === "upload" && (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="flex flex-col justify-between gap-3 rounded-2xl border border-dashed border-[#d9cfc0] bg-paper p-5">
              <div>
                <span className="mb-3 grid h-11 w-11 place-items-center rounded-2xl bg-peach text-saffron-text">
                  <FileUp
                    size={24}
                    strokeWidth={1.75}
                    aria-hidden="true"
                    className="shrink-0"
                  />
                </span>
                <Eyebrow>Upload a PDF or image</Eyebrow>
                <strong className="font-serif text-2xl font-normal">
                  <Text value="Upload a PDF or image" />
                </strong>
                <p className="m-0 mt-1 text-sm text-ink-soft">
                  Gazette notification, rejection letter, circular or scheme
                  order
                </p>
              </div>
              <label className="inline-flex min-h-12 cursor-pointer items-center gap-2 self-start rounded-full bg-ink px-5 text-sm font-semibold text-paper">
                <FileUp size={18} aria-hidden="true" />
                Choose PDF or image
                <input
                  type="file"
                  accept=".pdf,image/*"
                  disabled={busy}
                  className="sr-only"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) void upload(file);
                    e.currentTarget.value = "";
                  }}
                />
              </label>
            </div>

            <div className="flex flex-col justify-between gap-3 rounded-2xl bg-paper p-5">
              <div>
                <Eyebrow>Or paste a government document URL</Eyebrow>
                <label className="m-0">
                  <span className="sr-only">Government document URL</span>
                  <input
                    value={url}
                    disabled={busy}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="https://pib.gov.in/..."
                  />
                </label>
              </div>
              <div className="flex flex-wrap gap-2">
                <PillButton
                  type="button"
                  disabled={busy || !url.trim()}
                  onClick={() =>
                    void runExplain({ type: "url", url: url.trim() })
                  }
                >
                  <Link2 size={16} aria-hidden="true" className="shrink-0" />{" "}
                  <Text value="Explain URL" />
                </PillButton>
                <PillButton
                  type="button"
                  tone="light"
                  disabled={busy || !url.trim()}
                  onClick={() => void upload()}
                >
                  <Text value="Save to my documents & explain" />
                </PillButton>
              </div>
            </div>
          </div>
        )}

        {inputTab === "compare" && (
          <div className="flex flex-wrap items-end justify-between gap-3 rounded-2xl bg-peach p-5">
            {docs.length >= 2 ? (
              <>
                <div className="flex flex-1 flex-wrap gap-3">
                  <label className="m-0 min-w-[200px] flex-1 text-xs font-semibold">
                    New document / circular (Now · अब)
                    <select
                      value={docA}
                      disabled={busy}
                      onChange={(e) => setDocA(e.target.value)}
                      className="!mt-1 !min-h-11"
                    >
                      {docs.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.title}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="m-0 min-w-[200px] flex-1 text-xs font-semibold">
                    Previous circular to compare (Before · पहले)
                    <select
                      value={docB}
                      disabled={busy}
                      onChange={(e) => setDocB(e.target.value)}
                      className="!mt-1 !min-h-11"
                    >
                      {docs.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.title}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <button
                  type="button"
                  disabled={busy || !docA || !docB || docA === docB}
                  onClick={() => void runCompare()}
                  className="!bg-saffron-text !text-white"
                >
                  <ArrowLeftRight size={16} aria-hidden="true" />
                  Compare · पुराने सर्कुलर से तुलना करें
                </button>
              </>
            ) : (
              <p className="m-0 text-sm text-ink-soft">
                Upload at least two circulars in the Upload tab to compare what
                changed between the old and new versions.
              </p>
            )}
          </div>
        )}

      </Card>

      {error && (
        <ErrorBox
          error={error}
          retry={lastAction ? () => void lastAction() : undefined}
        />
      )}
      {busy && (
        <Loading message="Reading the document and writing a plain-language explanation…" />
      )}
      {data && !busy && <Explanation data={data} />}

      <div className="grid items-start gap-5 lg:grid-cols-2">
        {docs.length > 0 && (
          <section className="flex flex-col gap-3">
            <Eyebrow>Your uploaded documents</Eyebrow>
            <h2 className="m-0 font-serif text-2xl font-normal">
              <Text value="Your uploaded documents" />
            </h2>
            <div className="flex flex-col gap-2.5">
              {docs.map((d) => (
                <Card
                  key={d.id}
                  className="flex flex-wrap items-center justify-between gap-2 !rounded-2xl !p-4"
                >
                  <div>
                    <h3 className="m-0 font-serif text-xl font-normal">{d.title}</h3>
                    <small>
                      {d.source_type} · {d.pages} <Text value="pages" /> · {d.chunks}{" "}
                      <Text value="chunks" />
                    </small>
                  </div>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      void runExplain({ type: "document", document_id: d.id })
                    }
                    className="!min-h-11 !px-4 !py-1.5 text-sm"
                  >
                    {t.explain}
                  </button>
                </Card>
              ))}
            </div>
          </section>
        )}

        <section className="flex flex-col gap-3">
          <Eyebrow>From official sources · PIB &amp; eGazette</Eyebrow>
          <h2 className="m-0 font-serif text-2xl font-normal">
            <Text value="Latest government updates" />
          </h2>
          {feedError ? (
            <ErrorBox error={feedError} retry={() => void getFeed()} />
          ) : feedBusy ? (
            <Loading />
          ) : feed.length > 0 ? (
            <div className="flex flex-col gap-2.5">
              {feed.map((f, i) => (
                <Card key={i} className="flex flex-col gap-2 !rounded-2xl !p-4">
                  <span className="eyebrow">
                    {f.source}
                    {f.ministry ? ` · ${f.ministry}` : ""}
                    {f.published ? ` · ${f.published}` : ""}
                  </span>
                  <h3 className="m-0 font-serif text-xl font-normal">{f.title}</h3>
                  <div className="flex flex-wrap items-center gap-3 pt-1">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void runExplain({ type: "url", url: f.url })}
                      className="!min-h-11 !px-4 !py-1.5 text-sm"
                    >
                      <Text value="Explain this update" />
                    </button>
                    <SourceLink url={f.url} />
                  </div>
                </Card>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No updates available"
              action={
                <button
                  type="button"
                  className="secondary"
                  onClick={() => void getFeed()}
                >
                  <Text value="Refresh" />
                </button>
              }
            >
              Check back shortly for the latest PIB releases.
            </EmptyState>
          )}
        </section>
      </div>
    </div>
  );
}
