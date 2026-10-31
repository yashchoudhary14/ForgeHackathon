import { test, after } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

const server = await createServer({
  server: { middlewareMode: true, hmr: false },
  ssr: { resolve: { externalConditions: ["module-sync"] } },
  appType: "custom",
});
after(() => server.close());
const { streamMatches, BASE } =
  await server.ssrLoadModule("/src/api/client.ts");
const { applyMatchEvent } = await server.ssrLoadModule(
  "/src/api/match-state.ts",
);
const { MemoryRouter } = await import("react-router-dom");
const { MatchResults } = await server.ssrLoadModule("/src/pages/Schemes.tsx");
const match = (slug, verdict = "likely", confidence = 0.9) => ({
  scheme: { slug, name: slug, tags: [] },
  verdict,
  confidence,
  reasons: [],
  documents_needed: [],
  missing_info: [],
});
const encode = (event) =>
  new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`);

test("POST delivers fragmented matching events before completion and final list replaces live results", async (t) => {
  let controller;
  const body = new ReadableStream({
    start(value) {
      controller = value;
    },
  });
  const signal = new AbortController().signal;
  t.mock.method(globalThis, "fetch", async (url, init) => {
    assert.equal(url, BASE + "/api/schemes/match/stream");
    assert.equal(init.method, "POST");
    assert.equal(init.headers.Accept, "text/event-stream");
    assert.equal(init.signal, signal);
    assert.deepEqual(JSON.parse(init.body), {
      profile_id: "citizen",
      limit: 2,
    });
    return new Response(body);
  });
  let matches = [],
    progress = "",
    settled = false,
    sawResult;
  const received = new Promise((resolve) => {
    sawResult = resolve;
  });
  const pending = streamMatches(
    { profile_id: "citizen", limit: 2 },
    (event) => {
      if (event.type === "progress") progress = event.message;
      matches = applyMatchEvent(matches, event);
      if (event.type === "result") sawResult();
    },
    signal,
  ).then(() => {
    settled = true;
  });
  controller.enqueue(
    encode({
      type: "progress",
      message: "found 32 schemes",
      checked: 0,
      total: 32,
    }),
  );
  for (const byte of encode({ type: "result", result: match("हिन्दी") }))
    controller.enqueue(new Uint8Array([byte]));
  await received;
  assert.equal(settled, false);
  assert.equal(progress, "found 32 schemes");
  assert.equal(matches[0].scheme.slug, "हिन्दी");
  const final = [match("best", "eligible")];
  controller.enqueue(
    encode({
      type: "progress",
      message: "checked 32/32",
      checked: 32,
      total: 32,
    }),
  );
  controller.enqueue(encode({ type: "done", results: final }));
  await pending;
  assert.equal(progress, "checked 32/32");
  assert.deepEqual(matches, final);
});

test("live matches sort by verdict and confidence, deduplicate, and render before done", () => {
  let matches = [];
  for (const result of [
    match("low", "likely", 0.2),
    match("no", "not_eligible", 1),
    match("yes", "eligible", 0.5),
    match("high", "likely", 0.9),
    match("low", "likely", 0.8),
  ])
    matches = applyMatchEvent(matches, { type: "result", result });
  assert.deepEqual(
    matches.map((m) => m.scheme.slug),
    ["yes", "high", "low", "no"],
  );
  const html = renderToStaticMarkup(
    createElement(
      MemoryRouter,
      null,
      createElement(MatchResults, {
        matches,
        profileId: "citizen",
        busy: true,
        error: "",
        progress: "checked 12/32",
      }),
    ),
  );
  assert.match(html, /role="status" aria-live="polite"/);
  assert.match(html, /checked 12\/32/);
  assert.doesNotMatch(html, /No matching schemes/);
  assert.equal((html.match(/<article /g) || []).length, 4);
  assert.ok(html.indexOf(">yes</a>") < html.indexOf(">high</a>"));
});

test("stream errors and incomplete EOF reject; errors cancel the reader", async (t) => {
  for (const events of [
    [],
    [{ type: "error", message: "Please retry matching." }],
  ]) {
    let cancelled = false;
    t.mock.method(
      globalThis,
      "fetch",
      async () =>
        new Response(
          new ReadableStream({
            start(controller) {
              for (const event of events) controller.enqueue(encode(event));
              if (!events.length) controller.close();
            },
            cancel() {
              cancelled = true;
            },
          }),
        ),
    );
    await assert.rejects(
      streamMatches(
        { profile_id: "p" },
        () => {},
        new AbortController().signal,
      ),
      events.length ? /Please retry/ : /before the answer was complete/,
    );
    if (events.length) assert.equal(cancelled, true);
  }
});

test("profile cancellation interrupts the stream request", async (t) => {
  t.mock.method(
    globalThis,
    "fetch",
    (_url, { signal }) =>
      new Promise((_resolve, reject) => {
        signal.addEventListener("abort", () => reject(signal.reason), {
          once: true,
        });
      }),
  );
  const controller = new AbortController();
  const pending = streamMatches(
    { profile_id: "p" },
    () => {},
    controller.signal,
  );
  controller.abort();
  await assert.rejects(pending, { name: "AbortError" });
});
