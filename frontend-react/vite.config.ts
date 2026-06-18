import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1", // bind IPv4 loopback; default "localhost" resolved IPv6-only (::1), refusing 127.0.0.1
    port: 5173,
    // Dev convenience: proxy /v1 to the FastAPI backend so the browser hits same-origin.
    proxy: {
      "/v1": { target: "http://localhost:8000", changeOrigin: true },
      "/health": { target: "http://localhost:8000", changeOrigin: true },
      "/ready": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
