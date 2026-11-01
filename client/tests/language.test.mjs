import "./load-client.mjs";
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

const { en, tt } = await import("../src/ui-strings.ts");
const { hi } = await import("../src/ui-strings-hi.ts");
const { bn, as } = await import("../src/ui-strings-bn.ts");
const { profileHi, profileBn, profileAs } = await import("../src/profile-strings.ts");
const { translate } = await import("../src/i18n.ts");
const { Provider } = await import("../src/context.tsx");
const { BuddyProvider } = await import("../src/buddy/context.tsx");
const { default: Welcome } = await import("../src/buddy/BuddyWelcome.tsx");
const { default: Profile } = await import("../src/pages/Profile.tsx");
const { default: CivicNew } = await import("../src/pages/CivicNew.tsx");
const { default: Locker } = await import("../src/pages/Locker.tsx");
const { BrandWordmark } = await import("../src/nav.tsx");

function render(component, lang, props = {}) {
  const storage = globalThis.localStorage;
  globalThis.localStorage = { getItem: (key) => key === "adhikaar-language" ? lang : null };
  try {
    return renderToStaticMarkup(createElement(Provider, null,
      createElement(MemoryRouter, null, createElement(BuddyProvider, null,
        createElement(component, props)))));
  } finally { globalThis.localStorage = storage; }
}

test("every UI string has Hindi, Bengali and Assamese copy", () => {
  assert.ok(Object.values(en).every((value) => !/[\u0900-\u09ff]/.test(value)), "English copy must not contain a second-language subtitle");
  for (const [lang, table] of Object.entries({ hi: { ...hi, ...profileHi }, bn: { ...bn, ...profileBn }, as: { ...as, ...profileAs } })) {
    const missing = Object.keys(en).filter((key) => !table[key]?.trim());
    assert.deepEqual(missing, [], `${lang} missing translations`);
  }
});

test("English QA labels stay exact and all selected languages use their own copy", () => {
  for (const label of ["Upload photo", "Take or choose a photo", "Use my location", "Preview AI triage", "Report title", "Confirm & submit new report", "File on CPGRAMS", "Open camera", "Document type", "Civic issues map", "Audit trail"]) {
    assert.equal(translate(label, "en"), label);
    for (const lang of ["hi", "bn", "as"])
      assert.notEqual(translate(label, lang), label, `${lang}: ${label}`);
  }
  for (const lang of ["en", "hi", "bn", "as"])
    assert.equal(translate("Buddy", lang), tt(lang, "brandName"));
  assert.equal(translate("Waiting for your approval", "as"), "আপোনাৰ অনুমতিৰ বাবে অপেক্ষা");
  assert.equal(translate("Connecting…", "bn"), "সংযোগ হচ্ছে…");
});

test("welcome and profile ask for an optional full name first in all four languages", () => {
  for (const lang of ["en", "hi", "bn", "as"]) {
    for (const [component, props] of [[Welcome, { profile: true }], [Profile, {}]]) {
      const html = render(component, lang, props);
      const form = html.slice(html.indexOf("<form"));
      assert.ok(form.includes(tt(lang, "fullName")));
      const inputs = [...form.matchAll(/<input\b[^>]*>/g)].map((m) => m[0]);
      assert.match(inputs[0], /autoComplete="name"/i);
      assert.doesNotMatch(inputs[0], /\brequired\b/);
    }
  }
});

test("profile forms prefill and send the name only inside sensitive profile data", () => {
  for (const file of ["../src/buddy/BuddyWelcome.tsx", "../src/pages/Profile.tsx"]) {
    const source = readFileSync(new URL(file, import.meta.url), "utf8");
    assert.match(source, /setFullName\(out\.sensitive\?\.full_name \?\? ""\)/);
    assert.match(source, /sensitive: \{ full_name: fullName\.trim\(\) \}/);
    assert.doesNotMatch(source, /(?:data|text|message|prompt):\s*fullName/);
  }
});

test("brand badge and introductory pages render only the selected language", () => {
  assert.doesNotMatch(render(BrandWordmark, "en"), /साथी|বন্ধু/);
  for (const lang of ["hi", "bn", "as"]) {
    const badge = render(BrandWordmark, lang);
    assert.ok(badge.includes(tt(lang, "brandName")));
    assert.doesNotMatch(badge, /साथी · বন্ধু/);
    for (const component of [CivicNew, Locker]) {
      const html = render(component, lang).replace(/<option\b[^>]*>[\s\S]*?<\/option>/g, "");
      assert.doesNotMatch(html, /Report a local issue|Scan into locker|Your documents/);
      if (lang === "hi") assert.doesNotMatch(html, /[\u0980-\u09ff]/);
      else assert.doesNotMatch(html, /[\u0900-\u0963\u0966-\u097f]/);
    }
  }
});

test("Buddy dock keeps one saving language selector", () => {
  const source = readFileSync(new URL("../src/buddy/BuddyDock.tsx", import.meta.url), "utf8");
  const header = source.slice(source.indexOf("<header"), source.indexOf("</header>"));
  assert.equal((header.match(/<select\b/g) || []).length, 1);
  assert.match(header, /setLanguage\(e\.target\.value as Lang\)/);
  assert.doesNotMatch(source, /quickLangs/);
});
