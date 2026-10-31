// Interface strings for the Dawn UI. English is the fallback for every key;
// hi, bn and as cover the navigation and Talk mode chrome.
import { hi } from "./ui-strings-hi";
import { bn, as } from "./ui-strings-bn";

export const en = {
  mainNav: "Main navigation",
  navTalk: "Talk",
  navSchemes: "Schemes",
  navDocuments: "Documents",
  navCivic: "Civic",
  navAlerts: "Alerts",
  navForYou: "For you",
  navExplain: "Explain",
  navApplications: "Applications",
  navLocker: "Locker",
  navCivicMap: "Civic map",
  talkMode: "Talk mode",
  verdictEligible: "Eligible",
  verdictLikely: "Likely",
  verdictNot: "Not eligible",
  verdictUnknown: "Need more info",
  playAudio: "Play audio",
  cropAlt: "The part of the portal that needs your help",
  loading: "Please wait…",
  tryAgain: "Try again",
  chooseTitle: "How would you like to use Adhikaar?",
  chooseSub: "You can change this any time.",
  chooseTalk: "Talk to Sahayak",
  chooseTalkSub: "Speak in your own language. Sahayak does the rest.",
  chooseManual: "I'll use the site myself",
  chooseManualSub: "Browse schemes, documents and reports on your own.",
  talkTitle: "Sahayak",
  holdToTalk: "Hold to talk",
  release: "Release to send",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking…",
  typeInstead: "Or type here",
  typePlaceholder: "Type your message",
  send: "Send",
  langDetected: "Language detected",
  changeLang: "Change",
  talkEmpty: "Press and hold the microphone, then speak.",
  micDenied: "Microphone not available. Please type your message.",
  talkError: "Sahayak could not answer. Please try again.",
  openScheme: "See details",
  openRun: "Open the form",
  openReport: "Open the report",
  sendDocument: "Add to locker",
  needHelp: "We need your help",
  writeHere: "Type here",
  sendAnswer: "Send",
  doItMyself: "I'll do it on the screen",
  swipeSubmit: "Swipe to submit",
  swipeUpload: "Swipe to attach",
  attachDoc: "This document will be attached",
  alertsTitle: "Alerts",
  alertsEmpty: "No alerts yet.",
  unavailable: "This is not available yet. Please try again later.",
} as const;
export type UiKey = keyof typeof en;
export type Table = Partial<Record<UiKey, string>>;
const tables: Record<string, Table> = { hi, bn, as };
export function tt(lang: string, key: UiKey | string): string {
  const k = key as UiKey;
  return tables[lang]?.[k] ?? en[k] ?? String(key);
}
