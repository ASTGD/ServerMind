import { apiClient } from "./client"

/** A short-lived desktop session (Assets Phase E). The RDP credentials never reach the
 *  browser — the token references a server-side session the desktop viewer connects with. */
export interface RdpSession {
  session_token: string
  host: string
  port: number
  expires_in: number
  streaming_available: boolean
}

export async function enableRdp(id: string, enabled: boolean): Promise<{ rdp_enabled: boolean }> {
  const { data } = await apiClient.post<{ rdp_enabled: boolean }>(`/api/servers/${id}/rdp/enable`, { enabled })
  return data
}

export async function openRdpSession(id: string): Promise<RdpSession> {
  const { data } = await apiClient.post<RdpSession>(`/api/servers/${id}/rdp/session`)
  return data
}
