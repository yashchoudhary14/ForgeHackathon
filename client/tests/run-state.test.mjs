import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";
import ts from "typescript";

const js = ts.transpileModule(
  readFileSync(new URL("../src/api/run-state.ts", import.meta.url), "utf8"),
  {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ESNext,
    },
  },
).outputText;
const { isTerminal, applyRunEvent, mergeRunSnapshot } = await import(
  "data:text/javascript;base64," + Buffer.from(js).toString("base64")
);
const run = {
  id: "run-1",
  status: "queued",
  receipt: null,
  error: null,
  steps: [],
};
const step = (idx, result) => ({ idx, result, status: "done" });

test("only done, failed and aborted finish a run", () => {
  for (const status of [
    "queued",
    "running",
    "needs_human",
    "awaiting_approval",
    "done",
    "failed",
    "aborted",
  ]) {
    assert.equal(
      isTerminal(status),
      ["done", "failed", "aborted"].includes(status),
    );
    assert.equal(applyRunEvent(run, { type: "status", status }).status, status);
  }
});

test("human prompt replay restores the correct waiting status", () => {
  for (const kind of [
    "captcha",
    "otp",
    "missing_field",
    "login",
    "confirm_submit",
  ]) {
    const message = { type: "needs_human", kind, message: "Please continue" };
    const replayed = applyRunEvent(applyRunEvent(run, message), message);
    assert.equal(
      replayed.status,
      kind === "confirm_submit" ? "awaiting_approval" : "needs_human",
    );
  }
});

test("repeated and out-of-order steps stay ordered and retain the latest result", () => {
  let current = run;
  for (const event of [
    step(1, "ok"),
    step(0, "ok"),
    step(1, "ok but NOTHING CHANGED on the page"),
    step(2, "Portal error"),
  ]) {
    current = applyRunEvent(current, { type: "step", step: event });
  }
  assert.deepEqual(
    current.steps.map((s) => [s.idx, s.result]),
    [
      [0, "ok"],
      [1, "ok but NOTHING CHANGED on the page"],
      [2, "Portal error"],
    ],
  );
});

test("reconnect snapshot restores missed steps without overwriting newer live updates", () => {
  const snapshot = {
    ...run,
    status: "running",
    steps: [step(0, "ok"), step(1, "pending")],
  };
  const live = {
    ...run,
    status: "awaiting_approval",
    steps: [step(1, "ok"), step(2, "ok")],
  };
  const merged = mergeRunSnapshot(snapshot, live, new Set([1, 2]), true);
  assert.equal(merged.status, "awaiting_approval");
  assert.deepEqual(
    merged.steps.map((s) => s.result),
    ["ok", "ok", "ok"],
  );
});

test("a fresh snapshot replaces stale local steps and restores offline completion", () => {
  const snapshot = { ...run, status: "done", steps: [step(0, "ok")] };
  const stale = { ...run, status: "running", steps: [step(0, "pending")] };
  const merged = mergeRunSnapshot(snapshot, stale, new Set(), false);
  assert.equal(merged.status, "done");
  assert.equal(merged.steps[0].result, "ok");
});

test("done uses the backend status and a late snapshot preserves its receipt", () => {
  const receipt = {
    reference_no: "REF-123",
    summary: "Submitted",
    url: "https://gov.in/application",
    screenshot: "/receipts/run-1.jpg",
  };
  const done = applyRunEvent(run, { type: "done", receipt });
  assert.equal(done.status, "done");
  assert.deepEqual(
    mergeRunSnapshot(run, done, new Set(), true).receipt,
    receipt,
  );
});
