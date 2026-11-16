import type { NextConfig } from "next";

// O navegador só fala com o Next; /api é encaminhado ao backend. Assim o cookie de sessão é
// same-origin (httpOnly, SameSite=Lax) e não há CORS.
const API_URL = process.env.BORGES_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
