import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const frontendUrlHost = (() => {
  try {
    const raw = process.env.FRONTEND_URL?.trim();
    return raw ? new URL(raw).hostname : null;
  } catch {
    return null;
  }
})();

const allowAllHosts = (() => {
  const v = (process.env.VITE_ALLOW_ALL_HOSTS || "").trim().toLowerCase();
  if (v === "true" || v === "1" || v === "yes") return true;
  const list = (process.env.VITE_ALLOWED_HOSTS || "")
    .split(",")
    .map((x) => x.trim().toLowerCase())
    .filter(Boolean);
  return list.includes("*") || list.includes("all");
})();

const allowedHosts = allowAllHosts
  ? true
  : Array.from(
      new Set(
        [
          "localhost",
          "127.0.0.1",
          frontendUrlHost,
          ...(process.env.VITE_ALLOWED_HOSTS || "")
            .split(",")
            .map((x) => x.trim())
            .filter(Boolean)
            .filter((x) => !["*", "all"].includes(x.toLowerCase())),
        ].filter(Boolean),
      ),
    );

/** HMR behind HTTPS reverse proxy (Nginx Proxy Manager, Cloudflare, etc.). */
function devHmrSetting() {
  const off = (process.env.VITE_DEV_HMR || "").trim().toLowerCase();
  if (off === "false" || off === "0" || off === "off") {
    return false;
  }
  const host = (process.env.VITE_DEV_HMR_HOST || "").trim();
  if (!host) return null;
  const protocol = (process.env.VITE_DEV_HMR_PROTOCOL || "wss").trim();
  const clientPort = Number.parseInt(process.env.VITE_DEV_HMR_CLIENT_PORT || "443", 10);
  return {
    host,
    protocol,
    clientPort: Number.isNaN(clientPort) ? 443 : clientPort,
  };
}

const devHmr = devHmrSetting();

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      injectRegister: "auto",
      manifest: {
        id: "/",
        name: "Airlock",
        short_name: "Airlock",
        description: "Self-hosted secure container workspaces and session access",
        lang: "en",
        dir: "ltr",
        scope: "/",
        theme_color: "#070d16",
        background_color: "#070d16",
        display: "standalone",
        display_override: ["standalone", "minimal-ui", "browser"],
        orientation: "any",
        start_url: "/",
        categories: ["productivity", "utilities"],
        icons: [
          {
            src: "/icon.svg",
            sizes: "192x192",
            type: "image/svg+xml",
            purpose: "any",
          },
          {
            src: "/icon.svg",
            sizes: "512x512",
            type: "image/svg+xml",
            purpose: "any",
          },
          {
            src: "/icon-maskable.svg",
            sizes: "512x512",
            type: "image/svg+xml",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,ico,svg,woff2}"],
        navigateFallbackDenylist: [/^\/api/],
      },
      devOptions: {
        enabled: false,
      },
    }),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    allowedHosts,
    ...(devHmr !== null ? { hmr: devHmr } : {}),
    proxy: {
      "/api": {
        target: "http://backend:8000",
        changeOrigin: true,
      },
      // Session noVNC: browser uses same origin (e.g. :32770) for ws://.../ws/session/...
      "/ws": {
        target: "http://backend:8000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
