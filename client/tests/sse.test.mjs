import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";
import ts from "typescript";
const source = readFileSync(
  new URL("../src/api/sse.ts", import.meta.url),
  "utf8",
);
const js = ts.transpileModule(source, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.ESNext,
  },
}).outputText;
const { createSseParser } = await import(
  "data:text/javascript;base64," + Buffer.from(js).toString("base64")
);
test("SSE handles every chunk boundary, CRLF, Unicode and multiple events", () => {
  const payload =
    ': heartbeat\r\nevent: message\r\ndata: {"type":"token","text":"हिन्दी"}\r\n\r\ndata: {"type":"done","message_id":1}\r\n\r\n';
  const expected = [
    '{"type":"token","text":"हिन्दी"}',
    '{"type":"done","message_id":1}',
  ];
  for (let split = 0; split <= payload.length; split++) {
    const actual = [];
    const parser = createSseParser((d) => actual.push(d));
    parser.push(payload.slice(0, split));
    parser.push(payload.slice(split));
    parser.finish();
    assert.deepEqual(actual, expected, `boundary ${split}`);
  }
});
test("SSE joins multiline data and flushes a final event without a separator", () => {
  const values = [];
  const parser = createSseParser((d) => values.push(d));
  parser.push("data: first\ndata: second\n\ndata: last");
  parser.finish();
  assert.deepEqual(values, ["first\nsecond", "last"]);
});
test("SSE does not swallow errors from consumers", () => {
  const parser = createSseParser(() => {
    throw new Error("stream failure");
  });
  assert.throws(() => parser.push("data: failure\n\n"), /stream failure/);
});
