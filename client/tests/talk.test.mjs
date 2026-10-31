import { test, after } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";

const server = await createServer({
  server: { middlewareMode: true },
  appType: "custom",
  optimizeDeps: { noDiscovery: true, include: [] },
});
after(() => server.close());
const { talkBody, applyTalkEvent } = await server.ssrLoadModule("/src/api/talk.ts");

test("talk sends JSON for text and multipart for audio", async () => {
  const text = talkBody({ profile_id: "p1", text: "hello" });
  assert.deepEqual(JSON.parse(text.body), { profile_id: "p1", text: "hello" });
  assert.equal(text.headers["Content-Type"], "application/json");
  const audio = talkBody({
    profile_id: "p1",
    audio: new Blob(["x"], { type: "audio/webm" }),
    lang: "hi",
  });
  assert.ok(audio.body instanceof FormData);
  assert.equal(audio.body.get("profile_id"), "p1");
  assert.equal(audio.body.get("lang"), "hi");
  assert.ok(audio.body.get("audio"));
  assert.deepEqual(audio.headers, {});
});

test("talk events build the bot message", () => {
  let m = [{ id: 2, from: "bot", text: "", cards: [] }];
  m = applyTalkEvent(m, { type: "delta", text: "Hel" }, 2);
  m = applyTalkEvent(m, { type: "delta", text: "lo" }, 2);
  m = applyTalkEvent(
    m,
    { type: "card", card: { kind: "run", run_id: "r1" } },
    2,
  );
  assert.equal(m[0].text, "Hello");
  assert.equal(m[0].cards.length, 1);
  m = applyTalkEvent(
    m,
    { type: "done", text: "Hello!", lang: "hi", audio_url: "/a.wav" },
    2,
  );
  assert.equal(m[0].text, "Hello!");
  assert.equal(m[0].lang, "hi");
  assert.equal(m[0].audioUrl, "/a.wav");
});
