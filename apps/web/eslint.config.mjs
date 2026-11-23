import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores(["public/maplibre-gl-worker.mjs", ".next/**", "out/**", "node_modules/**", "next-env.d.ts", "coverage/**"]),
]);
