import { apiClient } from "./client"

export interface FirewallRule {
  index: number | null
  action: string
  port: string
  protocol: string
  source: string
  comment: string
  /** Plain-language name for what this rule opens. */
  describes: string
  /** True when removing it would end our own access — the button is disabled, not offered. */
  protected: boolean
}

export interface Firewall {
  manager: string          // ufw | firewalld | none | unmanaged
  active: boolean
  default_incoming: string
  note: string
  ssh_port: number
  /** The address the server sees us coming from, not one we assume. */
  our_ip: string
  manageable: boolean
  rules: FirewallRule[]
}

export interface SshKey {
  fingerprint: string
  type: string
  label: string
  comment: string
  options: string
  line: number
  is_ours: boolean
  protected: boolean
}

export interface SshKeys {
  user: string
  home: string
  note: string
  auth_type: string
  keys: SshKey[]
}

export async function getFirewall(serverId: string): Promise<Firewall> {
  const { data } = await apiClient.get(`/api/servers/${serverId}/firewall`)
  return data
}

export async function addFirewallRule(
  serverId: string,
  body: { action: string; port: string; protocol: string; source: string; comment: string },
): Promise<Firewall> {
  const { data } = await apiClient.post(`/api/servers/${serverId}/firewall/rules`, body)
  return data
}

export async function removeFirewallRule(
  serverId: string, rule: FirewallRule,
): Promise<Firewall> {
  const { data } = await apiClient.post(`/api/servers/${serverId}/firewall/rules/remove`, {
    index: rule.index, port: rule.port, protocol: rule.protocol,
    source: rule.source, comment: rule.comment,
  })
  return data
}

export async function toggleFirewall(serverId: string, on: boolean): Promise<Firewall> {
  const { data } = await apiClient.post(
    `/api/servers/${serverId}/firewall/toggle?on=${on}`)
  return data
}

export async function getSshKeys(serverId: string, user?: string): Promise<SshKeys> {
  const { data } = await apiClient.get(`/api/servers/${serverId}/ssh-keys`,
                                       { params: user ? { user } : {} })
  return data
}

export async function addSshKey(
  serverId: string, publicKey: string, label: string, user?: string,
): Promise<SshKeys> {
  const { data } = await apiClient.post(`/api/servers/${serverId}/ssh-keys`,
    { public_key: publicKey, label }, { params: user ? { user } : {} })
  return data
}

export async function removeSshKey(
  serverId: string, fingerprint: string, user?: string,
): Promise<SshKeys> {
  const { data } = await apiClient.delete(
    `/api/servers/${serverId}/ssh-keys/${fingerprint}`, { params: user ? { user } : {} })
  return data
}
