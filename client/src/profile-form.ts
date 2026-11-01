import type { ProfileData, ProfileOut } from "./api/types";

export const profileGroups = [
  {
    title: "profileAbout",
    fields: ["age", "gender", "state", "district", "residence"],
  },
  {
    title: "profileFamily",
    fields: ["annual_income", "is_bpl", "caste", "is_minority"],
  },
  {
    title: "profileEducation",
    fields: [
      "occupation",
      "is_student",
      "course",
      "study_year",
      "institution_name",
    ],
  },
  { title: "profileLand", fields: ["land_acres"] },
] as const;
export type ProfileField = (typeof profileGroups)[number]["fields"][number];
export type ProfileForm = Record<ProfileField, string>;
export const numericFields = {
  age: { max: 120, step: 1 },
  annual_income: { step: 1 },
  study_year: { step: 1 },
  land_acres: { step: 0.01 },
} as const;
export const profileChoices = {
  gender: ["male", "female", "transgender"],
  residence: ["urban", "rural"],
  caste: ["general", "obc", "sc", "st", "pvtg", "dnt"],
  is_bpl: ["true", "false"],
  is_minority: ["true", "false"],
  is_student: ["true", "false"],
} as const;
export const profileFields: ProfileField[] =
  profileGroups.flatMap<ProfileField>((group) => [...group.fields]);

/** Keep zero and false distinct from unknown; never put sensitive fields in this form. */
export function profileToForm(data: ProfileData): ProfileForm {
  return Object.fromEntries(
    profileFields.map((field) => [
      field,
      data[field] == null ? "" : String(data[field]),
    ]),
  ) as ProfileForm;
}

/** Only send changed fields, so unrelated data added by Talk is preserved. Null clears a value. */
export function formToProfilePatch(
  form: ProfileForm,
  original: ProfileData,
): Partial<ProfileData> {
  const patch: Record<string, string | number | boolean | null> = {};
  for (const field of profileFields) {
    const text = form[field].trim();
    let value: string | number | boolean | null = text || null;
    if (text && field in numericFields) {
      const number = Number(text);
      if (
        !Number.isFinite(number) ||
        number < 0 ||
        (field !== "land_acres" && !Number.isInteger(number)) ||
        (field === "age" && number > 120)
      )
        throw new Error(field);
      value = number;
    } else if (text && field in profileChoices) {
      const choices: readonly string[] =
        profileChoices[field as keyof typeof profileChoices];
      if (!choices.includes(text)) throw new Error(field);
      value = text === "true" ? true : text === "false" ? false : text;
    }
    if (value !== (original[field] ?? null)) patch[field] = value;
  }
  return patch as Partial<ProfileData>;
}

export function missingProfileFields(data: ProfileData): ProfileField[] {
  return profileFields.filter((field) => {
    if (
      data.is_student === false &&
      ["course", "study_year", "institution_name"].includes(field)
    )
      return false;
    return data[field] == null || data[field] === "";
  });
}
export function profileCompleteness(data: ProfileData): number {
  const total = profileFields.length - (data.is_student === false ? 3 : 0);
  return Math.round(
    ((total - missingProfileFields(data).length) / total) * 100,
  );
}
export function profileInitials(
  profile: Pick<ProfileOut, "sensitive">,
): string {
  return (profile.sensitive?.full_name ?? "")
    .trim()
    .split(/\s+/u)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => Array.from(part)[0])
    .join("");
}
