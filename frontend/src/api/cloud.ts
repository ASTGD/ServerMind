import { apiClient } from "./client"

/** A connected cloud provider account (Assets Phase C). We never see the instance logins —
 *  the provider API only lists machines; import prefills an asset the user finishes. */
export interface CloudAccount {
  id: string
  provider: string
  label: string
  created_at: string
}

export interface CloudInstance {
  instance_id: string
  name: string
  public_ip: string | null
  private_ip: string | null
  os: string // 'linux' | 'windows'
  state: string
  region: string | null
  instance_type: string | null
  already_imported: boolean
}

export interface ImportResult {
  imported: number
  skipped: number
  limited: boolean
  detail: string | null
}

export interface ConnectCloudBody {
  provider: string
  label: string
  credential: Record<string, string> // provider-shaped, e.g. {access_key_id, secret_access_key, region}
}

export interface ImportInstancesBody {
  instance_ids: string[]
  username: string
  auth_type: "password" | "key"
  credential: string
  use_private_ip: boolean
}

export async function listCloudAccounts(): Promise<CloudAccount[]> {
  const { data } = await apiClient.get<CloudAccount[]>("/api/cloud-accounts")
  return data
}

export async function connectCloudAccount(body: ConnectCloudBody): Promise<CloudAccount> {
  const { data } = await apiClient.post<CloudAccount>("/api/cloud-accounts", body)
  return data
}

export async function deleteCloudAccount(id: string): Promise<void> {
  await apiClient.delete(`/api/cloud-accounts/${id}`)
}

export async function listCloudInstances(id: string): Promise<CloudInstance[]> {
  const { data } = await apiClient.get<CloudInstance[]>(`/api/cloud-accounts/${id}/instances`)
  return data
}

export async function importCloudInstances(
  id: string,
  body: ImportInstancesBody,
): Promise<ImportResult> {
  const { data } = await apiClient.post<ImportResult>(`/api/cloud-accounts/${id}/import`, body)
  return data
}
