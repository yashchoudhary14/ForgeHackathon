// Load real client modules without starting Vite or its esbuild subprocess.
import { readFileSync, existsSync } from "node:fs";
import { registerHooks } from "node:module";
import ts from "typescript";

registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith(".") && context.parentURL?.includes("/client/src/")) {
      for (const ext of [".ts", ".tsx"])
        if (existsSync(new URL(specifier + ext, context.parentURL)))
          return next(specifier + ext, context);
    }
    return next(specifier, context);
  },
  load(url, context, next) {
    if (url.endsWith(".css"))
      return { format: "module", shortCircuit: true, source: "export {};" };
    if (url.includes("/client/src/") && /\.tsx?$/.test(url)) {
      const source = readFileSync(new URL(url), "utf8").replaceAll(
        "import.meta.env.VITE_API_URL", '""',
      );
      return {
        format: "module",
        shortCircuit: true,
        source: ts.transpileModule(source, {
          fileName: new URL(url).pathname,
          compilerOptions: { module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX },
        }).outputText,
      };
    }
    return next(url, context);
  },
});
