import { apiClient } from "./client"

export interface PhpSite {
  /** Full vhost path — the switch endpoint allowlists against this. */
  config: string
  name: string
  socket: string
  version: string | null
}

export interface PhpInfo {
  versions: string[]
  running: string[]
  cli_default: string | null
  sites: PhpSite[]
  error?: string
}

export async function getPhp(serverId: string): Promise<PhpInfo> {
  const { data } = await apiClient.get(`/api/servers/${serverId}/php`)
  return data
}

/** Move one site onto another installed version. The server verifies the site still works
 *  and puts the old version back if it does not, so a 409 means nothing is broken. */
export async function switchPhp(
  serverId: string, body: { config: string; domain: string; version: string },
): Promise<{ ok: boolean; message: string; php: PhpInfo }> {
  const { data } = await apiClient.post(`/api/servers/${serverId}/php/switch`, body)
  return data
}
