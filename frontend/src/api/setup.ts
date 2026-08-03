import { apiClient } from "./client"

export interface SetupStep {
  label: string
  slug: string
  optional: boolean
  state: "pending" | "running" | "done" | "skipped" | "failed"
  note?: string
}

export interface SetupOption {
  key: string
  title: string
  description: string
  minutes: number
  steps: { label: string; optional: boolean }[]
}

export interface Setup {
  id: string
  purpose: string
  status: "running" | "done" | "failed" | "stopped"
  steps: SetupStep[]
  current: number
  failed_step: string | null
  message: string | null
  progress: { done: number; total: number; percent: number }
  started_at: string | null
  finished_at: string | null
}

/** One entry in a setup dropdown. The screen never writes its own list — an option it
 *  invented would be refused by the endpoint, which validates against the same source. */
export interface SetupChoice {
  value: string
  label: string
  note: string
  /** PHP only: this version no longer receives security fixes. */
  eol?: boolean
  /** Database only: operating systems that cannot install it. */
  not_on?: string[]
}

export interface SetupStatus {
  options: SetupOption[]
  /** Why this server cannot be set up — empty when it can. */
  blocked: string
  php_choices: SetupChoice[]
  db_choices: SetupChoice[]
  /** The server's real OS, so a choice it cannot honour is greyed out before it is picked. */
  os_type: string
  /** The customer's OTHER servers. A database server is opened to these and nobody else,
   *  so they are shown before the button is pressed rather than after. */
  own_servers: { name: string; host: string }[]
  already_set_up: boolean
  latest: Setup | null
}

export async function getSetupStatus(serverId: string): Promise<SetupStatus> {
  const { data } = await apiClient.get(`/api/servers/${serverId}/setup`)
  return data
}

export async function startSetup(
  serverId: string,
  body: {
    purpose: string; timezone?: string; monitoring?: boolean; force?: boolean
    php_version?: string; db_engine?: string
  },
): Promise<Setup> {
  const { data } = await apiClient.post(`/api/servers/${serverId}/setup`, body)
  return data
}

export async function stopSetup(serverId: string): Promise<Setup> {
  const { data } = await apiClient.post(`/api/servers/${serverId}/setup/stop`)
  return data
}
