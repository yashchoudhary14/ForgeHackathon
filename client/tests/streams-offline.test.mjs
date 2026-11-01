// No Vite server, browser, npm command or network: exercise the real SSE clients
// with controlled byte streams using Node's built-in TypeScript stripping.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";

const modules = new Map();
function moduleUrl(file) {
  if (modules.has(file.href)) return modules.get(file.href);
  const source = readFileSync(file, "utf8").replaceAll(
    "import.meta.env.VITE_API_URL", '""',
  );
  const js = stripTypeScriptTypes(source).replace(
    /from\s+"(\.\.?\/[^"\n]+)"/g,
    (_match, path) => `from "${moduleUrl(new URL(path + ".ts", file))}"`,
  );
  const url = "data:text/javascript;base64," + Buffer.from(js).toString("base64");
  modules.set(file.href, url);
  return url;
}
const load = (name) => import(moduleUrl(new URL(`../src/api/${name}.ts`, import.meta.url)));
const { streamTalk, applyTalkEvent } = await load("talk");
const { streamMatches, withOwner, BASE } = await load("client");
const { applyMatchEvent } = await load("match-state");
const bytes = (event) => new TextEncoder().encode(`data: ${JSON.stringify(event)}\r\n\r\n`);

test("Talk delivers transcript, progress, Unicode deltas and cards while response is still open", async (t) => {
  let writer;
  const body = new ReadableStream({ start(c) { writer = c; } });
  t.mock.method(globalThis, "fetch", async (url, init) => {
    assert.equal(url, BASE + "/api/talk");
    assert.deepEqual(JSON.parse(init.body), { profile_id: "citizen", text: "नमस्ते" });
    return new Response(body);
  });
  const events = [];
  let messages = [{ id: 2, from: "bot", text: "", cards: [] }];
  let settled = false, received;
  const firstCard = new Promise((resolve) => { received = resolve; });
  const pending = streamTalk({ profile_id: "citizen", text: "नमस्ते" }, (event) => {
    events.push(event);
    messages = applyTalkEvent(messages, event, 2);
    if (event.type === "card") received();
  }, new AbortController().signal).then(() => { settled = true; });
  for (const event of [
    { type: "transcript", text: "नमस्ते", lang: "hi" },
    { type: "progress", stage: "finding_schemes" },
    { type: "delta", text: "नमस्ते " },
    { type: "delta", text: "किसान" },
    { type: "card", card: { kind: "scheme", slug: "official", name: "Official", verdict: "likely" } },
  ]) {
    for (const byte of bytes(event)) writer.enqueue(new Uint8Array([byte]));
  }
  await firstCard;
  assert.equal(settled, false);
  assert.deepEqual(events.map((e) => e.type), ["transcript", "progress", "delta", "delta", "card"]);
  assert.equal(messages[0].text, "नमस्ते किसान");
  assert.equal(messages[0].cards[0].slug, "official");
  writer.enqueue(bytes({ type: "done", text: "नमस्ते किसान", audio_url: "/files/audio/reply.wav" }));
  await pending; // Does not wait for EOF or requestfinished.
  assert.equal(messages[0].audioUrl, "/files/audio/reply.wav");
});

test("Schemes sends owner profile and exposes results before done, then replaces with ranked final list", async (t) => {
  let writer, received;
  const firstResult = new Promise((resolve) => { received = resolve; });
  const body = new ReadableStream({ start(c) { writer = c; } });
  t.mock.method(globalThis, "fetch", async (url, init) => {
    assert.equal(url, BASE + "/api/schemes/match/stream");
    assert.equal(init.method, "POST");
    assert.deepEqual(JSON.parse(init.body), { profile_id: "saved-profile", limit: 8 });
    return new Response(body);
  });
  let matches = [], settled = false, progress = "";
  const pending = streamMatches({ profile_id: "saved-profile", limit: 8 }, (event) => {
    if (event.type === "progress") progress = event.message;
    matches = applyMatchEvent(matches, event);
    if (event.type === "result") received();
  }, new AbortController().signal).then(() => { settled = true; });
  const found = { scheme: { slug: "scheme", name: "Official" }, verdict: "likely", confidence: 0.8 };
  writer.enqueue(bytes({ type: "progress", message: "checked 1/8", checked: 1, total: 8 }));
  writer.enqueue(bytes({ type: "result", result: found }));
  await firstResult;
  assert.equal(settled, false);
  assert.equal(progress, "checked 1/8");
  assert.deepEqual(matches, [found]);
  writer.enqueue(bytes({ type: "done", results: [found] }));
  await pending;
  assert.deepEqual(matches, [found]);
});

test("run reads and WebSocket ownership encode the saved profile", () => {
  for (const path of ["/agent/runs/r1", "/agent/runs/r1/ws", "/agent/runs/r1?view=steps"]) {
    const url = new URL(withOwner(path, "owner + id"), "https://example.test");
    assert.equal(url.searchParams.get("profile_id"), "owner + id");
  }
});

test("Talk and Schemes reject incomplete/error streams and cancel their readers", async (t) => {
  for (const start of [
    (onEvent) => streamTalk({ profile_id: "p", text: "hello" }, onEvent, new AbortController().signal),
    (onEvent) => streamMatches({ profile_id: "p" }, onEvent, new AbortController().signal),
  ]) {
    for (const error of [false, true]) {
      let cancelled = false;
      t.mock.method(globalThis, "fetch", async () => new Response(new ReadableStream({
        start(c) {
          if (error) c.enqueue(bytes({ type: "error", message: "Please retry." }));
          else c.close();
        },
        cancel() { cancelled = true; },
      })));
      await assert.rejects(start(() => {}), error ? /Please retry/ : /before the answer was complete/);
      if (error) assert.equal(cancelled, true);
    }
  }
});
