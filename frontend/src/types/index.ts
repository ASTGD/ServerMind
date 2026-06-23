export interface User {
  id: string
  email: string
  name: string | null
  avatar_url: string | null
  preferred_language: string
  is_active: boolean
  is_verified: boolean
  totp_enabled: boolean
  created_at: string
}

export interface Server {
  id: string
  name: string
  host: string
  port: number
  username: string
  auth_type: "password" | "key"
  connection_type: "ssh" | "winrm" | "hosting"
  panel_type: string | null
  os_type: string | null
  os_version: string | null
  arch: string | null
  shell: string
  status: "online" | "offline" | "unknown"
  tags: string[] | null
  notes: string | null
  last_seen: string | null
  created_at: string
}

export interface ServerMetrics {
  cpu_percent: number | null
  ram_percent: number | null
  ram_used_mb: number | null
  ram_total_mb: number | null
  disk_percent: number | null
  disk_used_gb: number | null
  disk_total_gb: number | null
  load_1: number | null
  load_5: number | null
  load_15: number | null
  uptime_seconds: number | null
  recorded_at: string
}

export interface CommandItem {
  cmd: string
  description: string
  risk_level: "low" | "medium" | "high"
  requires_confirmation: boolean
}

export interface AIPlan {
  intent_understood: string
  clarification_needed: string | null
  plan_summary: string
  commands: CommandItem[]
  estimated_duration_seconds: number
  post_execution_message: string
  follow_up_suggestions: string[]
}

export interface CommandLog {
  id: string
  server_id: string
  user_input: string
  ai_plan: AIPlan | null
  commands: CommandItem[] | null
  output: string | null
  status: "success" | "failed" | "partial" | "blocked" | "pending_approval" | null
  ai_explanation: string | null
  risk_level: string | null
  execution_ms: number | null
  created_at: string
}

export interface PlaybookVariable {
  name: string
  label: string
  default: string
  required: boolean
}

export interface Playbook {
  id: string
  slug: string
  title: string
  description: string | null
  category: string | null
  os_family: "linux" | "windows" | "both" | null
  script_type: "bash" | "powershell" | "both" | null
  variables: PlaybookVariable[] | null
  supported_os: string[] | null
  est_runtime_sec: number | null
  is_official: boolean
  run_count: number
  rating: number | null
  tags: string[] | null
  version: string
  created_at: string
}

export interface PlaybookAccessInfo {
  name?: string
  url?: string
  username?: string
  password?: string
  note?: string
}

export interface PlaybookDetail extends Playbook {
  script_bash: string | null
  script_powershell: string | null
  access_info: PlaybookAccessInfo | null
}

export interface PlaybookRun {
  id: string
  server_id: string
  playbook_id: string | null
  variables_used: Record<string, string> | null
  output: string | null
  status: "running" | "success" | "failed" | null
  started_at: string
  completed_at: string | null
}

export interface ScheduledTask {
  id: string
  server_id: string
  title: string
  task_type: "command" | "playbook" | "user_script"
  payload: Record<string, unknown> | null
  cron_expression: string
  human_schedule: string | null
  is_active: boolean
  last_run: string | null
  last_status: string | null
  next_run: string | null
  created_at: string
}

export interface Alert {
  id: string
  server_id: string
  metric: string | null
  condition: string | null
  threshold: number | null
  channel: "email" | "webhook" | "slack" | null
  channel_target: string | null
  is_active: boolean
  last_triggered: string | null
  created_at: string
}

export interface UserScript {
  id: string
  title: string
  description: string | null
  script_type: string | null
  script_content: string
  source: string | null
  tags: string[] | null
  created_at: string
}

export interface GenerateScriptResult {
  title: string
  description: string
  script_type: string
  estimated_runtime_seconds: number
  variables: PlaybookVariable[]
  script: string
  post_run_instructions: string
  warnings: string[]
  saved_id: string | null
}

export interface ActivityItem {
  id: string
  kind: "command" | "playbook"
  server_id: string | null
  title: string
  status: string | null
  risk_level: string | null
  duration_ms: number | null
  created_at: string
}

export interface WSMessage {
  type: string
  [key: string]: unknown
}
