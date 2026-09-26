import type { NextConfig } from "next";

// In Docker, Caddy serves everything from one origin (infra/caddy/Caddyfile).
// For `npm run dev` on the host, proxy API calls to a locally running FastAPI.
const API_ORIGIN = process.env.INTERNAL_API_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
};

export default nextConfig;
