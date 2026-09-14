/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API has no authentication, so the dev server stays on localhost like the API does.
// /api is proxied to FastAPI, so the browser sees one origin and the backend needs no CORS setup.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  build: {
    // Cytoscape is most of the bundle (about 430 kB minified); this is a local tool, so one chunk is fine.
    chunkSizeWarningLimit: 800,
  },
  test: {
    include: ["src/**/*.test.ts"],
  },
});
