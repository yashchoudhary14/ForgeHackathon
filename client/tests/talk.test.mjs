import { test, after } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

const server = await createServer({
  server: { middlewareMode: true, hmr: false },
  ssr: { resolve: { externalConditions: ["module-sync"] } },
  appType: "custom",
  optimizeDeps: { noDiscovery: true, include: [] },
});
after(() => server.close());
const { talkBody, applyTalkEvent } = await server.ssrLoadModule("/src/api/talk.ts");
const { variantSizes, variantSummary, formatKb, uploadForm } =
  await server.ssrLoadModule("/src/api/locker.ts");
const { default: LockerItemCard } = await server.ssrLoadModule(
  "/src/pages/LockerItemCard.tsx",
);
const { triageForm, reportsQuery, statusMeta, actorBadge } =
  await server.ssrLoadModule("/src/api/civic.ts");
const { CivicTimelineView } = await server.ssrLoadModule(
  "/src/pages/CivicTrack.tsx",
);
const { ActivityView } = await server.ssrLoadModule("/src/pages/Runs.tsx");
const { Explanation } = await server.ssrLoadModule("/src/components.tsx");
const { MemoryRouter } = await import("react-router-dom");

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

test("locker variants list sizes from object or array and render item card", () => {
  assert.deepEqual(variantSizes({ variants: { jpg: 184320, pdf: 215040 } }), [
    ["JPG", 184320],
    ["PDF", 215040],
  ]);
  assert.equal(
    variantSummary({ variants: { jpg: 184320, pdf: 215040 } }),
    "JPG 180 KB · PDF 210 KB",
  );
  assert.deepEqual(variantSizes({ variants: [{ variant: "jpg", size: 1 }] }), [["JPG", 1]]);
  assert.deepEqual(variantSizes({}), []);
  assert.equal(formatKb(184320), "180 KB");
  assert.equal(formatKb(null), "");
  const form = uploadForm("p1", new Blob(["abc"]), "scan.jpg", "aadhaar");
  assert.equal(form.get("profile_id"), "p1");
  assert.equal(form.get("doc_type"), "aadhaar");
  const html = renderToStaticMarkup(
    createElement(LockerItemCard, {
      item: {
        id: 7,
        doc_type: "income_certificate",
        title: "आय प्रमाण पत्र",
        variants: { jpg: 184320, pdf: 215040 },
        meta: { readable: true, issues: [] },
      },
      isNew: true,
      onDelete() {},
    }),
  );
  assert.match(html, /आय प्रमाण पत्र/);
  assert.match(html, /JPG 180 KB · PDF 210 KB ready/);
  assert.match(html, /New · नया/);
});

test("civic triage form, query string, badges and timeline view work cleanly", () => {
  const form = triageForm({
    text: "Pipeline leak",
    lat: 25.3176,
    lng: 82.9739,
    lang: "hi",
  });
  assert.equal(form.get("text"), "Pipeline leak");
  assert.equal(form.get("lat"), "25.3176");
  assert.equal(form.get("lng"), "82.9739");
  assert.equal(form.get("lang"), "hi");
  assert.equal(
    reportsQuery({ state: "UP", status: "filed", category: "" }),
    "?state=UP&status=filed",
  );
  assert.equal(statusMeta("filed").tone, "act");
  assert.equal(statusMeta("citizen_verified").tone, "ok");
  assert.equal(actorBadge({ actor: "official" }).kind, "official");
  assert.equal(actorBadge({ receipt_no: "MORPR/E/2026/004812" }).kind, "agent");
  const timelineHtml = renderToStaticMarkup(
    createElement(CivicTimelineView, {
      report: {
        id: 204,
        category: "water",
        title: "वार्ड 14 में पानी की पाइपलाइन टूटी",
        status: "filed",
        upvotes: 19,
        events: [
          {
            id: 1,
            actor: "citizen",
            title: "19 पड़ोसियों ने +1 पुष्टि की",
          },
          {
            id: 2,
            actor: "agent",
            title: "Adhikaar Agent ने CPGRAMS पर शिकायत दर्ज की",
            receipt_no: "MORPR/E/2026/004812",
          },
          {
            id: 3,
            actor: "official",
            title: "विभाग ने जवाब भेजा",
            note: "मरम्मत दल भेजा गया",
          },
        ],
      },
    }),
  );
  assert.match(timelineHtml, /Citizen · नागरिक/);
  assert.match(timelineHtml, /Adhikaar Agent · CPGRAMS/);
  assert.match(timelineHtml, /Official · सरकारी जवाब/);
  assert.match(timelineHtml, /MORPR\/E\/2026\/004812/);
});

test("unified activity view and restyled explanation with comparison render cleanly", () => {
  const actHtml = renderToStaticMarkup(
    createElement(
      MemoryRouter,
      null,
      createElement(ActivityView, {
        runs: [
          {
            id: "run-9",
            portal_url: "https://pmkisan.gov.in",
            goal: "Apply for PM-KISAN",
            status: "done",
            receipt: { reference_no: "PMK-2026-99" },
            steps: [],
          },
        ],
        reports: [
          {
            id: 204,
            category: "water",
            department: "Jal Jeevan Mission",
            title: "वार्ड 14 में पानी की पाइपलाइन टूटी",
            status: "filed",
            upvotes: 19,
            cpgrams_ref: "MORPR/E/2026/004812",
          },
        ],
      }),
    ),
  );
  assert.match(actHtml, /Apply for PM-KISAN/);
  assert.match(actHtml, /PMK-2026-99/);
  assert.match(actHtml, /वार्ड 14 में पानी की पाइपलाइन टूटी/);
  assert.match(actHtml, /MORPR\/E\/2026\/004812/);

  const expHtml = renderToStaticMarkup(
    createElement(Explanation, {
      data: {
        title: "New Scholarship Circular 2026",
        summary: "Income limit raised to ₹2.5 lakh and deadline extended.",
        key_points: ["Deadline is 30 November"],
        your_rights: ["Free application at CSC"],
        what_it_means_for_you: "Your household qualifies under the new limit.",
        deadlines: ["30 November 2026"],
        documents_needed: ["Income certificate"],
        citations: [
          {
            source_url: "https://scholarships.gov.in/circular.pdf",
            title: "Page 2, Para 4",
            quote: "Annual family income ceiling revised to Rs. 2.50 lakh.",
          },
        ],
        language: "en",
      },
      compare: {
        title: "Old Scholarship Circular 2024",
        summary: "Income limit was ₹2.0 lakh.",
        key_points: ["Deadline was 31 October"],
        your_rights: [],
        deadlines: [],
        documents_needed: [],
        citations: [],
        language: "en",
      },
    }),
  );
  assert.match(expHtml, /New Scholarship Circular 2026/);
  assert.match(expHtml, /What changed · पुराने सर्कुलर से तुलना/);
  assert.match(expHtml, /Old Scholarship Circular 2024/);
  assert.match(expHtml, /Your household qualifies under the new limit\./);
});
