import type { NextConfig } from "next";

// In Docker, Caddy serves everything from one origin (infra/caddy/Caddyfile).
// For `npm run dev` on the host, proxy API calls to a locally running FastAPI.
const API_ORIGIN = process.env.INTERNAL_API_ORIGIN || "http://localhost:8000";

// STATIC_EXPORT=1 builds the public preview on Vercel (D-056, set in vercel.json): plain HTML
// in `out/`, with no API behind it, so no rewrites.
const STATIC_EXPORT = process.env.STATIC_EXPORT === "1";

const nextConfig: NextConfig = STATIC_EXPORT
  ? {
      output: "export",
      trailingSlash: true,
      poweredByHeader: false,
      images: { unoptimized: true },
      // Pages that need the API show a notice instead (src/lib/api/client.ts).
      env: { NEXT_PUBLIC_STATIC_PREVIEW: "1" },
    }
  : {
      output: "standalone",
      poweredByHeader: false,
      async rewrites() {
        return [
          { source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` },
          // `npm run dev` against the Docker stack (INTERNAL_API_ORIGIN=http://localhost:8080):
          // the basemap is served by Caddy too. In Docker, Caddy answers /basemap itself.
          { source: "/basemap/:path*", destination: `${API_ORIGIN}/basemap/:path*` },
        ];
      },
    };

export default nextConfig;
