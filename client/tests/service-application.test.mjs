// Exercise the real card callback and SSE action without a browser or dev server.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { registerHooks } from "node:module";
import ts from "typescript";

registerHooks({
  resolve(specifier, context, next) {
    if (
      specifier.startsWith(".") &&
      context.parentURL?.includes("/client/src/")
    ) {
      for (const ext of [".ts", ".tsx"]) {
        if (existsSync(new URL(specifier + ext, context.parentURL)))
          return next(specifier + ext, context);
      }
    }
    return next(specifier, context);
  },
  load(url, context, next) {
    if (url.includes("/client/src/") && /\.tsx?$/.test(url)) {
      const source = readFileSync(new URL(url), "utf8").replaceAll(
        "import.meta.env.VITE_API_URL",
        '""',
      );
      return {
        format: "module",
        shortCircuit: true,
        source: ts.transpileModule(source, {
          fileName: new URL(url).pathname,
          compilerOptions: {
            module: ts.ModuleKind.ESNext,
            jsx: ts.JsxEmit.ReactJSX,
          },
        }).outputText,
      };
    }
    return next(url, context);
  },
});

const { default: CardView } = await import("../src/pages/TalkCards.tsx");
const { talkBody, streamTalk } = await import("../src/api/talk.ts");
const { dispatchAction } = await import("../src/buddy/actions.ts");

function elements(node) {
  if (!node || typeof node !== "object") return [];
  return [node, ...[node.props?.children].flat(Infinity).flatMap(elements)];
}

test("Hindi service apply button sends the selected ID and returned action opens its run", async (t) => {
  let input;
  const tree = CardView({
    card: {
      kind: "service",
      service_id: "driving_licence",
      service: "ड्राइविंग लाइसेंस",
      official_portal_url: "https://sarathi.parivahan.gov.in",
      steps: [],
      documents: [],
      fees: null,
      time: null,
      notes: ["निर्देशों की पुष्टि नहीं हो सकी।"],
      sources: [],
    },
    lang: "hi",
    disabled: false,
    onAnswer() {
      assert.fail("Apply must carry a service ID, not just a chat answer");
    },
    onApply(service, text) {
      input = {
        profile_id: "farmer",
        lang: "hi",
        text,
        action: { type: "start_application", service },
      };
    },
  });
  const button = elements(tree).find((node) => node.type === "button");
  assert.equal(button.props.children, "आवेदन में मदद करें");
  button.props.onClick();
  assert.equal(input.action.service, "driving_licence");
  const calls = [];
  t.mock.method(globalThis, "fetch", async (_url, init) => {
    assert.deepEqual(JSON.parse(init.body).action, {
      type: "start_application",
      service: "driving_licence",
    });
    const events = [
      {
        type: "action",
        action: {
          type: "start_application",
          service: "driving_licence",
          run_id: "run-123",
        },
      },
      { type: "done", text: "आवेदन में मदद शुरू है।", lang: "hi" },
    ];
    return new Response(
      events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join(""),
    );
  });
  await streamTalk(
    input,
    (event) => {
      if (event.type === "action")
        void dispatchAction(event.action, {
          activateRun: (id) => calls.push(["activate", id]),
          navigate: (url) => calls.push(["navigate", url]),
        });
    },
    new AbortController().signal,
  );
  assert.deepEqual(calls, [
    ["activate", "run-123"],
    ["navigate", "/runs/run-123"],
  ]);
});

test("multipart Talk preserves the explicit application action", () => {
  const action = { type: "start_application", service: "driving_licence" };
  const { body } = talkBody({
    profile_id: "farmer",
    action,
    audio: new Blob(["voice"], { type: "audio/webm" }),
  });
  assert.deepEqual(JSON.parse(body.get("action")), action);
});
