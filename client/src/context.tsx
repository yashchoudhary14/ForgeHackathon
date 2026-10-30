import { createContext, useContext, useState, useEffect } from "react";
import { translate } from "./i18n";
import type { ReactNode } from "react";
import type { Lang } from "./api/types";
export const languages: Record<Lang, string> = {
  en: "English",
  hi: "हिन्दी",
  bn: "বাংলা",
  ta: "தமிழ்",
  te: "తెలుగు",
  mr: "मराठी",
  gu: "ગુજરાતી",
  kn: "ಕನ್ನಡ",
  ml: "മലയാളം",
  pa: "ਪੰਜਾਬੀ",
  od: "ଓଡ଼ିଆ",
};
const strings = {
  en: {
    home: "Find my schemes",
    schemes: "My schemes",
    explain: "Explain a document",
    ask: "Ask a question",
    runs: "My applications",
    retry: "Try again",
    loading: "Please wait…",
    mic: "Speak",
    stop: "Stop recording",
    send: "Send",
    save: "Save profile",
    intro: "Your rights. Within reach.",
    subtitle:
      "Tell us a little about yourself. Discover government schemes, understand your rights, and get help applying.",
    language: "Language",
    start: "Tell us about yourself",
    hint: "Your age, state, work, and family income help us find relevant schemes.",
    find: "Find my schemes",
  },
  hi: {
    home: "योजनाएँ खोजें",
    schemes: "मेरी योजनाएँ",
    explain: "दस्तावेज़ समझें",
    ask: "सवाल पूछें",
    runs: "मेरे आवेदन",
    retry: "फिर कोशिश करें",
    loading: "कृपया प्रतीक्षा करें…",
    mic: "बोलें",
    stop: "रिकॉर्डिंग रोकें",
    send: "भेजें",
    save: "प्रोफ़ाइल सहेजें",
    intro: "आपके अधिकार। अब आपकी पहुँच में।",
    subtitle:
      "अपने बारे में बताएँ। सरकारी योजनाएँ खोजें, अपने अधिकार समझें और आवेदन में मदद पाएँ।",
    language: "भाषा",
    start: "अपने बारे में बताएँ",
    hint: "आपकी उम्र, राज्य, काम और परिवार की आय से सही योजनाएँ खोजने में मदद मिलेगी।",
    find: "मेरी योजनाएँ खोजें",
  },
};
function stored(key: string, fallback: string) {
  try {
    return localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}
export function persist(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* Private browsing may disable storage. */
  }
}
const Context = createContext({
  lang: "en" as Lang,
  setLang: (_l: Lang) => {},
  profileId: "",
  setProfileId: (_id: string) => {},
  t: strings.en,
});
export function Provider({ children }: { children: ReactNode }) {
  const [lang, setLanguage] = useState<Lang>(
    stored("adhikaar-language", "en") in languages
      ? (stored("adhikaar-language", "en") as Lang)
      : "en",
  );
  const [profileId, setId] = useState(stored("adhikaar-profile", ""));
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  return (
    <Context.Provider
      value={{
        lang,
        setLang: (l) => {
          setLanguage(l);
          persist("adhikaar-language", l);
          document.documentElement.lang = l;
        },
        profileId,
        setProfileId: (id) => {
          setId(id);
          persist("adhikaar-profile", id);
        },
        t: lang === "hi" ? strings.hi : strings.en,
      }}
    >
      {children}
    </Context.Provider>
  );
}
export const useApp = () => useContext(Context);
export function Text({ value }: { value: string }) {
  const { lang } = useApp();
  return translate(value, lang);
}
