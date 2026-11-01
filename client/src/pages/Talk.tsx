import { useBuddy } from "../buddy/context";
import { buddyText } from "../buddy/strings";
import { useApp } from "../context";

/** The shared conversation lives in Shell; this route never mounts a second mic. */
export default function Talk() {
  const { setOpen } = useBuddy();
  const { lang } = useApp();
  return <div className="mx-auto max-w-xl px-5 py-10">
    <h1>{buddyText(lang, "name")}</h1>
    <p>{buddyText(lang, "greeting")}</p>
    <button onClick={() => setOpen(true)}>{buddyText(lang, "voice")}</button>
    <p>{buddyText(lang, "tap")}</p>
  </div>;
}
