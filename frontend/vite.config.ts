import path from "path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig({
  plugins: [react()],
  // The .env file lives at the monorepo root, one level above frontend/.
  envDir: "..",
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: true,          // bind 0.0.0.0 so other devices on the LAN can reach it
    port: 5190,          // dedicated port (5173 is used by another local project)
    strictPort: true,    // fail loudly if 5190 is taken instead of silently moving
    proxy: {
      // The app calls relative /api and /ws — proxied here to the backend.
      // We force the Origin header to localhost:5190 so the backend CORS list
      // always matches, regardless of which IP/hostname the browser used to
      // reach the Vite dev server (LAN IP, localhost, etc.).
      "/api": {
        target: "http://localhost:8888",
        changeOrigin: true,
        headers: { origin: "http://localhost:5190" },
      },
      "/ws": {
        target: "ws://localhost:8888",
        ws: true,
        changeOrigin: true,
        headers: { origin: "http://localhost:5190" },
      },
    },
  },
})
