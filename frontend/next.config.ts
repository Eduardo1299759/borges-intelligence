import type { NextConfig } from "next";

// O navegador só fala com o Next; /api é encaminhado ao backend. Assim o cookie de sessão é
// same-origin (httpOnly, SameSite=Lax) e não há CORS.
// 127.0.0.1 e não "localhost": no Windows, o Node resolve localhost para o IPv6 ::1, onde a API não escuta.
const API_URL = process.env.BORGES_API_URL ?? "http://127.0.0.1:8000";

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
