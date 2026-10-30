import { test, after } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";

const server = await createServer({
  server: { middlewareMode: true },
  appType: "custom",
});
after(() => server.close());
const { request, assetUrl, BASE } =
  await server.ssrLoadModule("/src/api/client.ts");

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
