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
const { submissionForm, reportsQuery, statusMeta, sourceBadge } =
  await server.ssrLoadModule("/src/api/civic.ts");
const { CivicTimelineView } = await server.ssrLoadModule(
  "/src/pages/CivicTrack.tsx",
);
const { ActivityTimeline } = await server.ssrLoadModule("/src/pages/Runs.tsx");
const { Explanation } = await server.ssrLoadModule("/src/components.tsx");
const { resolveLink } = await server.ssrLoadModule("/src/api/alerts.ts");
const { withOwner } = await server.ssrLoadModule("/src/api/client.ts");
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


test("talk drops unknown languages and accepts Assamese", () => {
  assert.deepEqual(JSON.parse(talkBody({ profile_id: "p1", text: "hi", lang: "invalid" }).body), {
    profile_id: "p1",
    text: "hi",
  });
  assert.equal(JSON.parse(talkBody({ profile_id: "p1", text: "hi", lang: "bn" }).body).lang, "bn");
  assert.equal(JSON.parse(talkBody({ profile_id: "p1", text: "hi", lang: "as" }).body).lang, "as");
});

test("locker reads server variants [{format, bytes}] and links carry the owner", () => {
  const item = {
    id: "abc",
    doc_type: "income_certificate",
    title: "Income Certificate",
    variants: [
      { format: "jpg", bytes: 184320 },
      { format: "pdf", bytes: 215040 },
    ],
    meta: { readable: true, issues: [] },
    created_at: "2026-11-01T00:00:00Z",
  };
  assert.deepEqual(variantSizes(item), [
    ["JPG", 184320],
    ["PDF", 215040],
  ]);
  assert.equal(variantSummary(item), "JPG 180 KB · PDF 210 KB");
  assert.deepEqual(variantSizes({ variants: [] }), []);
  assert.equal(formatKb(184320), "180 KB");
  assert.equal(formatKb(null), "");
  const form = uploadForm("p1", new Blob(["abc"]), "scan.jpg", "aadhaar");
  assert.equal(form.get("profile_id"), "p1");
  assert.equal(form.get("doc_type"), "aadhaar");
  const html = renderToStaticMarkup(
    createElement(LockerItemCard, { item, isNew: true, profileId: "p1", onDelete() {} }),
  );
  assert.match(html, /Income Certificate/);
  assert.match(html, /JPG 180 KB · PDF 210 KB ready/);
  assert.match(html, /locker\/abc\/file\?variant=jpg&amp;profile_id=p1/);
  assert.equal(withOwner("/agent/runs/r1", "p 1"), "/agent/runs/r1?profile_id=p+1");
});

test("civic submission matches /reports multipart and timeline labels by source", () => {
  const triage = {
    category: "water",
    title: "Pipe leak",
    title_local: "पाइप लीक",
    description: "Water leaking for three days",
    severity: "high",
    severity_reason: "Drinking water lost",
    department: "Delhi Jal Board",
  };
  const form = submissionForm({ profile_id: "p1", lat: 25.3176, lng: 82.9739, text: " Pipe leak " }, triage);
  assert.equal(form.get("profile_id"), "p1");
  assert.equal(form.get("lat"), "25.3176");
  assert.equal(form.get("lng"), "82.9739");
  assert.equal(form.get("text"), "Pipe leak");
  assert.deepEqual(JSON.parse(form.get("triage")), triage);
  assert.equal(submissionForm({ profile_id: "p1", lat: 1, lng: 2 }).get("triage"), null);
  assert.equal(reportsQuery({ status: "filed", category: "", lat: 25.3, radius_km: 25 }), "?status=filed&lat=25.3&radius_km=25");
  assert.equal(statusMeta("filed").tone, "act");
  assert.equal(statusMeta("resolved").tone, "ok");
  assert.equal(sourceBadge({ source: "official" }).kind, "official");
  assert.equal(sourceBadge({ source: "system" }).kind, "system");
  const html = renderToStaticMarkup(
    createElement(CivicTimelineView, {
      report: {
        events: [
          { id: 1, source: "citizen", kind: "created", text: "Citizen reported this issue", meta: {}, created_at: "2026-11-01T00:00:00Z" },
          { id: 2, source: "official", kind: "filed", text: "Registered on CPGRAMS as MORPR/E/2026/004812", meta: {}, created_at: "2026-11-01T01:00:00Z" },
        ],
      },
    }),
  );
  assert.match(html, /Citizen · नागरिक/);
  assert.match(html, /Official CPGRAMS reply · सरकारी जवाब/);
  assert.match(html, /MORPR\/E\/2026\/004812/);
});

test("activity timeline renders server items and maps server links to app routes", () => {
  assert.deepEqual(resolveLink("/reports/r9"), { to: "/civic/r9" });
  assert.deepEqual(resolveLink("/runs/x"), { to: "/runs/x" });
  assert.deepEqual(resolveLink("https://pib.gov.in/a"), { href: "https://pib.gov.in/a" });
  assert.deepEqual(resolveLink("javascript:alert(1)"), {});
  const html = renderToStaticMarkup(
    createElement(
      MemoryRouter,
      null,
      createElement(ActivityTimeline, {
        items: [
          { type: "run", id: "run-9", title: "Apply for PM-KISAN", status: "done", official: true, updated_at: "2026-11-01T00:00:00Z", link: "/runs/run-9" },
          { type: "report", id: "r9", title: "वार्ड 14 में पानी", status: "filed", official: true, updated_at: "2026-10-31T00:00:00Z", link: "/reports/r9" },
        ],
      }),
    ),
  );
  assert.match(html, /Apply for PM-KISAN/);
  assert.match(html, /href="\/civic\/r9"/);
  assert.match(html, /वार्ड 14 में पानी/);
});

test("explanation renders quoted sections and compare changes", () => {
  const cite = (quote) => ({ source_url: "https://scholarships.gov.in/c.pdf", title: "Circular", quote });
  const html = renderToStaticMarkup(
    createElement(Explanation, {
      data: {
        title: "New Scholarship Circular 2026",
        summary: "Income limit raised.",
        key_points: [],
        your_rights: [],
        what_it_means_for_you: "Your household qualifies under the new limit.",
        deadlines: [],
        documents_needed: [],
        citations: [],
        language: "en",
        duties: [{ text: "Renew every year", citation: cite("must be renewed annually") }],
        changes: [
          {
            title: "Income ceiling",
            description: "Limit raised",
            old_citation: cite("Rs. 2.00 lakh"),
            new_citation: cite("Rs. 2.50 lakh"),
            affects_profile: true,
            impact: "You now qualify",
          },
        ],
      },
    }),
  );
  assert.match(html, /Your duties/);
  assert.match(html, /must be renewed annually/);
  assert.match(html, /What changed/);
  assert.match(html, /Rs\. 2\.00 lakh/);
  assert.match(html, /Rs\. 2\.50 lakh/);
  assert.match(html, /Your household qualifies under the new limit\./);
});

