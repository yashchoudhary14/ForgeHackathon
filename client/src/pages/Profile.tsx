import { Text, languages, useApp } from "../context";
import { useEffect, useState } from "react";
import type { ChangeEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Mic, Plus, ShieldCheck } from "lucide-react";
import { getActivity, resolveLink } from "../api/alerts";
import { post, request } from "../api/client";
import type { LockerItem } from "../api/locker";
import type { ActivityItem, Lang, ProfileData, ProfileOut } from "../api/types";
import { PersonIcon, PillLink } from "../nav";
import {
  formToProfilePatch,
  missingProfileFields,
  numericFields,
  profileChoices,
  profileCompleteness,
  profileFields,
  profileGroups,
  profileInitials,
  profileToForm,
} from "../profile-form";
import type { ProfileField, ProfileForm } from "../profile-form";
import { Card, Eyebrow, PillButton } from "../ui";
import { tt } from "../ui-strings";

function ActivityLinks({ items, lang }: { items: ActivityItem[]; lang: Lang }) {
  if (!items.length)
    return <p className="text-ink-soft">{tt(lang, "profileNoActivity")}</p>;
  return (
    <ul className="m-0 list-none p-0">
      {items.map((item) => {
        const link = resolveLink(item.link);
        const content = (
          <>
            {item.title}
            <time
              className="block text-sm text-ink-soft"
              dateTime={item.updated_at}
            >
              {new Date(item.updated_at).toLocaleDateString(lang)}
            </time>
          </>
        );
        const className =
          "block min-h-11 border-b border-dashed border-line py-3 text-ink";
        return (
          <li key={`${item.type}-${item.id}`}>
            {link.to ? (
              <Link to={link.to} className={className}>
                {content}
              </Link>
            ) : link.href ? (
              <a
                href={link.href}
                className={className}
                target="_blank"
                rel="noreferrer"
              >
                {content}
              </a>
            ) : (
              <div className={className}>{content}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export default function Profile() {
  const { lang, setLang, mode, setMode, profileId, setProfileId } = useApp();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const nextPath = searchParams.get("next");
  const [profile, setProfile] = useState<ProfileOut | null>(null);
  const [fullName, setFullName] = useState("");
  const [form, setForm] = useState<ProfileForm>(() => profileToForm({}));
  const [originalData, setOriginalData] = useState<ProfileData>({});
  const [loading, setLoading] = useState(Boolean(profileId));
  const [loadError, setLoadError] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const [invalid, setInvalid] = useState<ProfileField | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [reset, setReset] = useState(false);
  const [revision, setRevision] = useState(0);
  const [profileRevision, setProfileRevision] = useState(0);
  const [activity, setActivity] = useState<ActivityItem[] | null>(null);
  const [activityError, setActivityError] = useState(false);
  const [documents, setDocuments] = useState<number | null>(null);
  const [documentsError, setDocumentsError] = useState(false);

  useEffect(() => {
    const c = new AbortController();
    setProfile(null);
    setFullName("");
    setForm(profileToForm({}));
    setOriginalData({});
    setLoadError(false);
    setSaved(false);
    setLoading(Boolean(profileId));
    if (!profileId) return () => c.abort();
    request<ProfileOut>(`/profile/${encodeURIComponent(profileId)}`, {
      signal: c.signal,
    })
      .then((out) => {
        if (!c.signal.aborted) {
          setProfile(out);
          setFullName(out.sensitive?.full_name ?? "");
          setForm(profileToForm(out.data));
          setOriginalData(out.data);
        }
      })
      .catch(() => {
        if (!c.signal.aborted) setLoadError(true);
      })
      .finally(() => {
        if (!c.signal.aborted) setLoading(false);
      });
    return () => c.abort();
  }, [profileId, profileRevision]);

  useEffect(() => {
    const c = new AbortController();
    setActivity(null);
    setDocuments(null);
    setActivityError(false);
    setDocumentsError(false);
    if (!profileId) return () => c.abort();
    getActivity(profileId, c.signal)
      .then((items) => {
        if (!c.signal.aborted) setActivity(items);
      })
      .catch(() => {
        if (!c.signal.aborted) setActivityError(true);
      });
    request<LockerItem[]>(
      `/locker?${new URLSearchParams({ profile_id: profileId })}`,
      { signal: c.signal },
    )
      .then((items) => {
        if (!c.signal.aborted) setDocuments(items.length);
      })
      .catch(() => {
        if (!c.signal.aborted) setDocumentsError(true);
      });
    return () => c.abort();
  }, [profileId, revision]);

  async function save() {
    setSaveError(false);
    setInvalid(null);
    setSaved(false);
    let data: Partial<ProfileData>;
    try {
      data = formToProfilePatch(form, originalData);
    } catch (error) {
      setInvalid((error as Error).message as ProfileField);
      return;
    }
    setBusy(true);
    try {
      const body = {
        data,
        sensitive: { full_name: fullName.trim() },
        language: lang,
        mode: mode || "manual",
      };
      const out = profileId
        ? await request<ProfileOut>(
            `/profile/${encodeURIComponent(profileId)}`,
            { method: "PUT", body: JSON.stringify(body) },
          )
        : await post<ProfileOut>("/profile", body);
      setProfile(out);
      setFullName(out.sensitive?.full_name ?? "");
      setForm(profileToForm(out.data));
      setOriginalData(out.data);
      setSaved(true);
      if (!profileId) setProfileId(out.id);
    } catch {
      setSaveError(true);
    } finally {
      setBusy(false);
    }
  }

  async function preference(next: {
    language?: Lang;
    mode?: "talk" | "manual";
  }) {
    setBusy(true);
    setSaveError(false);
    setSaved(false);
    try {
      if (profileId) {
        const out = await request<ProfileOut>(
          `/profile/${encodeURIComponent(profileId)}`,
          { method: "PUT", body: JSON.stringify(next) },
        );
        setProfile(out);
      }
      if (next.language) setLang(next.language);
      if (next.mode) setMode(next.mode);
      setSaved(true);
    } catch {
      setSaveError(true);
    } finally {
      setBusy(false);
    }
  }

  const missing = missingProfileFields(profile?.data ?? {});
  const completeness = profileCompleteness(profile?.data ?? {});
  const initials = profile ? profileInitials(profile) : "";
  const applications = activity?.filter((item) => item.type === "run") ?? [];
  const reports = activity?.filter((item) => item.type === "report") ?? [];
  const retry = (
    <PillButton tone="light" onClick={() => setRevision((v) => v + 1)}>
      {tt(lang, "tryAgain")}
    </PillButton>
  );

  return (
    <div className="flex flex-col gap-6" lang={lang}>
      <Card className="flex flex-col gap-5 !rounded-card border-2 border-ink border-t-[12px] !bg-card p-6 !shadow-none">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-4">
            <span
              className="grid h-20 w-16 shrink-0 place-items-center rounded-md border-2 border-dashed border-act bg-act-soft font-serif text-2xl font-bold text-act"
              aria-hidden="true"
            >
              {initials || <PersonIcon size={30} />}
            </span>
            <div className="flex flex-col gap-1">
              <div className="flex flex-wrap items-center gap-2">
                <Eyebrow>{tt(lang, "profilePassEyebrow")}</Eyebrow>
                {!loading && !loadError && (
                  <span className="inline-flex -rotate-2 items-center gap-1 rounded-lg border-[3px] border-double border-ok bg-card px-2 py-0.5 text-xs font-bold text-ok motion-reduce:rotate-0">
                    <ShieldCheck size={14} aria-hidden="true" />
                    {completeness}% · {profileFields.length - missing.length}/
                    {profileFields.length}
                  </span>
                )}
              </div>
              <h1 className="m-0 font-serif !font-bold leading-tight">{tt(lang, "profileTitle")}</h1>
              {profile?.sensitive?.full_name && (
                <p className="m-0 text-lg font-semibold">
                  {profile.sensitive.full_name}
                </p>
              )}
              <p className="m-0 text-ink-soft">{tt(lang, "profileSubtitle")}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <PillLink to="/talk" tone="saffron">
              <Mic size={18} aria-hidden="true" />
               <Text value="Complete by Voice with Buddy" /> </PillLink>
            {nextPath && profileId && (
              <PillLink to={nextPath} tone="dark">
                 <Text value="Continue →" /> </PillLink>
            )}
          </div>
        </div>
        <fieldset
          disabled={busy || loading || loadError}
          className="m-0 grid gap-4 border-0 border-t border-dashed border-line p-0 pt-4 sm:grid-cols-2"
        >
          <label className="min-w-0 flex-1" htmlFor="profile-language">
            {tt(lang, "profileLanguage")}
            <select
              id="profile-language"
              value={lang}
              onChange={(e) =>
                void preference({ language: e.target.value as Lang })
              }
              className="!mb-0 !min-h-11"
            >
              {Object.entries(languages).map(([value, label]) => (
                <option value={value} key={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="min-w-0 flex-1" htmlFor="profile-mode">
            {tt(lang, "profileMode")}
            <select
              id="profile-mode"
              value={mode || profile?.mode || "manual"}
              onChange={(e) =>
                void preference({ mode: e.target.value as "talk" | "manual" })
              }
              className="!mb-0 !min-h-11"
            >
              <option value="talk">{tt(lang, "profileTalk")}</option>
              <option value="manual">{tt(lang, "profileManual")}</option>
            </select>
          </label>
        </fieldset>
        {!loading && !loadError && (
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between text-sm font-semibold">
              <label htmlFor="profile-completeness" className="m-0">
                {tt(lang, "profileComplete")} · {completeness}%
              </label>
              <span className="text-xs text-ink-soft">
                {profileFields.length - missing.length} / {profileFields.length}{" "}
                 <Text value="fields saved" /> </span>
            </div>
            <progress
              id="profile-completeness"
              value={completeness}
              max={100}
              className="!h-3 w-full overflow-hidden rounded-full accent-[var(--color-ok)]"
            />
          </div>
        )}
        <div className="-mx-6 -mb-6 grid grid-cols-2 border-t-2 border-ink sm:grid-cols-4 [&>a]:!m-0 [&>a]:!min-h-12 [&>a]:!justify-start [&>a]:!rounded-none [&>a]:!border-0 [&>a]:!bg-transparent [&>a]:!px-4 [&>a]:!shadow-none [&>a:nth-child(odd)]:border-r [&>a:nth-child(odd)]:border-line [&>a:nth-child(-n+2)]:border-b [&>a:nth-child(-n+2)]:border-line sm:[&>a]:border-r sm:[&>a]:border-line sm:[&>a:nth-child(-n+2)]:border-b-0">
          <PillLink to="/locker" tone="light" className="!min-h-11 !px-4 text-xs">
            {tt(lang, "profileDocuments")}
            {documents !== null ? ` · ${documents}` : ""}
          </PillLink>
          <PillLink to="/runs" tone="light" className="!min-h-11 !px-4 text-xs">
            {tt(lang, "profileApplications")}
            {activity ? ` · ${applications.length}` : ""}
          </PillLink>
          <PillLink to="/civic" tone="light" className="!min-h-11 !px-4 text-xs">
            {tt(lang, "profileReports")}
            {activity ? ` · ${reports.length}` : ""}
          </PillLink>
          <PillLink to="/alerts" tone="light" className="!min-h-11 !px-4 text-xs">
            {tt(lang, "navAlerts")}
          </PillLink>
        </div>
      </Card>
      {loading && <p role="status">{tt(lang, "loading")}</p>}
      {loadError && (
        <div role="alert">
          <p>{tt(lang, "profileLoadError")}</p>
          <PillButton
            tone="light"
            onClick={() => setProfileRevision((v) => v + 1)}
          >
            {tt(lang, "tryAgain")}
          </PillButton>
        </div>
      )}
      {saveError && (
        <p role="alert" className="text-bad">
          {tt(lang, "profileSaveError")}
        </p>
      )}
      {saved && (
        <p role="status" className="text-ok">
          {tt(lang, "profileSaved")}
        </p>
      )}
      {!loading && !loadError && (
        <>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void save();
            }}
          >
            <fieldset disabled={busy} className="m-0 min-w-0 border-0 p-0">
              <label htmlFor="profile-full-name">
                {tt(lang, "fullName")}
                <input
                  id="profile-full-name"
                  type="text"
                  autoComplete="name"
                  value={fullName}
                  onChange={(e) => {
                    setFullName(e.target.value);
                    setSaved(false);
                  }}
                />
              </label>
              <div className="grid gap-5 lg:grid-cols-2">
                {profileGroups.map((group) => (
                  <Card key={group.title} className="!rounded-card border border-line !bg-card !shadow-none">
                    <h2 className="-mx-5 mb-5 border-b-2 border-ink px-5 pb-3 font-serif text-2xl font-bold sm:-mx-6 sm:px-6">
                      {tt(lang, group.title)}
                    </h2>
                    <div className="grid gap-x-4 sm:grid-cols-2">
                      {group.fields.map((field) => {
                        const choices: readonly string[] | undefined =
                          field in profileChoices
                            ? profileChoices[
                                field as keyof typeof profileChoices
                              ]
                            : undefined;
                        const numeric =
                          field in numericFields
                            ? numericFields[field as keyof typeof numericFields]
                            : undefined;
                        const attrs = {
                          id: `profile-${field}`,
                          name: field,
                          value: form[field],
                          onChange: (
                            e: ChangeEvent<
                              HTMLInputElement | HTMLSelectElement
                            >,
                          ) => {
                            setForm((current) => ({
                              ...current,
                              [field]: e.target.value,
                            }));
                            setSaved(false);
                            setInvalid(null);
                          },
                          "aria-invalid": invalid === field || undefined,
                          "aria-describedby":
                            invalid === field
                              ? "profile-validation"
                              : undefined,
                          className: "!min-h-12 !text-base",
                        };
                        return (
                          <label htmlFor={attrs.id} key={field}>
                            {tt(lang, `field_${field}`)}
                            {choices ? (
                              <select {...attrs}>
                                <option value="">
                                  {tt(lang, "profileUnknown")}
                                </option>
                                {choices.map((value) => (
                                  <option value={value} key={value}>
                                    {tt(
                                      lang,
                                      value === "true"
                                        ? "profileYes"
                                        : value === "false"
                                          ? "profileNo"
                                          : `option_${value}`,
                                    )}
                                  </option>
                                ))}
                              </select>
                            ) : (
                              <input
                                {...attrs}
                                type={numeric ? "number" : "text"}
                                min={numeric ? 0 : undefined}
                                max={field === "age" ? 120 : undefined}
                                step={numeric?.step}
                              />
                            )}
                          </label>
                        );
                      })}
                    </div>
                  </Card>
                ))}
              </div>
              {invalid && (
                <p
                  id="profile-validation"
                  role="alert"
                  className="mt-4 text-bad"
                >
                  {tt(lang, "profileInvalid")} {tt(lang, `field_${invalid}`)}
                </p>
              )}
              <PillButton type="submit" className="mt-5 !min-h-12 w-full text-base sm:w-auto">
                {tt(
                  lang,
                  busy
                    ? "loading"
                    : profileId
                      ? "profileSave"
                      : "profileCreate",
                )}
              </PillButton>
            </fieldset>
          </form>
          <Card className="flex flex-col gap-3 !rounded-card border-l-[6px] border-saffron !bg-peach !shadow-none">
            <h2 className="m-0 font-serif text-2xl font-bold">
              {tt(lang, "profileMissing")}
            </h2>
            <p className="m-0 text-ink-soft">
              {tt(
                lang,
                missing.length ? "profileMissingHint" : "profileAllDone",
              )}
            </p>
            {missing.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {missing.map((field) => (
                  <a
                    key={field}
                    href={`#profile-${field}`}
                    onClick={(e) => {
                      const el = document.getElementById(`profile-${field}`);
                      if (el) {
                        e.preventDefault();
                        el.scrollIntoView({ behavior: "smooth", block: "center" });
                        el.focus();
                      }
                    }}
                    className="inline-flex min-h-11 items-center gap-1.5 rounded-full border border-dashed border-saffron-text bg-card px-3.5 py-1.5 text-xs font-semibold text-saffron-text no-underline transition-colors hover:bg-saffron/15"
                  >
                    <Plus size={14} aria-hidden="true" />
                    {tt(lang, `field_${field}`)}
                  </a>
                ))}
              </div>
            )}
            <div className="pt-1">
              <PillLink to="/schemes" tone="light">
                {tt(lang, "navSchemes")} →
              </PillLink>
            </div>
          </Card>
        </>
      )}
      {profileId && (
        <>
          <Card className="!rounded-tile border border-line !bg-transparent !shadow-none">
            <div className="flex flex-wrap gap-3">
              <PillLink to="/locker" tone="light">
                {tt(lang, "profileDocuments")}
                {documents !== null ? ` · ${documents}` : ""}
              </PillLink>
              <PillLink to="/runs" tone="light">
                {tt(lang, "profileApplications")}
                {activity ? ` · ${applications.length}` : ""}
              </PillLink>
              <a
                href="#profile-reports"
                className="inline-flex min-h-12 items-center rounded-full border border-line bg-card px-6 font-semibold text-ink"
              >
                {tt(lang, "profileReports")}
                {activity ? ` · ${reports.length}` : ""}
              </a>
              <PillLink to="/alerts" tone="light">
                {tt(lang, "navAlerts")}
              </PillLink>
            </div>
            {documentsError && (
              <p role="alert" className="mt-3">
                {tt(lang, "profileDocumentsError")}
              </p>
            )}
            {documents === null && !documentsError && (
              <p role="status" className="mt-3">
                {tt(lang, "profileDocuments")}: {tt(lang, "loading")}
              </p>
            )}
          </Card>
          <div className="grid gap-5 md:grid-cols-2">
            <Card className="!rounded-card border border-line !bg-card !shadow-none">
              <h2 className="font-serif font-bold">{tt(lang, "profileApplications")}</h2>
              {activity && <ActivityLinks items={applications} lang={lang} />}
            </Card>
            <section id="profile-reports" className="scroll-mt-28">
              <Card className="!rounded-card border border-line !bg-card !shadow-none">
                <h2 className="font-serif font-bold">{tt(lang, "profileReports")}</h2>
                {activity && <ActivityLinks items={reports} lang={lang} />}
              </Card>
            </section>
          </div>
          {activityError && (
            <p role="alert">{tt(lang, "profileActivityError")}</p>
          )}
          {!activity && !activityError && (
            <p role="status">{tt(lang, "loading")}</p>
          )}
          {(activityError || documentsError) && retry}
        </>
      )}
      <Card className="!rounded-none border-t border-line !bg-transparent !px-0 !shadow-none">
        <PillButton tone="ghost" disabled={busy} onClick={() => setReset(true)}>
          {tt(lang, "profileReset")}
        </PillButton>
        {reset && (
          <div className="mt-4">
            <p>{tt(lang, "profileResetHint")}</p>
            <div className="flex flex-wrap gap-3">
              <PillButton
                disabled={busy}
                onClick={() => {
                  setProfileId("");
                  navigate("/welcome");
                }}
              >
                {tt(lang, "profileResetConfirm")}
              </PillButton>
              <PillButton tone="light" onClick={() => setReset(false)}>
                {tt(lang, "profileCancel")}
              </PillButton>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
