import { test, after } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

const server = await createServer({
  server: { middlewareMode: true },
  appType: "custom",
  optimizeDeps: { noDiscovery: true, include: [] },
});
after(() => server.close());
const { request, assetUrl, BASE, websocketUrl } =
  await server.ssrLoadModule("/src/api/client.ts");
const { ReceiptView } = await server.ssrLoadModule("/src/ReceiptView.tsx");
const { Loading, ErrorBox } = await server.ssrLoadModule("/src/components.tsx");
const { friendlyError, responseError } =
  await server.ssrLoadModule("/src/api/errors.ts");

test("agent websocket uses the configured backend base", () => {
  const expected = new URL(BASE + "/api/agent/runs/demo/ws");
  expected.protocol = expected.protocol === "https:" ? "wss:" : "ws:";
  assert.equal(websocketUrl("/agent/runs/demo/ws"), expected.href);
});

function pendingFetch(t) {
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
  t.mock.timers.enable({ apis: ["setTimeout"] });
}

test("slow government and AI routes survive 90 seconds and stop at 150 seconds", async (t) => {
  pendingFetch(t);
  for (const path of [
    "/schemes/match",
    "/explain",
    "/documents",
    "/documents?limit=10",
  ]) {
    let settled = false;
    const pending = request(path).finally(() => {
      settled = true;
    });
    const rejected = assert.rejects(pending, /timed out/);
    t.mock.timers.tick(90000);
    await Promise.resolve();
    assert.equal(settled, false, path);
    t.mock.timers.tick(59999);
    await Promise.resolve();
    assert.equal(settled, false, path);
    t.mock.timers.tick(1);
    await rejected;
  }
});

test("other routes keep the 60-second timeout", async (t) => {
  pendingFetch(t);
  const rejected = assert.rejects(request("/agent/runs"), /timed out/);
  t.mock.timers.tick(60000);
  await rejected;
});

test("caller cancellation still interrupts a slow request immediately", async (t) => {
  pendingFetch(t);
  const controller = new AbortController();
  const rejected = assert.rejects(
    request("/explain", { signal: controller.signal }),
    /cancelled/,
  );
  controller.abort();
  await rejected;
});

test("receipt screenshots resolve against the API base and reject unsafe protocols", () => {
  assert.equal(assetUrl("receipts/run-1.jpg"), BASE + "/receipts/run-1.jpg");
  assert.equal(
    assetUrl("/receipts/run-1.jpg"),
    new URL("/receipts/run-1.jpg", BASE).href,
  );
  assert.equal(assetUrl("javascript:alert(1)"), undefined);
});

test("receipt renders reference, summary, source link and API screenshot as a citation", () => {
  const html = renderToStaticMarkup(
    createElement(ReceiptView, {
      receipt: {
        reference_no: "REF-123",
        summary: "Your application was submitted.",
        url: "https://example.gov.in/applications/123",
        screenshot: "/receipts/run-1.jpg",
      },
    }),
  );
  assert.match(html, /<ol class="citations receipt-citations">/);
  assert.match(html, /<strong>REF-123<\/strong>/);
  assert.match(
    html,
    /<blockquote>Your application was submitted\.<\/blockquote>/,
  );
  assert.match(html, /href="https:\/\/example.gov.in\/applications\/123"/);
  assert.ok(
    html.includes(`src="${new URL("/receipts/run-1.jpg", BASE).href}"`),
  );
});

test("unsafe receipt sources do not produce links or images", () => {
  const html = renderToStaticMarkup(
    createElement(ReceiptView, {
      receipt: {
        url: "javascript:alert(1)",
        screenshot: "javascript:alert(1)",
        summary: "Receipt",
      },
    }),
  );
  assert.doesNotMatch(html, /<a |<img /);
});

test("slow-operation progress text is exposed as a live status", () => {
  const html = renderToStaticMarkup(
    createElement(Loading, {
      message: "Checking schemes against official rules…",
    }),
  );
  assert.match(html, /role="status"/);
  assert.match(html, /Checking schemes against official rules…/);
});

test("failed API responses never show provider or validation internals", async (t) => {
  t.mock.method(
    globalThis,
    "fetch",
    async () =>
      new Response(
        JSON.stringify({
          detail:
            "Traceback: provider credential=private-value; database unavailable",
        }),
        { status: 502, headers: { "Content-Type": "application/json" } },
      ),
  );
  await assert.rejects(request("/schemes/search"), {
    message: responseError(502),
  });
  for (const raw of [
    "TypeError: Failed to fetch",
    "Internal Server Error",
    "Traceback: credential=private-value",
  ])
    assert.equal(friendlyError(raw), responseError(500));
});

test("errors provide friendly recovery and a retry control", () => {
  const html = renderToStaticMarkup(
    createElement(ErrorBox, {
      error: "raw database exception",
      retry: () => {},
    }),
  );
  assert.match(html, /role="alert"/);
  assert.match(html, /Let’s try that again/);
  assert.match(html, /Try again/);
  assert.doesNotMatch(html, /raw database exception/);
  assert.match(responseError(429), /wait a moment/);
  assert.match(responseError(404), /list/);
  assert.match(responseError(422), /check the details/);
  assert.match(
    friendlyError("Node 'approval' raised asyncio.CancelledError"),
    /application was stopped/,
  );
});
