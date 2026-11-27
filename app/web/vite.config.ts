import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development Vite serves the screen and forwards /api and /ws to the
// Python server (port APP_SERVER_PORT, default 8765).
const server = `http://127.0.0.1:${process.env.APP_SERVER_PORT ?? 8765}`;

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: Number(process.env.APP_WEB_PORT ?? 5173),
    strictPort: true,
    proxy: {
      "/api": server,
      "/ws": { target: server, ws: true },
    },
  },
});
