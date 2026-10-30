// Preserve carriage returns until a complete line arrives: a network chunk can
// end halfway through a CRLF separator or a UTF-8 character.
export function createSseParser(onData: (data: string) => void) {
  let buffer = "";
  let lines: string[] = [];
  const line = (value: string) => {
    if (value === "") {
      if (lines.length) onData(lines.join("\n"));
      lines = [];
    } else if (value.startsWith("data:")) {
      lines.push(value.slice(5).replace(/^ /, ""));
    }
  };
  return {
    push(chunk: string) {
      buffer += chunk;
      let index: number;
      while ((index = buffer.indexOf("\n")) >= 0) {
        line(buffer.slice(0, index).replace(/\r$/, ""));
        buffer = buffer.slice(index + 1);
      }
    },
    finish() {
      if (buffer) line(buffer.replace(/\r$/, ""));
      buffer = "";
      line("");
    },
  };
}
