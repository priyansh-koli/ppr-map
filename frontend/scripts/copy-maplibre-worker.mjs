// MapLibre 6 is ESM-only and starts its worker from a URL next to its own module. Bundlers
// do not carry that file along, so the worker and the chunk it imports are copied to
// public/maplibre/<version>/ and the map points `setWorkerUrl` at them. Runs before dev/build.
import { copyFileSync, mkdirSync, readFileSync, rmSync } from "node:fs";

const { version } = JSON.parse(readFileSync("node_modules/maplibre-gl/package.json", "utf8"));
const dir = `public/maplibre/${version}`;
rmSync("public/maplibre", { recursive: true, force: true });
mkdirSync(dir, { recursive: true });
for (const file of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  copyFileSync(`node_modules/maplibre-gl/dist/${file}`, `${dir}/${file}`);
}
