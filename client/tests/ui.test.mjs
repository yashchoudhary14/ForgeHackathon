import { test, after } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

const server = await createServer({
  server: { middlewareMode: true, hmr: false },
  // Match the router ESM exports used by Node and the other SSR tests.
  ssr: { resolve: { externalConditions: ["module-sync"] } },
  appType: "custom",
  optimizeDeps: { noDiscovery: true, include: [] },
});
after(() => server.close());
const { tt } = await server.ssrLoadModule("/src/ui-strings.ts");
const { VerdictChip, StatTile, Orb, EmptyState } =
  await server.ssrLoadModule("/src/ui.tsx");
const { SwipeToConfirm } = await server.ssrLoadModule("/src/guide.tsx");

test("tt falls back to English when a language lacks a key", () => {
  assert.equal(tt("hi", "navTalk"), "बोलें");
  assert.equal(tt("as", "navSchemes"), "আঁচনি");
  assert.equal(tt("as", "navExplain"), "বুজক");
  assert.equal(tt("as", "verdictEligible-missing"), "verdictEligible-missing");
  assert.equal(tt("xx", "navTalk"), "Talk");
});

test("navigation and Talk mode chrome are translated to Hindi, Bengali and Assamese", async () => {
  const { hi } = await server.ssrLoadModule("/src/ui-strings-hi.ts");
  const { bn, as } = await server.ssrLoadModule("/src/ui-strings-bn.ts");
  const chrome = [
    "mainNav", "navTalk", "navSchemes", "navDocuments", "navCivic", "navAlerts",
    "navForYou", "navExplain", "navApplications", "navLocker", "navCivicMap",
    "navActivity", "talkMode", "talkTitle", "holdToTalk", "listening", "thinking",
    "speaking", "typeInstead", "typePlaceholder", "send", "langDetected", "changeLang",
    "talkEmpty", "micDenied", "talkError", "openScheme", "openRun", "openReport",
    "startReport", "sendDocument", "close", "audioFailed", "playAudio",
  ];
  for (const [name, table] of Object.entries({ hi, bn, as })) {
    const missing = chrome.filter((k) => !table[k]);
    assert.deepEqual(missing, [], `${name} is missing ${missing.join(", ")}`);
  }
});

test("components render accessible markup", () => {
  assert.match(
    renderToStaticMarkup(createElement(VerdictChip, { verdict: "eligible" })),
    /Eligible/,
  );
  assert.match(
    renderToStaticMarkup(createElement(StatTile, { value: 3, label: "docs" })),
    /docs/,
  );
  assert.match(
    renderToStaticMarkup(createElement(Orb, { state: "listening" })),
    /data-state="listening"/,
  );
  assert.match(
    renderToStaticMarkup(createElement(EmptyState, { title: "Nothing" })),
    /role="status"/,
  );
  const swipe = renderToStaticMarkup(
    createElement(SwipeToConfirm, { label: "Swipe", onConfirm() {} }),
  );
  assert.match(swipe, /role="slider"/);
  assert.match(swipe, /tabindex="0"/);
});
