import type { ClientMessage, Human } from "../api/types";
import { GuideCard, SwipeToConfirm } from "../guide";
import { useApp } from "../context";
import { tt } from "../ui-strings";

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
  onDone: (type: "resume" | "approve" | "abort") => void;
}) {
  const { lang } = useApp();
  const gl = human.guide?.lang || lang;
  const ui = (k: string) => tt(gl, k);
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
      className="my-4"
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
          <p className="m-0 rounded-[14px] bg-white p-3 font-semibold">
            {ui("attachDoc")}: {doc.title || doc.doc_type}
          </p>
        )}
        {human.kind === "confirm_submit" || human.kind === "confirm_upload" ? (
          <>
            <SwipeToConfirm
              label={
                human.kind === "confirm_submit"
                  ? ui("swipeSubmit")
                  : ui("swipeUpload")
              }
              disabled={!connected}
              onConfirm={() => onDone("approve")}
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
                className="flex gap-2"
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
                  className="!m-0 flex-1 !rounded-full !border-[#c9d6f2] !px-5"
                />
                <button
                  type="submit"
                  disabled={!answer.trim() || !connected}
                  className="!bg-act !text-white"
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
              {(takeover || human.kind === "payment") && (
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
