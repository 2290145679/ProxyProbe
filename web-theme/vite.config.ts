import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // import.meta.dirname rather than new URL(...).pathname: the latter is
  // URL-encoded, so a checkout under a path containing a space or a non-ASCII
  // name resolves to %20 and the alias silently points nowhere.
  resolve: { alias: { "@": import.meta.dirname + "/src" } },
  build: {
    chunkSizeWarningLimit: 900,
    // Flags stay files. Vite would inline every one under 4 KiB -- all of them --
    // as a data URL, and because the page imports the whole set, all of them
    // would ship in the entry chunk whichever flags a hub's nodes need.
    assetsInlineLimit: (file) => (file.includes("/country-flag-icons/") ? false : undefined),
  },
  // A theme reads public data only, so any hub with its status page open can
  // serve as the source: MONITOR_HUB=https://hub.example.com npm run dev.
  // changeOrigin sends that hub its own name as Host, which the proxy or CDN in
  // front of it routes by.
  server: {
    proxy: { "/api": { target: process.env.MONITOR_HUB || "http://127.0.0.1:9911", changeOrigin: true, ws: true } },
  },
})
