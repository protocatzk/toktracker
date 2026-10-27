import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        admin: fileURLToPath(new URL("index.html", import.meta.url)),
        public: fileURLToPath(new URL("public.html", import.meta.url)),
        donorRadar: fileURLToPath(new URL("donor-radar.html", import.meta.url)),
        chatIntelligence: fileURLToPath(new URL("chat-intelligence.html", import.meta.url)),
        siteAnalytics: fileURLToPath(new URL("site-analytics.html", import.meta.url)),
        login: fileURLToPath(new URL("login.html", import.meta.url)),
        miniapp: fileURLToPath(new URL("miniapp.html", import.meta.url)),
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:5000",
        changeOrigin: true,
      },
    },
  },
});
