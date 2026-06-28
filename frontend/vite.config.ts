import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build output goes into the FastAPI app's static dir so the Databricks App
// serves the SPA and API from one process. Dev proxies /api to FastAPI.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
