import { useEffect } from "react";
import { useBuddy } from "../buddy/context";
import { buddyText } from "../buddy/strings";
import { useApp } from "../context";

/** The shared conversation lives in Shell (BuddyDock); this route never mounts a second mic. */
export default function Talk() {
  const { setOpen } = useBuddy();
  const { lang } = useApp();
  useEffect(() => {
    setOpen(true);
  }, [setOpen]);
  return (
    <div className="sr-only">
      <h1>{buddyText(lang, "name")}</h1>
      <p>{buddyText(lang, "greeting")}</p>
    </div>
  );
}
