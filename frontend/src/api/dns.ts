import { apiClient } from "./client"

export interface DnsAccount {
  id: string
  provider: string
  label: string
  created_at: string | null
}

export interface DnsZone {
  id: string
  name: string
  status: string
}

export interface DnsRecord {
  id: string
  type: string
  name: string
  content: string
  ttl: number
  priority: number | null
  proxied: boolean | null
  /** False for NS/SOA — shown so you can see them, never changed through us. */
  editable: boolean
}

export interface RecordInput {
  type: string
  name: string
  content: string
  ttl?: number
  priority?: number | null
  proxied?: boolean | null
}

export async function listDnsAccounts(): Promise<{ accounts: DnsAccount[]; count: number }> {
  const { data } = await apiClient.get("/api/dns/accounts")
  return data
}

export async function connectDns(body: {
  provider: string; label: string; api_token: string
}): Promise<DnsAccount> {
  const { data } = await apiClient.post("/api/dns/accounts", body)
  return data
}

export async function disconnectDns(id: string): Promise<void> {
  await apiClient.delete(`/api/dns/accounts/${id}`)
}

export async function listZones(accountId: string): Promise<{ zones: DnsZone[]; count: number }> {
  const { data } = await apiClient.get(`/api/dns/accounts/${accountId}/zones`)
  return data
}

export async function listRecords(
  accountId: string, zoneId: string, zone: string,
): Promise<{ zone: string; records: DnsRecord[]; count: number; editable_types: string[] }> {
  const { data } = await apiClient.get(
    `/api/dns/accounts/${accountId}/zones/${zoneId}/records`, { params: { zone } })
  return data
}

export async function createRecord(
  accountId: string, zoneId: string, zone: string, body: RecordInput,
): Promise<DnsRecord> {
  const { data } = await apiClient.post(
    `/api/dns/accounts/${accountId}/zones/${zoneId}/records`, body, { params: { zone } })
  return data
}

export async function updateRecord(
  accountId: string, zoneId: string, zone: string, recordId: string, body: RecordInput,
): Promise<DnsRecord> {
  const { data } = await apiClient.put(
    `/api/dns/accounts/${accountId}/zones/${zoneId}/records/${recordId}`, body,
    { params: { zone } })
  return data
}

export async function deleteRecord(
  accountId: string, zoneId: string, zone: string, recordId: string,
): Promise<void> {
  await apiClient.delete(
    `/api/dns/accounts/${accountId}/zones/${zoneId}/records/${recordId}`, { params: { zone } })
}

/**
 * Validate a record WITHOUT saving it.
 *
 * Called as the user types, so an objection ("a CNAME can't hold an IP") arrives before
 * the mistake rather than after — which for DNS is the difference between a correction
 * and an outage.
 */
export async function checkRecord(params: {
  type: string; name: string; content: string; zone: string
  ttl?: number; priority?: number | null
}): Promise<{ ok: boolean; error: string | null; warning: string | null }> {
  const { data } = await apiClient.get("/api/dns/check", { params })
  return data
}
