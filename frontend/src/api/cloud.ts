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
  /** Registered with AWS Systems Manager and answering — reachable with no key and no open
   *  port. Absent or false for providers that have no such thing. */
  ssm_managed?: boolean
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
  /** Use Systems Manager wherever it is available, rather than only where there is no
   *  address to reach. */
  prefer_ssm?: boolean
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

// ── Lifecycle: create, restart, resize and destroy (DigitalOcean + Hetzner) ──

export interface CloudSize {
  slug: string
  label: string
  vcpus: number
  memory_mb: number
  disk_gb: number
  price_monthly: number | null
  currency: string
  available: boolean
}

export interface Catalogue {
  supported: boolean
  provider: string
  message?: string
  regions: { slug: string; label: string; available: boolean; sizes?: string[] }[]
  sizes: CloudSize[]
  images: { slug: string; label: string }[]
  ssh_keys: { id: string; label: string }[]
}

export interface ResizePlan {
  from_size: string
  to_size: string
  grows_disk: boolean
  /** False means the disk grows, which can never be undone. */
  reversible: boolean
  needs_power_off: boolean
  warning: string
  price_change: string
}

export async function getCloudCatalogue(accountId: string): Promise<Catalogue> {
  const { data } = await apiClient.get(`/api/cloud-accounts/${accountId}/catalogue`)
  return data
}

export async function createCloudInstance(
  accountId: string,
  body: { name: string; region: string; size: string; image: string; ssh_keys: string[] },
): Promise<{ instance: CloudInstance; message: string }> {
  const { data } = await apiClient.post(`/api/cloud-accounts/${accountId}/instances`, body)
  return data
}

export async function cloudPower(
  accountId: string, instanceId: string, action: "reboot" | "power-on" | "power-off",
): Promise<{ ok: boolean; message: string }> {
  const { data } = await apiClient.post(
    `/api/cloud-accounts/${accountId}/instances/${instanceId}/${action}`)
  return data
}

export async function previewCloudResize(
  accountId: string, instanceId: string, size: string, growDisk: boolean,
): Promise<{ plan: ResizePlan; name: string; state: string }> {
  const { data } = await apiClient.post(
    `/api/cloud-accounts/${accountId}/instances/${instanceId}/resize/preview`,
    { size, grow_disk: growDisk })
  return data
}

export async function cloudResize(
  accountId: string, instanceId: string, size: string, growDisk: boolean,
): Promise<{ ok: boolean; plan: ResizePlan; message: string }> {
  const { data } = await apiClient.post(
    `/api/cloud-accounts/${accountId}/instances/${instanceId}/resize`,
    { size, grow_disk: growDisk })
  return data
}

/** The typed name is the safety mechanism — the server refuses unless it matches. */
export async function destroyCloudInstance(
  accountId: string, instanceId: string, confirmName: string,
): Promise<{ ok: boolean; message: string }> {
  const { data } = await apiClient.post(
    `/api/cloud-accounts/${accountId}/instances/${instanceId}/destroy`,
    { confirm_name: confirmName })
  return data
}
