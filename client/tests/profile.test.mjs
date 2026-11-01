import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { tt } from "../src/ui-strings.ts";
import {
  profileEn,
  profileHi,
  profileBn,
  profileAs,
} from "../src/profile-strings.ts";
import {
  profileToForm,
  formToProfilePatch,
  profileInitials,
  profileCompleteness,
  missingProfileFields,
  profileFields,
} from "../src/profile-form.ts";

test("brand changes with the UI language, including installed app manifests", async () => {
  for (const [lang, name] of Object.entries({
    en: "Buddy",
    hi: "साथी",
    bn: "বন্ধু",
    as: "বন্ধু",
  })) {
    assert.equal(tt(lang, "brandName"), name);
    assert.ok(tt(lang, "chooseTalk").includes(name));
    assert.ok(tt(lang, "talkGreeting").includes(name));
    const manifest = JSON.parse(
      await readFile(
        new URL(`../public/manifest-${lang}.webmanifest`, import.meta.url),
        "utf8",
      ),
    );
    assert.equal(manifest.name, name);
    assert.equal(manifest.short_name, name);
    assert.equal(manifest.lang, lang);
  }
  assert.equal(tt("xx", "brandName"), "Buddy");
});

test("every profile field, option and message has all four UI translations", () => {
  for (const table of [profileHi, profileBn, profileAs]) {
    assert.deepEqual(Object.keys(table).sort(), Object.keys(profileEn).sort());
    assert.ok(
      Object.values(table).every(
        (value) => typeof value === "string" && value.trim(),
      ),
    );
  }
  for (const field of profileFields) assert.ok(profileEn[`field_${field}`]);
});

test("form mapping round trips false, zero, numbers, enums and education fields", () => {
  const original = {
    age: 0,
    gender: "female",
    annual_income: 0,
    is_student: false,
    is_bpl: false,
    land_acres: 0,
    is_minority: true,
    course: "BA",
    study_year: 2,
    institution_name: "College",
  };
  const form = profileToForm(original);
  assert.equal(form.age, "0");
  assert.equal(form.is_bpl, "false");
  assert.equal(form.state, "");
  assert.deepEqual(formToProfilePatch(form, original), {});
  assert.deepEqual(
    formToProfilePatch(
      {
        ...form,
        is_student: "true",
        study_year: "3",
        land_acres: "1.25",
        state: " Assam ",
      },
      original,
    ),
    { state: "Assam", is_student: true, study_year: 3, land_acres: 1.25 },
  );
});

test("clearing a field sends explicit null and preserves fields outside this form", () => {
  const data = {
    age: 30,
    occupation: "Farmer",
    education_level: "ug",
    institution_type: "government",
    disability_percent: 0,
  };
  const form = profileToForm(data);
  assert.deepEqual(
    formToProfilePatch({ ...form, age: "", occupation: "  " }, data),
    { age: null, occupation: null },
  );
  assert.equal("sensitive" in form, false);
  assert.equal("education_level" in formToProfilePatch(form, data), false);
});

test("invalid numeric and choice values cannot silently become null or invalid API values", () => {
  const form = profileToForm({});
  for (const [field, value] of [
    ["age", "121"],
    ["age", "1.5"],
    ["annual_income", "-1"],
    ["land_acres", "NaN"],
    ["study_year", "Infinity"],
    ["is_student", "maybe"],
    ["gender", "invalid"],
  ]) {
    assert.throws(
      () => formToProfilePatch({ ...form, [field]: value }, {}),
      new RegExp(field),
    );
  }
});

test("completeness counts false and zero as provided and omits study details for non-students", () => {
  assert.equal(profileCompleteness({}), 0);
  const missing = missingProfileFields({
    age: 0,
    annual_income: 0,
    is_student: false,
    is_bpl: false,
    land_acres: 0,
  });
  for (const field of [
    "age",
    "annual_income",
    "is_student",
    "is_bpl",
    "land_acres",
    "course",
    "study_year",
    "institution_name",
  ])
    assert.ok(!missing.includes(field));
  const filled = {
    age: 34,
    gender: "male",
    state: "Assam",
    district: "Kamrup",
    residence: "rural",
    annual_income: 0,
    is_bpl: false,
    caste: "general",
    is_minority: false,
    occupation: "Farmer",
    is_student: false,
    land_acres: 0,
  };
  assert.equal(profileCompleteness(filled), 100);
});

test("avatar uses only the API's decrypted full_name and has a neutral fallback", () => {
  assert.equal(
    profileInitials({ sensitive: { full_name: "  Anu Das  " } }),
    "AD",
  );
  assert.equal(profileInitials({ sensitive: { full_name: "साथी" } }), "स");
  assert.equal(profileInitials({ sensitive: {} }), "");
  assert.equal(profileInitials({ sensitive: { phone: "9999999999" } }), "");
});
