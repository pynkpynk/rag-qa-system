import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const proxyTarget = (process.env.VITE_PROXY_TARGET || "http://127.0.0.1:8000").trim();

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    proxy: {
      "/api": {
        target: proxyTarget,
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
