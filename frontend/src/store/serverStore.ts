import { create } from "zustand"
import type { Server } from "@/types"

interface ServerState {
  selectedServerId: string | null
  servers: Server[]
  setServers: (servers: Server[]) => void
  selectServer: (id: string | null) => void
}

/** Client-side server selection state. */
export const useServerStore = create<ServerState>()((set) => ({
  selectedServerId: null,
  servers: [],
  setServers: (servers) => set({ servers }),
  selectServer: (id) => set({ selectedServerId: id }),
}))
