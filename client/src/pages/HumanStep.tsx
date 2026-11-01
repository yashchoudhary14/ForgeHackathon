import type { ClientMessage, Human } from "../api/types";
import { GuideCard, SwipeToConfirm } from "../guide";
import { Text, useApp } from "../context";
import { tt } from "../ui-strings";
import { formatKb } from "../api/locker";

/** The "your help is needed" panel of the run screen (Agent + Approve designs). */
export default function HumanStep({
  human,
  connected,
  answer,
  setAnswer,
  takeover,
  onTakeOver,
  send,
  onDone,
}: {
  human: Human;
  connected: boolean;
  answer: string;
  setAnswer: (v: string) => void;
  takeover: boolean;
  onTakeOver: () => void;
  send: (m: ClientMessage) => boolean;
  onDone: (type: "resume" | "approve" | "approve_duplicate" | "abort") => void;
}) {
  const { lang } = useApp();
  const gl = human.guide?.lang || lang;
  const ui = (k: string) => tt(lang, k);
  const title =
    human.guide?.title ||
    (human.kind === "confirm_submit"
      ? ui("reviewSubmit")
      : human.kind === "confirm_upload"
        ? ui("attachDoc")
        : ui("needHelp"));
  const typed =
    human.kind === "captcha" ||
    human.kind === "otp" ||
    human.kind === "missing_field" ||
    human.kind === "login";
  const doc = human.document;
  return (
    <section
      id="human-step"
      role="alert"
      tabIndex={-1}
      aria-label={title}
      className="my-5 scroll-mt-4 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-act"
    >
      <GuideCard
        title={title}
        steps={human.guide?.steps}
        crop={human.crop}
        audioUrl={human.audio_url}
        lang={gl}
      >
        {human.message && <p className="m-0">{human.message}</p>}
        {human.kind === "confirm_upload" && doc && (
          <div className="flex flex-col gap-1 rounded-tile border border-line bg-card p-3">
            <span className="text-sm text-ink-soft">{ui("attachDoc")}</span>
            <strong className="font-serif text-xl font-bold capitalize">
              {doc.title || <Text value={doc.doc_type.replaceAll("_", " ")} />}
            </strong>
            <span className="text-sm text-ink-soft">
              {String(doc.format).toUpperCase()}
              {doc.bytes ? ` · ${formatKb(doc.bytes)}` : ""}
              {doc.meta?.readable === false ? ` · ${ui("docHardToRead")}` : ""}
            </span>
          </div>
        )}
        {human.duplicate_warning && (
          <p role="alert" className="m-0 rounded-tile border border-warn/40 bg-warn-soft p-3 font-medium text-warn">
            {human.duplicate_warning}
          </p>
        )}
        {human.capture_required ? (
          <button type="button" disabled={!connected} onClick={() => window.dispatchEvent(new Event("buddy:capture"))}>
            {ui("sendDocument")}
          </button>
        ) : human.kind === "confirm_submit" || human.kind === "confirm_upload" ? (
          <>
            <SwipeToConfirm
              label={
                human.kind === "confirm_submit"
                  ? ui("swipeSubmit")
                  : ui("swipeUpload")
              }
              disabled={!connected}
              onConfirm={() =>
                onDone(human.duplicate_warning ? "approve_duplicate" : "approve")
              }
            />
            <button
              type="button"
              className="secondary"
              disabled={!connected}
              onClick={() => onDone("abort")}
            >
              {tt(lang, "abort")}
            </button>
          </>
        ) : (
          <>
            {typed && human.kind !== "login" && (
              <form
                className="flex flex-wrap gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (answer.trim() && send({ type: "human_input", value: answer }))
                    setAnswer("");
                }}
              >
                <label htmlFor="human-answer" className="sr-only">
                  {human.field || ui("writeHere")}
                </label>
                <input
                  id="human-answer"
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  placeholder={ui("writeHere")}
                  type={human.kind === "otp" ? "password" : "text"}
                  autoComplete={human.kind === "otp" ? "one-time-code" : "off"}
                  inputMode={human.kind === "otp" ? "numeric" : undefined}
                  required
                  className="!m-0 !min-h-14 min-w-0 basis-40 flex-1 !rounded-tile !border-2 !border-act/40 !bg-card !px-5 text-center !text-xl font-semibold tracking-[0.2em] focus:!border-act"
                />
                <button
                  type="submit"
                  disabled={!answer.trim() || !connected}
                  className="!min-h-14 !rounded-full !bg-act !px-6 !text-white"
                >
                  {ui("sendAnswer")}
                </button>
              </form>
            )}
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="secondary"
                disabled={!connected}
                onClick={onTakeOver}
              >
                {ui("doItMyself")}
              </button>
              {(takeover || human.kind === "payment" || human.kind === "login") && (
                <button
                  type="button"
                  disabled={!connected}
                  onClick={() => onDone("resume")}
                >
                  {tt(lang, "continueBtn")}
                </button>
              )}
            </div>
          </>
        )}
      </GuideCard>
    </section>
  );
}
