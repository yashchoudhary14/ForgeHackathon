import type { Lang } from "./api/types";
import { tt } from "./ui-strings";
// Navigation and Talk mode chrome (en, hi, bn, as) live in ui-strings*.ts; `tt` is the lookup.
export { tt } from "./ui-strings";
// English is also the fallback for the other supported intake/answer languages.
const hi: Record<string, string> = {
  "The receipt image is unavailable. Your reference and official link are still shown above.":
    "रसीद की तस्वीर उपलब्ध नहीं है। आपका संदर्भ और आधिकारिक लिंक ऊपर दिए गए हैं।",
  "Retry receipt image": "रसीद की तस्वीर फिर लाएँ",
  "This application was stopped. You can start again from a scheme page.":
    "यह आवेदन रोक दिया गया है। योजना के पेज से फिर शुरू कर सकते हैं।",
  "Preparing your voice message…": "आपका आवाज़ का संदेश तैयार कर रहे हैं…",
  "This live session has ended. Your saved steps are still available. Start a new application from the scheme page when you’re ready.":
    "यह लाइव सत्र समाप्त हो गया है। सहेजे हुए चरण अब भी उपलब्ध हैं। तैयार होने पर योजना के पेज से नया आवेदन शुरू करें।",
  "Selecting a field or button": "खाना या बटन चुन रहे हैं",
  "Filling in your details": "आपकी जानकारी भर रहे हैं",
  "Choosing an option": "विकल्प चुन रहे हैं",
  "Checking the next section": "अगला भाग जाँच रहे हैं",
  "Opening a portal page": "पोर्टल का पेज खोल रहे हैं",
  "Waiting for the portal": "पोर्टल का इंतज़ार है",
  "Waiting for your help": "आपकी मदद का इंतज़ार है",
  "Waiting for your approval": "आपकी मंज़ूरी का इंतज़ार है",
  "Finishing the application": "आवेदन पूरा कर रहे हैं",
  "Working on the portal": "पोर्टल पर काम कर रहे हैं",
  "Please enter a valid age.": "कृपया सही उम्र भरें।",
  "Please enter a valid annual income.": "कृपया सही सालाना आय भरें।",
  "Please enter a valid disability percent.":
    "कृपया सही दिव्यांगता प्रतिशत भरें।",
  "Please enter a valid land acres.": "कृपया ज़मीन का सही क्षेत्रफल भरें।",
  Start: "शुरू करें",
  Understand: "समझें",
  Decide: "तय करें",
  Act: "आवेदन करें",
  "Explain any scheme or notice in your language.":
    "किसी भी योजना या सूचना को अपनी भाषा में समझें।",
  "Find schemes you qualify for, with quotes from official sources.":
    "अपने लिए पात्र योजनाएँ खोजें, आधिकारिक स्रोतों के उद्धरणों के साथ।",
  "Watch the agent fill the portal. You approve before submit.":
    "साथी को पोर्टल भरते हुए देखें। जमा करने से पहले मंज़ूरी आप दें।",
  "Have a notice? Understand it first →": "कोई सूचना मिली है? पहले उसे समझें →",
  "Fill in details instead": "जानकारी खुद भरें",
  "Understanding your details and building your profile…":
    "आपकी जानकारी समझकर प्रोफ़ाइल बना रहे हैं…",
  "Saving your profile securely…": "आपकी जानकारी सुरक्षित रूप से सहेज रहे हैं…",
  "Loading your saved profile…": "आपकी सहेजी हुई जानकारी ला रहे हैं…",
  "Opening your page…": "आपका पेज खोल रहे हैं…",
  "Let’s try that again": "आइए, फिर कोशिश करें",
  "Try again": "फिर कोशिश करें",
  "The service is taking a break. Please try again in a moment.":
    "सेवा अभी उपलब्ध नहीं है। थोड़ी देर बाद फिर कोशिश करें।",
  "Lots of people are asking for help right now. Please wait a moment and try again.":
    "अभी बहुत से लोग मदद माँग रहे हैं। थोड़ा रुककर फिर कोशिश करें।",
  "We couldn’t find that item. Go back to the list or try again.":
    "यह जानकारी नहीं मिली। सूची पर वापस जाएँ या फिर कोशिश करें।",
  "Please check the details you entered and try again.":
    "अपनी भरी हुई जानकारी जाँचें और फिर कोशिश करें।",
  "Checking your profile against official scheme rules…":
    "आपकी जानकारी आधिकारिक योजना के नियमों से मिला रहे हैं…",
  "Searching official government schemes…":
    "आधिकारिक सरकारी योजनाएँ खोज रहे हैं…",
  "Loading benefits, eligibility and official application steps…":
    "लाभ, पात्रता और आधिकारिक आवेदन के चरण ला रहे हैं…",
  "Reading the official scheme and preparing your explanation…":
    "आधिकारिक योजना पढ़कर आपके लिए आसान भाषा में समझा रहे हैं…",
  "Opening the portal and starting your assisted application…":
    "पोर्टल खोलकर आपका आवेदन शुरू कर रहे हैं…",
  "Loading your applications and saved receipts…":
    "आपके आवेदन और सहेजी हुई रसीदें ला रहे हैं…",
  "Loading your uploaded documents…": "आपके अपलोड किए दस्तावेज़ ला रहे हैं…",
  "Fetching the latest official notices…": "ताज़ा आधिकारिक सूचनाएँ ला रहे हैं…",
  "What should the assistant do?": "साथी को क्या करना चाहिए?",
  "Restoring your application and connecting to the live browser…":
    "आपका आवेदन लाकर लाइव ब्राउज़र से जुड़ रहे हैं…",
  "You stay in control": "नियंत्रण आपके हाथ में",
  "The agent pauses for CAPTCHA, OTP and your approval before submission.":
    "साथी CAPTCHA, OTP और जमा करने से पहले आपकी मंज़ूरी के लिए रुकेगा।",
  "Restoring your next action…": "आपका अगला काम ला रहे हैं…",
  "No action needed from you yet": "अभी आपको कुछ करने की ज़रूरत नहीं है",
  "Reconnecting to retrieve the request. If it does not appear, try again.":
    "अनुरोध लाने के लिए दोबारा जुड़ रहे हैं। न दिखे तो फिर कोशिश करें।",
  "Watch the browser and steps below. We’ll show your next action here.":
    "नीचे ब्राउज़र और चरण देखें। आपका अगला काम यहाँ दिखेगा।",
  "Final approval": "अंतिम मंज़ूरी",
  "One-time password (OTP)": "वन टाइम पासवर्ड (OTP)",
  "You are in control": "नियंत्रण आपके पास है",
  "Watch live": "लाइव देखें",
  "Opening the portal. The live browser will appear here…":
    "पोर्टल खोल रहे हैं। लाइव ब्राउज़र यहाँ दिखेगा…",
  "This application has ended. Check the steps and receipt below.":
    "यह आवेदन समाप्त हो गया है। नीचे चरण और रसीद देखें।",
  "The answer was interrupted or timed out. You can retry.":
    "जवाब बीच में रुक गया या समय समाप्त हो गया। फिर कोशिश करें।",
  "Could not read a live update. Reconnect to restore the application view.":
    "लाइव अपडेट नहीं पढ़ पाए। आवेदन देखने के लिए दोबारा जुड़ें।",
  "The live connection is unavailable. Wait for reconnection before continuing.":
    "लाइव संपर्क उपलब्ध नहीं है। आगे बढ़ने से पहले दोबारा जुड़ने का इंतज़ार करें।",
  "Voice recording is unavailable in this browser. Please type your message.":
    "इस ब्राउज़र में आवाज़ रिकॉर्ड नहीं हो सकती। अपना संदेश लिखें।",
  "Microphone permission was denied. Allow microphone access in your browser or type below.":
    "माइक्रोफ़ोन की अनुमति नहीं मिली। ब्राउज़र में अनुमति दें या नीचे लिखें।",
  "Could not access the microphone. Please type below.":
    "माइक्रोफ़ोन नहीं खुल पाया। नीचे लिखें।",
  "More information needed:": "और जानकारी चाहिए:",
  "Match confidence ·": "मिलान का भरोसा ·",
  "schemes found": "योजनाएँ मिलीं",
  pages: "पृष्ठ",
  Step: "चरण",
  Reload: "फिर खोलें",
  "Something went wrong": "कुछ गड़बड़ हो गई",
  "Please reload this page to continue.": "आगे बढ़ने के लिए पेज फिर खोलें।",
  "Page not found": "पेज नहीं मिला",
  "Go home": "होम पर जाएँ",
  "Contact and application details": "संपर्क और आवेदन की जानकारी",
  "full name": "पूरा नाम",
  phone: "फ़ोन",
  email: "ईमेल",
  dob: "जन्मतिथि",
  address: "पता",
  "father name": "पिता का नाम",
  "bank ifsc": "बैंक IFSC",
  "Could not connect to the service. Check your connection and try again.":
    "सेवा से संपर्क नहीं हो पाया। इंटरनेट जाँचें और फिर कोशिश करें।",
  "The request timed out or was cancelled. Please try again.":
    "अनुरोध में बहुत समय लगा या रद्द हो गया। फिर कोशिश करें।",
  "To help us match:": "सही योजना खोजने के लिए:",
  "Official sources. Clear reasons. You stay in control.":
    "आधिकारिक स्रोत। स्पष्ट कारण। नियंत्रण आपके हाथ में।",
  "01 / ABOUT YOU": "01 / आपके बारे में",
  "02 / YOUR PROFILE": "02 / आपकी जानकारी",
  "Review and edit before finding schemes. Share only what you are comfortable sharing.":
    "योजनाएँ खोजने से पहले जानकारी जाँचें और बदलें। उतनी ही जानकारी दें जितनी आप देना चाहें।",
  "Your profile will appear here after you tell us about yourself.":
    "अपने बारे में बताने के बाद आपकी जानकारी यहाँ दिखेगी।",
  "Your profile is ready. Review it and find your schemes.":
    "आपकी जानकारी तैयार है। जाँचें और अपनी योजनाएँ खोजें।",
  "Find support for your next step, with reasons from official sources.":
    "अपने अगले कदम के लिए सहायता खोजें, आधिकारिक स्रोतों से कारणों के साथ।",
  "Search all government schemes": "सभी सरकारी योजनाओं में खोजें",
  Search: "खोजें",
  State: "राज्य",
  "Show my matches": "मेरे लिए योजनाएँ दिखाएँ",
  "Checking schemes against official rules…":
    "आधिकारिक नियमों के अनुसार योजनाएँ जाँच रहे हैं…",
  "Tell us about yourself to see schemes matched to you.":
    "अपने लिए योजनाएँ देखने के लिए अपने बारे में बताएँ।",
  "Create your profile →": "अपनी जानकारी जोड़ें →",
  "No matching schemes were returned. Update your profile or search above.":
    "अभी कोई योजना नहीं मिली। जानकारी बदलें या ऊपर खोजें।",
  "Why this matches you": "यह योजना आपके लिए क्यों है",
  "Documents you’ll need": "ज़रूरी दस्तावेज़",
  "Update profile": "जानकारी बदलें",
  "See benefits & apply →": "लाभ देखें और आवेदन करें →",
  "No schemes found. Try a different search.":
    "कोई योजना नहीं मिली। कुछ और खोजें।",
  Previous: "पिछला",
  Next: "अगला",
  "← My schemes": "← मेरी योजनाएँ",
  "Read official source ↗": "आधिकारिक स्रोत पढ़ें ↗",
  "Explain to me": "मुझे समझाएँ",
  "Explaining…": "समझा रहे हैं…",
  "Apply for me": "मेरे लिए आवेदन करें",
  "Choose the application portal": "आवेदन पोर्टल चुनें",
  "The assistant will fill the application while you watch. You approve the final submission.":
    "आपकी निगरानी में साथी आवेदन भरेगा। अंतिम सबमिशन की मंज़ूरी आप देंगे।",
  "Create a profile first →": "पहले अपनी जानकारी जोड़ें →",
  "Official application options": "आधिकारिक आवेदन विकल्प",
  "Enter another portal below": "नीचे दूसरा पोर्टल डालें",
  "Portal URL": "पोर्टल का लिंक",
  "Start application": "आवेदन शुरू करें",
  "Starting…": "शुरू हो रहा है…",
  Benefits: "लाभ",
  Eligibility: "पात्रता",
  Documents: "दस्तावेज़",
  "How to apply": "आवेदन कैसे करें",
  FAQs: "आम सवाल",
  Exclusions: "किसे लाभ नहीं मिलेगा",
  "Open application portal ↗": "आवेदन पोर्टल खोलें ↗",
  "No application steps available.": "आवेदन के चरण उपलब्ध नहीं हैं।",
  "No frequently asked questions available.": "आम सवाल उपलब्ध नहीं हैं।",
  "Make sense of government notices, one clear explanation at a time.":
    "सरकारी सूचनाएँ आसान भाषा में समझें।",
  "Upload a PDF or image": "PDF या तस्वीर अपलोड करें",
  "Or paste a government document URL": "या सरकारी दस्तावेज़ का लिंक डालें",
  "Clear file": "फ़ाइल हटाएँ",
  "Reading and explaining…": "पढ़ और समझा रहे हैं…",
  "Explain this document": "यह दस्तावेज़ समझाएँ",
  "Your uploaded documents": "आपके अपलोड किए दस्तावेज़",
  "No documents uploaded yet.": "अभी कोई दस्तावेज़ अपलोड नहीं किया।",
  "FROM OFFICIAL SOURCES": "आधिकारिक स्रोतों से",
  "Latest government updates": "ताज़ा सरकारी सूचनाएँ",
  "Explain this update": "यह सूचना समझाएँ",
  "No updates available.": "कोई सूचना उपलब्ध नहीं है।",
  Refresh: "फिर देखें",
  "Questions about schemes, documents, or your next step? Start here.":
    "योजनाओं, दस्तावेज़ों या अगले कदम पर सवाल हैं? यहाँ पूछें।",
  "Type or speak a question in your language. Answers will include available sources.":
    "अपनी भाषा में सवाल लिखें या बोलें। जवाब में उपलब्ध स्रोत भी दिखेंगे।",
  "Your question": "आपका सवाल",
  "Answering…": "जवाब आ रहा है…",
  Stop: "रोकें",
  You: "आप",
  "Thinking…": "सोच रहे हैं…",
  "No answer received.": "कोई जवाब नहीं मिला।",
  "Follow your applications and keep your receipts in one place.":
    "अपने आवेदनों की स्थिति और रसीदें एक जगह देखें।",
  "No applications yet. Choose a scheme to start an assisted application.":
    "अभी कोई आवेदन नहीं है। मदद से आवेदन करने के लिए योजना चुनें।",
  "Explore schemes →": "योजनाएँ देखें →",
  "Open application →": "आवेदन खोलें →",
  "Application receipt": "आवेदन की रसीद",
  "Reference number:": "संदर्भ संख्या:",
  "View application ↗": "आवेदन देखें ↗",
  "← My applications": "← मेरे आवेदन",
  "Applying, together.": "आइए, मिलकर आवेदन करें।",
  "Watch each step. Take over when needed. You decide before final submission.":
    "हर चरण देखें। ज़रूरत पर नियंत्रण लें। अंतिम सबमिशन से पहले आप तय करेंगे।",
  "YOUR HELP IS NEEDED": "आपकी मदद चाहिए",
  "Ready to submit?": "आवेदन जमा करने के लिए तैयार हैं?",
  "Enter your one-time password": "अपना OTP डालें",
  "Complete the CAPTCHA": "CAPTCHA पूरा करें",
  "Sign in to continue": "आगे बढ़ने के लिए लॉग इन करें",
  "A detail is missing": "कुछ जानकारी चाहिए",
  "Review the application in the browser view before approving.":
    "मंज़ूरी से पहले ब्राउज़र में आवेदन जाँचें।",
  "Approve final submission": "अंतिम सबमिशन मंज़ूर करें",
  "Abort application": "आवेदन रोकें",
  "Take over": "नियंत्रण लें",
  "I’m done, continue": "हो गया, आगे बढ़ें",
  Continue: "आगे बढ़ें",
  "Your answer": "आपका जवाब",
  "Live browser": "लाइव ब्राउज़र",
  "Waiting for the browser view…": "ब्राउज़र का इंतज़ार है…",
  "You are in control. Click the live browser to choose a field, then type here.":
    "नियंत्रण आपके पास है। ब्राउज़र में जगह चुनें, फिर यहाँ लिखें।",
  "Text for the selected field": "चुने हुए खाने के लिए जानकारी",
  "Type into browser": "ब्राउज़र में लिखें",
  "Step by step": "एक-एक चरण",
  "Result:": "परिणाम:",
  "Steps will appear when the assistant begins.":
    "साथी के शुरू करते ही चरण दिखेंगे।",
  "In plain language": "आसान भाषा में",
  "Key points": "मुख्य बातें",
  "Your rights": "आपके अधिकार",
  Deadlines: "अंतिम तारीखें",
  "Documents you need": "ज़रूरी दस्तावेज़",
  "What this means for you": "आपके लिए इसका क्या मतलब है",
  Listen: "सुनें",
  "Official source": "आधिकारिक स्रोत",
  "Not provided": "नहीं बताया",
  Yes: "हाँ",
  No: "नहीं",
  Eligible: "पात्र",
  "Likely eligible": "संभवतः पात्र",
  "Not eligible": "पात्र नहीं",
  "Need more information": "और जानकारी चाहिए",
  age: "उम्र",
  gender: "लिंग",
  state: "राज्य",
  district: "ज़िला",
  residence: "निवास",
  caste: "सामाजिक वर्ग",
  "annual income": "सालाना आय (₹)",
  occupation: "काम",
  "is student": "क्या छात्र हैं",
  "education level": "शिक्षा",
  "disability percent": "दिव्यांगता प्रतिशत",
  "marital status": "वैवाहिक स्थिति",
  "is bpl": "क्या BPL परिवार है",
  "land acres": "ज़मीन (एकड़)",
  "is minority": "क्या अल्पसंख्यक हैं",
  male: "पुरुष",
  female: "महिला",
  transgender: "ट्रांसजेंडर",
  urban: "शहरी",
  rural: "ग्रामीण",
  general: "सामान्य",
  obc: "अन्य पिछड़ा वर्ग",
  sc: "अनुसूचित जाति",
  st: "अनुसूचित जनजाति",
  "Connecting…": "जुड़ रहे हैं…",
  Connected: "जुड़ा हुआ",
  "Reconnecting…": "दोबारा जुड़ रहे हैं…",
  "Disconnected · reconnecting": "संपर्क टूटा · दोबारा जुड़ रहे हैं",
  "Connection interrupted": "संपर्क टूट गया",
  Finished: "समाप्त",
  Unavailable: "उपलब्ध नहीं",
  running: "चल रहा है",
  queued: "कतार में",
  "awaiting approval": "आपकी मंज़ूरी का इंतज़ार है",
  done: "पूरा हुआ",
  "needs human": "आपकी मदद चाहिए",
  completed: "पूरा हुआ",
  failed: "विफल",
  aborted: "रोका गया",
  cancelled: "रद्द",
  pending: "इंतज़ार में",
};
export function translate(text: string, lang: Lang) {
  if (text === "Buddy") return tt(lang, "brandName");
  return lang === "hi" ? hi[text] || text : text;
}
