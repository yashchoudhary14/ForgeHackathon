// Pure modules run directly on Node 24: node --test tests/buddy.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  dispatchAction,
  confirmationIntent,
  normaliseAnswer,
  profileComplete,
} from "../src/buddy/actions.ts";
import { micGesture, silenceExpired } from "../src/buddy/mic.ts";

function host() {
  const calls = [];
  return {
    calls,
    navigate: (route) => calls.push(["navigate", route]),
    activateRun: (id) => calls.push(["run", id]),
    openCamera: (...args) => calls.push(["camera", ...args]),
    setLanguage: (lang) => calls.push(["lang", lang]),
    profileChanged: (...args) => calls.push(["profile", ...args]),
  };
}
test("every Buddy action dispatches to the exact app capability", async () => {
  const h = host();
  for (const a of [
    { type: "navigate", route: "/locker" },
    { type: "open_scheme", slug: "support-1" },
    { type: "start_application", slug: "support-1", run_id: "run-2" },
    {
      type: "open_camera",
      doc_type: "income_certificate",
      reason: "Income proof",
    },
    { type: "open_report" },
    { type: "show_profile" },
    { type: "set_language", lang: "hi" },
    { type: "fill_profile_field", field: "is_student", value: false },
  ])
    assert.equal(await dispatchAction(a, h), true);
  assert.deepEqual(h.calls, [
    ["navigate", "/locker"],
    ["navigate", "/schemes/support-1"],
    ["run", "run-2"],
    ["navigate", "/runs/run-2"],
    ["camera", "income_certificate", "Income proof"],
    ["navigate", "/civic/new"],
    ["navigate", "/profile"],
    ["lang", "hi"],
    ["profile", "is_student", false],
  ]);
});
test("untrusted actions cannot navigate externally, create a run, or write private fields", async () => {
  const h = host();
  for (const a of [
    null,
    { type: "navigate", route: "//evil.example" },
    { type: "navigate", route: "/locker?profile_id=other" },
    { type: "open_scheme", slug: "../private" },
    { type: "start_application", slug: "s" },
    { type: "start_application", slug: "s", run_id: "https://evil.example" },
    { type: "open_camera", doc_type: "password", reason: "" },
    { type: "set_language", lang: "xx" },
    { type: "fill_profile_field", field: "phone", value: "private" },
    { type: "fill_profile_field", field: "age", value: {} },
    { type: "approve" },
  ])
    assert.equal(await dispatchAction(a, h), false);
  assert.deepEqual(h.calls, []);
});
test("tap starts, second tap sends, and holding releases with one stop", () => {
  assert.equal(micGesture(false, 0), "start");
  assert.equal(micGesture(true, 0), "stop");
  assert.equal(micGesture(true, 299), "stop");
  assert.equal(micGesture(true, 301), "stop");
  // Releasing before getUserMedia resolves still cancels the pending hold.
  assert.equal(micGesture(false, 301), "stop");
});
test("local AudioContext meter requires two seconds of continuous silence", () => {
  assert.equal(silenceExpired(0.001, 1999, 0), false);
  assert.equal(silenceExpired(0.001, 2000, 0), true);
  assert.equal(silenceExpired(0.1, 2500, 0), false);
  assert.equal(silenceExpired(0.001, 2500, 2000), false);
});
test("verification digits normalise locally; a question is never a yes", () => {
  for (const text of [
    "4 1 7 9 2 3",
    "four one seven nine two three",
    "४ १ ७ ९ २ ३",
    "৪ ১ ৭ ৯ ২ ৩",
  ])
    assert.equal(normaliseAnswer(text, "otp"), "417923");
  assert.equal(normaliseAnswer("Ab 4C", "captcha"), "Ab 4C");
  assert.equal(normaliseAnswer("A B four C", "captcha", true), "AB4C");
  assert.equal(normaliseAnswer("capital A small b 4", "captcha", true), "Ab4");
  assert.equal(normaliseAnswer("ए बी चार सी", "captcha", true), "AB4C");
  assert.equal(confirmationIntent("हाँ"), "yes");
  assert.equal(confirmationIntent("না"), "no");
  assert.equal(confirmationIntent("yes but change the first digit"), null);
});
test("onboarding preserves false and zero as actual answers", () => {
  const data = {
    state: "Bihar",
    age: 21,
    gender: "female",
    occupation: "student",
    is_student: false,
    annual_income: 0,
    caste: "sc",
    residence: "rural",
  };
  assert.equal(profileComplete(data), true);
  assert.equal(profileComplete({ ...data, state: "" }), false);
  assert.equal(profileComplete({ ...data, caste: null }), false);
});
