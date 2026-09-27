// Serves the static export (`out/`) under BASE_PATH the way GitHub Pages does: directories
// redirect to a trailing slash, `dir/` serves `dir/index.html`, anything else gets 404.html.
// Used by `E2E_BASE_PATH=/ppr-map npm run test:e2e` after a STATIC_EXPORT build.
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize, sep } from "node:path";

const OUT = join(import.meta.dirname, "..", "out");
const BASE = (process.env.BASE_PATH ?? "").replace(/\/$/, "");
const PORT = Number(process.env.PORT ?? 3000);

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".txt": "text/plain; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
};

function send(res, status, file) {
  res.writeHead(status, { "content-type": TYPES[extname(file)] ?? "application/octet-stream" });
  createReadStream(file).pipe(res);
}

createServer((req, res) => {
  const url = new URL(req.url ?? "/", "http://localhost");
  const path = decodeURIComponent(url.pathname);
  const notFound = () => send(res, 404, join(OUT, "404.html"));
  if (path !== BASE && !path.startsWith(`${BASE}/`)) return notFound();

  const file = normalize(join(OUT, path.slice(BASE.length)));
  if (file !== OUT && !file.startsWith(OUT + sep)) return notFound();
  if (existsSync(file) && statSync(file).isDirectory()) {
    if (!path.endsWith("/")) {
      res.writeHead(301, { location: `${path}/${url.search}` });
      return res.end();
    }
    const index = join(file, "index.html");
    return existsSync(index) ? send(res, 200, index) : notFound();
  }
  return existsSync(file) ? send(res, 200, file) : notFound();
}).listen(PORT, () => console.log(`serving ${OUT} at http://localhost:${PORT}${BASE}/`));
