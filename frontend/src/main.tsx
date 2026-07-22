import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import "./i18n/index"
// Self-hosted Inter (variable weight) — bundled locally by Vite, no CDN request.
import "@fontsource-variable/inter"
// Applies the persisted light/dark theme before first render (avoids a flash).
import "./store/themeStore"
import "./index.css"
import App from "./App"

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000 } },
})

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
