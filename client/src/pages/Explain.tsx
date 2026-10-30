import { Text } from "../context";
import { useEffect, useState, useRef } from "react";
import { request, post } from "../api/client";
import type {
  DocumentOut,
  ExplainOut,
  ExplainSource,
  FeedItem,
} from "../api/types";
import { useApp } from "../context";
import { Empty, ErrorBox, Explanation, Loading } from "../components";
export default function Explain() {
  const { lang, profileId, t } = useApp();
  const [url, setUrl] = useState(""),
    [file, setFile] = useState<File | null>(null),
    [documents, setDocuments] = useState<DocumentOut[]>([]),
    [feed, setFeed] = useState<FeedItem[]>([]),
    [data, setData] = useState<ExplainOut | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [feedError, setFeedError] = useState(""),
    [docsError, setDocsError] = useState(""),
    [feedLoading, setFeedLoading] = useState(true);
  const retryAction = useRef<() => void>(() => {});
  async function getFeed(signal?: AbortSignal) {
    setFeedLoading(true);
    setFeedError("");
    try {
      setFeed(await request<FeedItem[]>("/feed", { signal }));
    } catch (e) {
      if (!signal?.aborted) setFeedError((e as Error).message);
    } finally {
      setFeedLoading(false);
    }
  }
  async function getDocuments(signal?: AbortSignal) {
    setDocsError("");
    try {
      setDocuments(await request<DocumentOut[]>("/documents", { signal }));
    } catch (e) {
      if (!signal?.aborted) setDocsError((e as Error).message);
    }
  }
  useEffect(() => {
    const controller = new AbortController();
    void getFeed(controller.signal);
    void getDocuments(controller.signal);
    return () => controller.abort();
  }, []);
  async function explain(source: ExplainSource) {
    retryAction.current = () => void explain(source);
    setBusy(true);
    setError("");
    setData(null);
    try {
      setData(
        await post<ExplainOut>("/explain", {
          source,
          profile_id: profileId || null,
          language: lang,
          with_audio: true,
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function upload() {
    if (!file && !url.trim()) return;
    retryAction.current = () => void upload();
    setBusy(true);
    setError("");
    setData(null);
    try {
      const body = new FormData();
      if (file) body.append("file", file);
      else body.append("url", url);
      const doc = await request<DocumentOut>("/documents", {
        method: "POST",
        body,
      });
      setDocuments((d) => [doc, ...d.filter((x) => x.id !== doc.id)]);
      retryAction.current = () =>
        void explain({ type: "document", document_id: doc.id });
      setData(
        await post<ExplainOut>("/explain", {
          source: { type: "document", document_id: doc.id },
          language: lang,
          profile_id: profileId || null,
          with_audio: true,
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <span className="eyebrow">
          <Text value={"UNDERSTAND / आसान भाषा में"} />
        </span>
        <h1>{t.explain}</h1>
        <p className="muted">
          <Text
            value={
              "Make sense of government notices, one clear explanation at a time."
            }
          />
        </p>
      </div>
      <section className="panel">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void upload();
          }}
        >
          <label htmlFor="document-file">
            <Text value={"Upload a PDF or image"} />
          </label>
          <input
            id="document-file"
            type="file"
            accept="application/pdf,image/*"
            disabled={busy}
            onChange={(e) => {
              setFile(e.target.files?.[0] || null);
              if (e.target.files?.length) setUrl("");
            }}
          />
          <label htmlFor="document-url">
            <Text value={"Or paste a government document URL"} />
          </label>
          <input
            id="document-url"
            type="url"
            value={url}
            disabled={busy || !!file}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://…"
          />
          {file && (
            <button
              className="secondary"
              type="button"
              disabled={busy}
              onClick={() => {
                setFile(null);
                const input = document.getElementById(
                  "document-file",
                ) as HTMLInputElement;
                input.value = "";
              }}
            >
              <Text value={"Clear file"} />
            </button>
          )}
          <div className="actions">
            <button disabled={busy || (!file && !url.trim())}>
              <Text
                value={
                  busy ? "Reading and explaining…" : "Explain this document"
                }
              />
            </button>
          </div>
        </form>
      </section>
      {error && <ErrorBox error={error} retry={() => retryAction.current()} />}{" "}
      {busy && <Loading />}
      {data && <Explanation data={data} />}
      <section className="panel">
        <h2>
          <Text value={"Your uploaded documents"} />
        </h2>
        {docsError ? (
          <ErrorBox error={docsError} retry={getDocuments} />
        ) : documents.length ? (
          documents.map((d) => (
            <button
              disabled={busy}
              className="secondary list-row"
              key={d.id}
              onClick={() =>
                void explain({ type: "document", document_id: d.id })
              }
            >
              {d.title}
              <small>
                {d.pages} <Text value={"pages"} />
              </small>
            </button>
          ))
        ) : (
          <Empty>
            <Text value={"No documents uploaded yet."} />
          </Empty>
        )}
      </section>
      <section className="panel">
        <span className="eyebrow">
          <Text value={"FROM OFFICIAL SOURCES"} />
        </span>
        <h2>
          <Text value={"Latest government updates"} />
        </h2>
        {feedError ? (
          <ErrorBox error={feedError} retry={getFeed} />
        ) : feedLoading ? (
          <Loading />
        ) : feed.length ? (
          feed.map((f, i) => (
            <div className="list-row" key={f.url + i}>
              <small>
                {f.source}
                {f.ministry && ` · ${f.ministry}`}
                {f.published && ` · ${f.published}`}
              </small>
              <h3>{f.title}</h3>
              <button
                className="secondary"
                disabled={busy}
                onClick={() => void explain({ type: "url", url: f.url })}
              >
                <Text value={"Explain this update"} />
              </button>
            </div>
          ))
        ) : (
          <Empty>
            <Text value={"No updates available."} />{" "}
            <button className="secondary" onClick={() => void getFeed()}>
              <Text value={"Refresh"} />
            </button>
          </Empty>
        )}
      </section>
    </>
  );
}
