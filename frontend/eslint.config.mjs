import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores([
    ".next/**",
    "node_modules/**",
    "playwright-report/**",
    "test-results/**",
    "next-env.d.ts",
    // copied from node_modules (scripts/copy-maplibre-worker.mjs) and generated (make api-types)
    "public/maplibre/**",
    "src/lib/api/schema.d.ts",
  ]),
]);
