import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { registerHooks } from "node:module";
import ts from "typescript";

const state = { values: [], index: 0, calls: [] };
globalThis.__buddyApplicationTest = state;
const stubs = {
  react: `const s = globalThis.__buddyApplicationTest;
    export function useState(initial) { const i=s.index++; if (!(i in s.values)) s.values[i]=initial;
      return [s.values[i], v=>s.values[i]=typeof v==='function'?v(s.values[i]):v]; }
    export function useRef(initial) { const i=s.index++; return s.values[i] ??= {current:initial}; }
    export function useEffect(fn, deps) { const i=s.index++; if (!s.values[i]) { s.values[i]=deps; fn(); } }`,
  "react-router-dom": `const s=globalThis.__buddyApplicationTest;
    export const Link='a'; export const useParams=()=>({slug:'test-scheme'});
    export const useNavigate=()=>url=>s.calls.push(['navigate',url]);`,
  "../context": `export const Text='text'; export const useApp=()=>({lang:'en',profileId:'farmer'});`,
  "../api/client": `const s=globalThis.__buddyApplicationTest;
    export const request=async url=>{s.calls.push(['request',url]); return url.endsWith('/application-url')
      ? {portal_url:'https://official.gov.in/apply'} : s.scheme;};
    export const post=async (url,body)=>{s.calls.push(['post',url,body]); return {id:'run-123'};};
    export const safeUrl=url=>url?.startsWith('https://')?url:undefined;`,
  "../components": `export const ErrorBox='error', Explanation='explanation', Loading='loading', Markdown='markdown';`,
  "../ui": `export const Card='card', PillButton='button', SourceLink='source';`,
  "lucide-react": `export const Bot='svg', Landmark='svg', Mic='svg', Volume2='svg';`,
};

registerHooks({
  resolve(specifier, context, next) {
    if (context.parentURL?.endsWith("/src/pages/Scheme.tsx") && specifier in stubs)
      return { url: `buddy-application-test:${specifier}`, shortCircuit: true };
    if (specifier.startsWith(".") && context.parentURL?.includes("/client/src/")) {
      for (const ext of [".ts", ".tsx"])
        if (existsSync(new URL(specifier + ext, context.parentURL))) return next(specifier + ext, context);
    }
    return next(specifier, context);
  },
  load(url, context, next) {
    if (url.startsWith("buddy-application-test:"))
      return { format: "module", shortCircuit: true, source: stubs[url.slice("buddy-application-test:".length)] };
    if (url.includes("/client/src/") && /\.tsx?$/.test(url))
      return { format: "module", shortCircuit: true, source: ts.transpileModule(
        readFileSync(new URL(url), "utf8").replaceAll("import.meta.env.VITE_API_URL", '""'),
        { fileName: new URL(url).pathname, compilerOptions: { module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX } },
      ).outputText };
    return next(url, context);
  },
});

const { default: Scheme } = await import("../src/pages/Scheme.tsx");
const { asksAboutPendingStep } = await import("../src/api/talk.ts");
function elements(node) {
  if (!node || typeof node !== "object") return [];
  return [node, ...[node.props?.children].flat(Infinity).flatMap(elements)];
}

test("Apply for me resolves a missing scheme URL and starts its run on one click", async () => {
  state.scheme = { name: "Official scheme", source_url: "https://www.myscheme.gov.in/schemes/test-scheme", application: [], faqs: [] };
  Scheme();
  await new Promise(setImmediate);
  state.index = 0;
  const tree = Scheme();
  const nodes = elements(tree);
  assert.ok(!nodes.some(n => n.type === "input" && n.props.id === "portal"));
  const button = nodes.find(n => n.type === "button" && elements(n).some(c => c.props?.value === "Apply for me"));
  assert.ok(button);
  button.props.onClick();
  await new Promise(setImmediate);
  assert.deepEqual(state.calls.slice(-3), [
    ["request", "/schemes/test-scheme/application-url"],
    ["post", "/agent/runs", { profile_id: "farmer", portal_url: "https://official.gov.in/apply", goal: "Apply for Official scheme", scheme_slug: "test-scheme" }],
    ["navigate", "/runs/run-123"],
  ]);
});

test("document questions reach Talk while personal answers and security steps stay local", () => {
  for (const kind of ["confirm_upload", "missing_field", "capture_required"])
    for (const question of ["which document is that?", "yeh kaunsa document hai?", "এটা কোন নথি?", "এইখন কি নথি?"])
      assert.equal(asksAboutPendingStep(question, kind), true);
  for (const kind of ["otp", "captcha", "login", "payment", "confirm_submit"])
    assert.equal(asksAboutPendingStep("what is this?", kind), false);
  for (const value of ["987654", "Private Citizen", "Assam"])
    assert.equal(asksAboutPendingStep(value, "missing_field"), false);
});
