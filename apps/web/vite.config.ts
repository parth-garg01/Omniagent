import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Same-origin proxy so the session and CSRF cookies work without CORS.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
  test: { environment: "node" },
});
