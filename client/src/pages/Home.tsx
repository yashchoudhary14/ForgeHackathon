import { Link } from "react-router-dom";
import { FileText, MapPin, Mic, MousePointerClick, Bot } from "lucide-react";
import { useApp } from "../context";
import { Card, Eyebrow } from "../ui";
import { PillLink } from "../nav";
import { tt } from "../ui-strings";
import Intake from "./Intake";

const jobs = [
  {
    title: "Understand",
    tint: "bg-paper shadow-[inset_0_0_0_1px_#ede5da]",
    icon: FileText,
    text: "Upload a notice or paste a gov link. Get your rights, duties and deadlines in plain language, what changes for you, and every point backed by a quote.",
  },
  {
    title: "Act",
    tint: "bg-act-soft",
    icon: Bot,
    text: "The agent opens the portal, fills it from your saved profile and documents, guides you through CAPTCHA and OTP, and submits only after you approve.",
  },
  {
    title: "Speak up",
    tint: "bg-[#f2f8e1]",
    icon: MapPin,
    text: "Report a local problem with a photo or your voice. Neighbours confirm it, the agent files it on CPGRAMS and you track the official reply.",
  },
];

/** Home: the Dawn hero, the two ways to use Adhikaar, then the profile form. */
export default function Home() {
  const { lang } = useApp();
  return (
    <div className="-mx-4 -mt-6 md:-mx-8">
      <section
        className="px-5 pb-20 pt-14 text-center md:pt-20"
        style={{
          background:
            "linear-gradient(180deg,#F7A35C 0%,#FFC994 38%,#FBE6D2 70%,#FBF6EE 100%)",
        }}
      >
        <div className="mx-auto flex max-w-3xl flex-col items-center gap-5">
          <span className="rounded-full bg-[#ffe7d3] px-4 py-2 text-[13px] font-semibold text-saffron-text">
            For every citizen · in your own language
          </span>
          <h1 className="mx-auto text-[clamp(2.6rem,9vw,5.6rem)]">
            Your rights, explained.
            <br />
            <em>Your forms, done.</em>
          </h1>
          <p className="m-0 max-w-xl text-xl text-ink-soft">
            Tell Adhikaar who you are, by voice or text, in Hindi, Bengali,
            Assamese or any Indian language. It finds what you are entitled to,
            explains it with official proof, and fills the government form with
            you.
          </p>
          <div className="mt-2 flex flex-wrap justify-center gap-3">
            <PillLink to="/talk" className="!min-h-14 !px-7 text-[17px]">
              <Mic size={20} aria-hidden="true" />
              {tt(lang, "chooseTalk")}
            </PillLink>
            <a
              href="#get-started"
              className="inline-flex min-h-14 items-center gap-2 rounded-full bg-white/85 px-7 text-[17px] font-semibold no-underline"
              style={{ color: "#17140f" }}
            >
              <MousePointerClick size={20} aria-hidden="true" />
              {tt(lang, "chooseManual")}
            </a>
          </div>
        </div>
      </section>
      <section className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 md:px-8">
        <div className="flex flex-col items-center gap-2 text-center">
          <Eyebrow>One assistant, three jobs</Eyebrow>
          <h2 className="text-[clamp(2rem,6vw,3.2rem)]">
            Understand. Act. Speak up.
          </h2>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          {jobs.map(({ title, tint, icon: Icon, text }) => (
            <div
              key={title}
              className={`flex flex-col gap-3 rounded-[28px] p-6 ${tint}`}
            >
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-white/70">
                <Icon aria-hidden="true" />
              </span>
              <h3 className="m-0 font-serif text-3xl font-normal">{title}</h3>
              <p className="m-0 text-ink-soft">{text}</p>
            </div>
          ))}
        </div>
      </section>
      <section
        id="get-started"
        className="mx-auto max-w-6xl scroll-mt-20 px-4 pb-10 md:px-8"
      >
        <Card tint="peach" className="mb-6">
          <p className="m-0">
            <Link to="/explain">Have a notice? Understand it first →</Link>
          </p>
        </Card>
        <Intake />
      </section>
    </div>
  );
}
