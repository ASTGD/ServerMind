# ServerAlly — Claude Code Master Instructions
> **VERSION 3.0** — Updated with official name/tagline, Windows Server support, WinRM layer, hosting environment mode, multilingual AI, and full feature roadmap.
> Read this file FULLY before doing anything. Update checklists as you complete tasks.

---

## 🧠 Product Identity

**Product Name:** ServerAlly
**Tagline:** Your AI companion to manage, automate, and secure any server — without the expertise.
**Category:** AI-powered server management platform

**Core value proposition:**
- Manage any server — Linux, Windows Server, shared hosting — without technical knowledge
- Describe what you want in plain English (or any language) — AI handles the rest
- AI plans, validates, and executes commands safely with real-time output
- Plain English explanations of everything that happens
- One-click script library for common tasks
- AI-generated custom scripts on demand

**Target users:** Founders, designers, agencies, bloggers, small businesses who own servers or hosting accounts but don't know system administration.

**Competitors we beat:**
- RunCloud, Ploi, ServerPilot — Linux-only, technical, no AI
- cPanel, Plesk — dated UI, no AI, technical
- We win on: AI-native, any OS, any hosting, any language, non-technical UX

---

## 🖥️ Developer Environment

- **Machine:** Mac Mini M4 (Apple Silicon — ARM64)
- **OS:** macOS
- **Editor/Agent:** Claude Code (latest)
- **Docker:** Docker Desktop for Mac (Apple Silicon)
- **Node:** v20+ (via Homebrew)
- **Python:** 3.12 (via Homebrew)
- **JS Package manager:** npm
- **Python package manager:** pip + venv
- **Version control:** Git + GitHub (private repo)

### Local Dev URLs
| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Redis | localhost:6379 |
| PostgreSQL | localhost:5432 |

---

## 🌍 Supported Platforms

### Server Mode (direct SSH / WinRM access)
| Platform | Protocol | Status |
|---|---|---|
| Ubuntu 20.04+ | SSH (Paramiko) | Phase 2 |
| Debian 11+ | SSH (Paramiko) | Phase 2 |
| CentOS / AlmaLinux / Rocky | SSH (Paramiko) | Phase 2 |
| Fedora | SSH (Paramiko) | Phase 2 |
| Windows Server 2016/2019/2022/2025 | WinRM (pywinrm) | Phase 2B |
| FreeBSD | SSH (Paramiko) | Backlog |

### Hosting Mode (panel API + limited SSH)
| Platform | Connection | Status |
|---|---|---|
| CyberPanel | API + SSH | Phase 7 |
| cPanel / WHM | API + SSH | Phase 7 |
| Plesk | API + SSH | Phase 7 |
| DirectAdmin | API + SSH | Phase 7 |

---

## 🤖 AI Multilingual Support

ServerAlly AI responds in the user's preferred language.
The AI system prompt always includes: `"Respond in {user_language}. User may write in {user_language}."`

**Launch languages:**
- English (default)
- Bengali (বাংলা)
- Arabic (العربية)
- Spanish (Español)
- French (Français)
- Hindi (हिन्दी)
- Portuguese (Português)
- Turkish (Türkçe)

**Implementation:**
- User sets preferred language on signup or in Settings
- Stored in `users.preferred_language` (ISO 639-1 code)
- Passed to every Claude API call in system prompt
- UI strings translated via `react-i18next`
- AI explanations, plan summaries, and post-execution messages all in user's language

---

## 🏗️ Full Project Structure

```
servermind/
├── CLAUDE.md                        ← Master instructions (this file)
├── .env                             ← All secrets — NEVER commit
├── .env.example                     ← Committed template, empty values
├── .gitignore
├── docker-compose.yml               ← Local dev (postgres + redis)
├── docker-compose.prod.yml          ← Production overrides
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── i18n/                      ← Translations
│       │   ├── index.ts
│       │   └── locales/
│       │       ├── en.json
│       │       ├── bn.json
│       │       ├── ar.json
│       │       └── es.json
│       ├── routes/
│       │   ├── Dashboard.tsx          ← Overview all servers
│       │   ├── Servers.tsx            ← Server list
│       │   ├── ServerDetail.tsx       ← Single server view
│       │   ├── Chat.tsx               ← AI chat interface
│       │   ├── Terminal.tsx           ← Full terminal page
│       │   ├── Playbooks.tsx          ← Script library
│       │   ├── PlaybookDetail.tsx     ← Single playbook view
│       │   ├── ScriptGenerator.tsx    ← AI script builder
│       │   ├── MyScripts.tsx          ← User saved scripts
│       │   ├── Scheduler.tsx          ← Scheduled tasks
│       │   ├── FileManager.tsx        ← Server file browser
│       │   ├── Monitoring.tsx         ← Metrics & alerts
│       │   ├── Security.tsx           ← Security audit
│       │   ├── Backups.tsx            ← Backup management
│       │   ├── Logs.tsx               ← Command history
│       │   ├── Team.tsx               ← Team management
│       │   ├── Settings.tsx           ← User/account settings
│       │   └── Auth.tsx               ← Login / register
│       ├── components/
│       │   ├── layout/
│       │   │   ├── Sidebar.tsx
│       │   │   ├── TopBar.tsx
│       │   │   └── Layout.tsx
│       │   ├── server/
│       │   │   ├── ServerCard.tsx
│       │   │   ├── AddServerModal.tsx
│       │   │   ├── ServerMetrics.tsx
│       │   │   └── ConnectionStatus.tsx
│       │   ├── chat/
│       │   │   ├── ChatWindow.tsx
│       │   │   ├── ChatMessage.tsx
│       │   │   ├── CommandPlan.tsx
│       │   │   └── ChatInput.tsx
│       │   ├── terminal/
│       │   │   └── XTerminal.tsx
│       │   ├── playbooks/
│       │   │   ├── PlaybookCard.tsx
│       │   │   ├── PlaybookLibrary.tsx
│       │   │   ├── ScriptPreview.tsx
│       │   │   └── RunPlaybookModal.tsx
│       │   ├── monitoring/
│       │   │   ├── CpuChart.tsx
│       │   │   ├── RamChart.tsx
│       │   │   ├── DiskChart.tsx
│       │   │   └── AlertCard.tsx
│       │   └── shared/
│       │       ├── ConfirmModal.tsx
│       │       ├── EmptyState.tsx
│       │       └── LoadingSpinner.tsx
│       ├── store/
│       │   ├── authStore.ts
│       │   ├── serverStore.ts
│       │   └── uiStore.ts
│       ├── hooks/
│       │   ├── useWebSocket.ts
│       │   ├── useServerMetrics.ts
│       │   └── usePlaybooks.ts
│       ├── api/
│       │   ├── client.ts
│       │   ├── auth.ts
│       │   ├── servers.ts
│       │   ├── commands.ts
│       │   ├── playbooks.ts
│       │   ├── monitoring.ts
│       │   └── files.ts
│       └── types/
│           └── index.ts
│
└── backend/
    ├── requirements.txt
    ├── Dockerfile
    ├── main.py
    ├── alembic.ini
    ├── alembic/
    │   └── versions/
    └── app/
        ├── config.py
        ├── database.py
        ├── models/
        │   ├── user.py
        │   ├── server.py
        │   ├── command_log.py
        │   ├── playbook.py
        │   ├── scheduled_task.py
        │   ├── alert.py
        │   └── team.py
        ├── schemas/
        │   ├── user.py
        │   ├── server.py
        │   ├── command.py
        │   ├── playbook.py
        │   ├── scheduled_task.py
        │   └── monitoring.py
        ├── routers/
        │   ├── auth.py
        │   ├── servers.py
        │   ├── commands.py
        │   ├── playbooks.py
        │   ├── scripts.py
        │   ├── scheduler.py
        │   ├── monitoring.py
        │   ├── files.py
        │   ├── security.py
        │   ├── backups.py
        │   └── team.py
        ├── services/
        │   ├── ssh_service.py          ← Linux/Unix: Paramiko
        │   ├── winrm_service.py        ← Windows Server: pywinrm
        │   ├── connection_manager.py   ← Routes to ssh or winrm by OS
        │   ├── hosting_service.py      ← cPanel/CyberPanel/Plesk APIs
        │   ├── ai_service.py           ← Claude API integration
        │   ├── safety_service.py       ← Command validator
        │   ├── crypto_service.py       ← AES-256-GCM
        │   ├── metrics_service.py      ← CPU/RAM/disk
        │   ├── playbook_service.py     ← Script library
        │   ├── scheduler_service.py    ← Cron management
        │   ├── file_service.py         ← Remote file browser
        │   ├── security_service.py     ← Security audit
        │   ├── backup_service.py       ← Backup orchestration
        │   └── notification_service.py ← Email/webhook alerts
        ├── websocket/
        │   └── terminal.py
        └── workers/
            ├── command_worker.py
            ├── metrics_worker.py
            ├── backup_worker.py
            └── alert_worker.py
```

---

## ⚙️ Tech Stack — Final Decisions

### Frontend
| Tool | Version | Purpose |
|---|---|---|
| React | 19 | UI framework |
| TypeScript | 5.x | Type safety — no `any` allowed |
| Vite | 5.x | Build tool |
| TailwindCSS | 3.x | Styling |
| shadcn/ui | latest | UI components |
| xterm.js | 5.x | Terminal emulator |
| Zustand | 4.x | Client state |
| TanStack Query | 5.x | Server data fetching |
| Socket.io-client | 4.x | WebSocket streaming |
| Recharts | 2.x | Metrics charts |
| React Router | 6.x | Routing |
| Axios | 1.x | HTTP client |
| Monaco Editor | latest | Script editor |
| react-i18next | latest | Multilingual UI |
| date-fns | 3.x | Date formatting |
| lucide-react | latest | Icons |

### Backend
| Tool | Version | Purpose |
|---|---|---|
| Python | 3.12 | Runtime |
| FastAPI | 0.111+ | API framework |
| SQLAlchemy | 2.x async | ORM |
| Alembic | 1.x | Migrations |
| Pydantic | 2.x | Validation |
| Paramiko | 3.x | SSH (Linux/Unix) |
| pywinrm | 0.4.x | WinRM (Windows Server) |
| python-socketio | 5.x | WebSocket |
| Celery | 5.x | Background jobs |
| Redis (redis-py) | 5.x | Cache + queue |
| python-jose | 3.x | JWT |
| passlib + bcrypt | latest | Password hashing |
| cryptography | 42.x | AES-256-GCM |
| anthropic | latest | Claude API SDK |
| python-dotenv | 1.x | .env loading |
| uvicorn | 0.29+ | ASGI server |
| APScheduler | 3.x | Cron tasks |
| aiofiles | 23.x | Async file ops |
| requests | 2.x | cPanel/Plesk API calls |

### Infrastructure
| Service | Local Dev | Production |
|---|---|---|
| PostgreSQL | Docker | Supabase free tier |
| Redis | Docker | Upstash free tier |
| File storage | Local | Cloudflare R2 free tier |
| Frontend | Vite dev server | Static via OLS reverse proxy |
| Backend | Docker / uvicorn | Docker Compose on CyberPanel VPS |
| SSL | None | CyberPanel Let's Encrypt |
| CDN / DDoS | None | Cloudflare free plan |

---

## 🔌 Connection Manager Design

`connection_manager.py` is the single entry point for all server communication.
It detects the server OS type and routes to the correct service.

```python
class ConnectionManager:
    """
    Routes commands to the correct connection service based on server OS.
    - Linux/Unix/BSD → ssh_service.py (Paramiko)
    - Windows Server → winrm_service.py (pywinrm)
    - Hosting panels → hosting_service.py (REST API)
    """

    async def execute(self, server: Server, command: str) -> AsyncIterator[str]:
        if server.connection_type == "ssh":
            return await ssh_service.execute_stream(server, command)
        elif server.connection_type == "winrm":
            return await winrm_service.execute_stream(server, command)
        elif server.connection_type == "hosting":
            return await hosting_service.execute(server, command)

    async def test_connection(self, server: Server) -> ConnectionResult:
        ...

    async def get_metrics(self, server: Server) -> ServerMetrics:
        ...
```

### Windows Server (WinRM) specifics
- Port: 5985 (HTTP) or 5986 (HTTPS)
- Auth: username + password or Kerberos
- Shell: PowerShell 5.1+ or PowerShell 7+
- Package manager: winget (modern) or chocolatey
- Service management: `Get-Service`, `Start-Service`, `Stop-Service`
- Safety blocklist additions for Windows (see Safety section)

### Hosting Panel (API) specifics
- CyberPanel: REST API on port 8090 (HTTPS)
- cPanel: UAPI + WHM API on port 2083/2087
- Plesk: REST API on port 8443
- DirectAdmin: HTTP API on port 2222
- All actions go through panel API — no raw system commands
- Limited to what the panel API exposes (by design — safer for shared hosting)

---

## 🗄️ Complete Database Schema

### users
```sql
id                UUID PRIMARY KEY DEFAULT gen_random_uuid()
email             VARCHAR(255) UNIQUE NOT NULL
password_hash     VARCHAR(255) NOT NULL
name              VARCHAR(255)
avatar_url        VARCHAR(500)
preferred_language VARCHAR(10) DEFAULT 'en'    -- ISO 639-1: 'en','bn','ar','es'
is_active         BOOLEAN DEFAULT true
is_verified       BOOLEAN DEFAULT false
totp_secret       VARCHAR(255)
totp_enabled      BOOLEAN DEFAULT false
created_at        TIMESTAMP DEFAULT now()
updated_at        TIMESTAMP DEFAULT now()
```

### servers
```sql
id                UUID PRIMARY KEY DEFAULT gen_random_uuid()
user_id           UUID REFERENCES users(id) ON DELETE CASCADE
name              VARCHAR(255) NOT NULL
host              VARCHAR(255) NOT NULL
port              INTEGER DEFAULT 22
username          VARCHAR(255) NOT NULL
auth_type         VARCHAR(20) NOT NULL        -- 'password' | 'key'
connection_type   VARCHAR(20) NOT NULL        -- 'ssh' | 'winrm' | 'hosting'
panel_type        VARCHAR(20)                 -- 'cyberpanel'|'cpanel'|'plesk'|null
encrypted_cred    TEXT NOT NULL               -- AES-256-GCM encrypted
fingerprint       TEXT                        -- SSH host fingerprint
os_type           VARCHAR(50)                 -- 'ubuntu'|'debian'|'centos'|'windows'|'freebsd'
os_version        VARCHAR(50)
arch              VARCHAR(20)                 -- 'amd64' | 'arm64' | 'x86'
shell             VARCHAR(20) DEFAULT 'bash'  -- 'bash' | 'powershell' | 'sh'
status            VARCHAR(20) DEFAULT 'unknown'
tags              TEXT[]
notes             TEXT
last_seen         TIMESTAMP
created_at        TIMESTAMP DEFAULT now()
```

### command_logs
```sql
id                UUID PRIMARY KEY DEFAULT gen_random_uuid()
server_id         UUID REFERENCES servers(id) ON DELETE CASCADE
user_id           UUID REFERENCES users(id)
user_input        TEXT NOT NULL
user_language     VARCHAR(10)                 -- language used for this command
ai_plan           JSONB
commands          JSONB
output            TEXT
status            VARCHAR(20)                 -- 'success'|'failed'|'partial'|'blocked'|'pending_approval'
ai_explanation    TEXT                        -- in user's language
risk_level        VARCHAR(10)
execution_ms      INTEGER
created_at        TIMESTAMP DEFAULT now()
```

### playbooks
```sql
id                UUID PRIMARY KEY DEFAULT gen_random_uuid()
slug              VARCHAR(255) UNIQUE NOT NULL
title             VARCHAR(255) NOT NULL
description       TEXT
category          VARCHAR(50)
os_family         VARCHAR(20)                 -- 'linux' | 'windows' | 'both'
script_type       VARCHAR(20)                 -- 'bash' | 'powershell' | 'both'
script_bash       TEXT                        -- bash version
script_powershell TEXT                        -- powershell version
variables         JSONB
access_info       JSONB                       -- "service ready" card template {name,url,username,password,note} with {{HOST}}/{{VAR}} placeholders (migration 010)
supported_os      TEXT[]
est_runtime_sec   INTEGER
is_official       BOOLEAN DEFAULT false
is_public         BOOLEAN DEFAULT false
author_id         UUID REFERENCES users(id)
run_count         INTEGER DEFAULT 0
rating            DECIMAL(3,2)
tags              TEXT[]
version           VARCHAR(20) DEFAULT '1.0.0'
created_at        TIMESTAMP DEFAULT now()
updated_at        TIMESTAMP DEFAULT now()
```

### user_scripts
```sql
id                UUID PRIMARY KEY DEFAULT gen_random_uuid()
user_id           UUID REFERENCES users(id) ON DELETE CASCADE
title             VARCHAR(255) NOT NULL
description       TEXT
script_type       VARCHAR(20)                 -- 'bash' | 'powershell'
script_content    TEXT NOT NULL
variables         JSONB
source            VARCHAR(20)                 -- 'ai_generated' | 'manual' | 'forked'
forked_from       UUID REFERENCES playbooks(id)
tags              TEXT[]
created_at        TIMESTAMP DEFAULT now()
updated_at        TIMESTAMP DEFAULT now()
```

### playbook_runs
```sql
id                UUID PRIMARY KEY DEFAULT gen_random_uuid()
server_id         UUID REFERENCES servers(id) ON DELETE CASCADE
user_id           UUID REFERENCES users(id)
playbook_id       UUID REFERENCES playbooks(id)
user_script_id    UUID REFERENCES user_scripts(id)
variables_used    JSONB
output            TEXT
status            VARCHAR(20)
started_at        TIMESTAMP DEFAULT now()
completed_at      TIMESTAMP
```

### scheduled_tasks
```sql
id                UUID PRIMARY KEY DEFAULT gen_random_uuid()
server_id         UUID REFERENCES servers(id) ON DELETE CASCADE
user_id           UUID REFERENCES users(id)
title             VARCHAR(255) NOT NULL
task_type         VARCHAR(20)                 -- 'command'|'playbook'|'user_script'
payload           JSONB
cron_expression   VARCHAR(100) NOT NULL
human_schedule    VARCHAR(255)
is_active         BOOLEAN DEFAULT true
last_run          TIMESTAMP
last_status       VARCHAR(20)
next_run          TIMESTAMP
created_at        TIMESTAMP DEFAULT now()
```

### server_metrics
```sql
id                UUID PRIMARY KEY DEFAULT gen_random_uuid()
server_id         UUID REFERENCES servers(id) ON DELETE CASCADE
cpu_percent       DECIMAL(5,2)
ram_percent       DECIMAL(5,2)
ram_used_mb       INTEGER
ram_total_mb      INTEGER
disk_percent      DECIMAL(5,2)
disk_used_gb      DECIMAL(10,2)
disk_total_gb     DECIMAL(10,2)
load_1            DECIMAL(6,3)               -- null for Windows
load_5            DECIMAL(6,3)               -- null for Windows
load_15           DECIMAL(6,3)               -- null for Windows
uptime_seconds    BIGINT
recorded_at       TIMESTAMP DEFAULT now()
```

### alerts
```sql
id                UUID PRIMARY KEY DEFAULT gen_random_uuid()
server_id         UUID REFERENCES servers(id) ON DELETE CASCADE
user_id           UUID REFERENCES users(id)
metric            VARCHAR(50)
condition         VARCHAR(20)
threshold         DECIMAL(10,2)
channel           VARCHAR(20)                -- 'email' | 'webhook' | 'slack'
channel_target    VARCHAR(500)
is_active         BOOLEAN DEFAULT true
last_triggered    TIMESTAMP
created_at        TIMESTAMP DEFAULT now()
```

### team_members
```sql
id                UUID PRIMARY KEY DEFAULT gen_random_uuid()
owner_id          UUID REFERENCES users(id) ON DELETE CASCADE
member_id         UUID REFERENCES users(id) ON DELETE CASCADE
role              VARCHAR(20)                -- 'viewer'|'operator'|'admin'
invited_email     VARCHAR(255)
invite_token      VARCHAR(255)
invite_accepted   BOOLEAN DEFAULT false
created_at        TIMESTAMP DEFAULT now()
```

### server_access
```sql
id                UUID PRIMARY KEY DEFAULT gen_random_uuid()
team_member_id    UUID REFERENCES team_members(id) ON DELETE CASCADE
server_id         UUID REFERENCES servers(id) ON DELETE CASCADE
can_execute       BOOLEAN DEFAULT false
can_view_logs     BOOLEAN DEFAULT true
```

---

## 🔐 Security Rules — NEVER Violate These

1. NEVER store credentials in plain text — AES-256-GCM always
2. NEVER log credentials anywhere
3. NEVER return credentials in API responses after creation
4. ALWAYS validate JWT on every protected endpoint
5. ALWAYS run safety_service.validate() before any AI command
6. ALWAYS verify SSH fingerprint on reconnect
7. Role enforcement: viewers cannot execute — check every /commands endpoint
8. Rate limiting: max 30 commands per minute per user per server

### Linux/Unix Absolute Blocklist
```python
LINUX_BLOCKED = [
    r"rm\s+-[rf]+\s+/\s*$",
    r"rm\s+-[rf]+\s+/\*",
    r"mkfs\.",
    r"dd\s+if=/dev/(zero|random)\s+of=/dev/[a-z]+\b",
    r":\(\)\s*\{\s*:\|:&\s*\}",          # fork bomb
    r"chmod\s+-R\s+[0-7]*7[0-7]*\s+/",
    r">\s*/dev/sd[a-z]",
    r"mv\s+/\s+",
    r"chown\s+-R\s+.+\s+/\s*$",
]
```

### Windows/PowerShell Absolute Blocklist
```python
WINDOWS_BLOCKED = [
    r"Format-Volume",
    r"Remove-Item\s+C:\\Windows",
    r"Remove-Item\s+C:\\\*",
    r"rd\s+/s\s+/q\s+C:\\",
    r"del\s+/f\s+/s\s+/q\s+C:\\Windows",
    r"Stop-Computer",                      # shutdown
    r"Restart-Computer",                   # reboot (warn, not block)
    r"Disable-NetAdapter",                 # disable network
    r"Clear-Disk",
    r"Initialize-Disk",
]
```

### Confirm Before Running (all OS)
```python
CONFIRM_PATTERNS = [
    # Linux
    r"apt.*(remove|purge|autoremove)",
    r"(systemctl|service)\s+(stop|disable)",
    r"ufw\s+(disable|reset)",
    r"passwd\s+root",
    r"(wget|curl).+\|\s*(ba)?sh",
    # Windows
    r"Uninstall-WindowsFeature",
    r"Stop-Service",
    r"Disable-WindowsOptionalFeature",
    r"Remove-WindowsFeature",
    # Both
    r"DROP\s+(TABLE|DATABASE)",
    r"crontab\s+-r",
]
```

---

## 🤖 AI Service Design

### Chat System Prompt (all platforms)
```
You are ServerAlly AI, an expert server administrator.
You help non-technical users manage their servers safely using natural language.

SERVER CONTEXT:
- Name: {server_name}
- OS: {os_type} {os_version}
- Platform: {connection_type}     ← ssh | winrm | hosting
- Shell: {shell}                  ← bash | powershell
- Architecture: {arch}
- Known installed: {installed_packages}
- Recent history: {recent_history}

LANGUAGE: Respond in {user_language}. User may write in {user_language}.

RULES:
1. Use the correct shell for the OS — bash for Linux/Unix, PowerShell for Windows
2. For Linux: apt (Ubuntu/Debian), dnf (Fedora/RHEL), yum (CentOS 7)
3. For Windows: winget or chocolatey for packages, Get-Service for services
4. For hosting panels: describe UI actions or use panel-specific CLI tools
5. Always check if software is already installed before installing
6. Always include a verification step after installation
7. Never suggest commands that risk data loss without flagging risk_level as 'high'
8. If ambiguous, ask ONE clarifying question before proceeding
9. Keep explanations friendly and jargon-free — user is non-technical
10. Respond entirely in the user's language including technical explanations

ALWAYS RESPOND WITH VALID JSON ONLY:
{
  "intent_understood": "...",
  "clarification_needed": null,
  "plan_summary": "...",
  "commands": [
    {
      "cmd": "exact command string",
      "description": "plain language explanation",
      "risk_level": "low | medium | high",
      "requires_confirmation": false
    }
  ],
  "estimated_duration_seconds": 30,
  "post_execution_message": "...",
  "follow_up_suggestions": ["...", "..."]
}
```

### Script Generator Prompt
```
You are ServerAlly Script Generator.
Create production-ready scripts for server administration.

Target OS family: {os_family}       ← linux | windows | both
Shell: {shell}                       ← bash | powershell
User language: {user_language}
Request: {user_request}

For bash scripts:
- Start with: #!/bin/bash
- Set strict mode: set -euo pipefail
- Detect OS at runtime
- Use trap EXIT for cleanup

For PowerShell scripts:
- Start with: #Requires -Version 5.1
- Use Set-StrictMode -Version Latest
- Use try/catch for error handling
- Use Write-Host for progress messages

Both:
- Clear header comment (title, description, author: ServerAlly AI, date)
- Check prerequisites before running
- Clear progress messages
- Handle errors gracefully
- Customizable variables at top
- Inline comments explaining non-obvious steps
- Success summary at end

RESPOND WITH JSON:
{
  "title": "...",
  "description": "...",
  "script_type": "bash | powershell",
  "estimated_runtime_seconds": 120,
  "variables": [
    {"name": "VAR", "label": "...", "default": "...", "required": true}
  ],
  "script": "full script content",
  "post_run_instructions": "...",
  "warnings": ["..."]
}
```

### AI Execution Flow
```
user_input (any language)
  → ai_service.plan_commands(input, server_context, user_language)
  → safety_service.validate_plan(plan, server.os_family)
      → BLOCKED → return blocked message in user_language
      → CONFIRM → return plan to frontend for approval
      → OK → proceed
  → ws: send { type: "plan", plan }
  → for each command:
      → connection_manager.execute(server, cmd)   ← routes to ssh/winrm/hosting
      → ws: stream output chunks
  → ai_service.explain_output(output, plan, user_language)
  → ws: send { type: "complete", explanation }
  → save command_log to DB
```

---

## 🌐 Hosting Mode Feature Design

When `connection_type = "hosting"`, ServerAlly connects via panel API instead of raw SSH.

### What AI can do in Hosting Mode

**Website Management**
- Create / delete websites and subdomains
- Change document root
- Change PHP version per domain
- View / edit .htaccess
- View access logs and error logs
- Enable/disable site

**SSL**
- Issue Let's Encrypt certificate
- Renew certificate
- Force HTTPS redirect

**Database**
- Create MySQL/MariaDB database
- Create database user + assign permissions
- Delete database
- Import/export SQL file

**Email**
- Create email account
- Set email forwarder
- Set autoresponder
- View mail logs

**DNS**
- Add/edit/delete DNS records
- Change nameservers

**File Management**
- Browse files via File Manager API
- Upload files
- Set file permissions
- Extract archives

**WordPress (via WP-CLI where available)**
- Install WordPress
- Update core/plugins/themes
- Reset admin password
- Clear cache
- Enable/disable maintenance mode
- Fix file permissions

### Hosting Mode AI Examples
```
User: "My WordPress site shows a white screen"
AI: Checks error logs → identifies PHP error → suggests fix → applies with approval

User: "Create a staging subdomain for mysite.com"
AI: Creates subdomain via panel API → copies files → updates wp-config

User: "My SSL certificate is expired"
AI: Triggers Let's Encrypt renewal via panel API → verifies → confirms success

User: "Increase PHP memory limit for my site"
AI: Updates php.ini or .htaccess → restarts PHP-FPM → verifies change
```

---

## 📋 Complete API Endpoints

### Auth
```
POST   /api/auth/register
POST   /api/auth/login
POST   /api/auth/refresh
POST   /api/auth/logout
GET    /api/auth/me
PUT    /api/auth/me
PUT    /api/auth/password
PUT    /api/auth/language          ← update preferred language
POST   /api/auth/2fa/enable
POST   /api/auth/2fa/verify
DELETE /api/auth/2fa
```

### Servers
```
GET    /api/servers
POST   /api/servers
GET    /api/servers/{id}
PUT    /api/servers/{id}
DELETE /api/servers/{id}
POST   /api/servers/{id}/test      ← test SSH/WinRM/API connection
POST   /api/servers/{id}/detect    ← detect OS, arch, shell, installed packages
GET    /api/servers/{id}/metrics
GET    /api/servers/{id}/metrics/history
GET    /api/servers/{id}/processes
GET    /api/servers/{id}/services
POST   /api/servers/{id}/services/{name}/start
POST   /api/servers/{id}/services/{name}/stop
POST   /api/servers/{id}/services/{name}/restart
```

### AI Chat & Commands
```
POST   /api/servers/{id}/chat
POST   /api/servers/{id}/chat/approve
POST   /api/servers/{id}/chat/cancel
GET    /api/servers/{id}/history
GET    /api/commands/{log_id}
DELETE /api/commands/{log_id}
GET    /api/activity                  ← unified feed: AI commands + playbook runs (newest first)
```

### Playbooks
```
GET    /api/playbooks
GET    /api/playbooks/categories
GET    /api/playbooks/{id}
POST   /api/playbooks/{id}/run
GET    /api/playbooks/runs/{run_id}
GET    /api/servers/{id}/playbook-history
POST   /api/admin/playbooks
PUT    /api/admin/playbooks/{id}
```

### User Scripts
```
GET    /api/scripts
POST   /api/scripts
POST   /api/scripts/generate
PUT    /api/scripts/{id}
DELETE /api/scripts/{id}
POST   /api/scripts/{id}/run
POST   /api/scripts/{id}/fork
POST   /api/scripts/{id}/publish
```

### Scheduler
```
GET    /api/servers/{id}/schedules
POST   /api/servers/{id}/schedules
PUT    /api/schedules/{id}
DELETE /api/schedules/{id}
POST   /api/schedules/{id}/toggle
GET    /api/schedules/{id}/runs
POST   /api/schedules/{id}/run-now
```

### File Manager
```
GET    /api/servers/{id}/files
GET    /api/servers/{id}/files/read
POST   /api/servers/{id}/files/write
POST   /api/servers/{id}/files/mkdir
DELETE /api/servers/{id}/files
POST   /api/servers/{id}/files/upload
GET    /api/servers/{id}/files/download
POST   /api/servers/{id}/files/rename
```

### Monitoring & Alerts
```
GET    /api/servers/{id}/alerts
POST   /api/servers/{id}/alerts
PUT    /api/alerts/{id}
DELETE /api/alerts/{id}
POST   /api/alerts/{id}/test
GET    /api/servers/{id}/security
POST   /api/servers/{id}/security/scan
```

### Backups
```
GET    /api/servers/{id}/backups
POST   /api/servers/{id}/backups
PUT    /api/backups/{id}
DELETE /api/backups/{id}
POST   /api/backups/{id}/run
GET    /api/backups/{id}/history
POST   /api/backups/{id}/restore
```

### Team
```
GET    /api/team
POST   /api/team/invite
PUT    /api/team/{member_id}
DELETE /api/team/{member_id}
GET    /api/team/{member_id}/access
PUT    /api/team/{member_id}/access
POST   /api/team/accept/{token}
```

### WebSocket
```
WS     /ws/{server_id}             ← terminal stream
WS     /ws/metrics/{server_id}     ← live metrics (1s updates)
```

---

## 🌊 WebSocket Message Protocol

### Client → Server
```json
{ "type": "subscribe_execution", "command_log_id": "uuid" }
{ "type": "approve", "command_log_id": "uuid" }
{ "type": "cancel", "command_log_id": "uuid" }
{ "type": "ping" }
```

### Server → Client
```json
{ "type": "plan", "summary": "...", "commands": [...], "requires_approval": false }
{ "type": "command_start", "index": 0, "total": 3, "cmd": "...", "description": "..." }
{ "type": "output", "data": "chunk", "stream": "stdout" }
{ "type": "output", "data": "error", "stream": "stderr" }
{ "type": "command_done", "index": 0, "exit_code": 0, "duration_ms": 1200 }
{ "type": "execution_complete", "status": "success", "explanation": "..." }
{ "type": "blocked", "reason": "...", "pattern": "..." }
{ "type": "error", "message": "Connection lost — retrying..." }
{ "type": "pong" }
```

---

## 📦 Script Library — Official Playbooks

### Linux Playbooks

**Server Setup**
| Slug | Title | Time |
|---|---|---|
| lamp-stack | LAMP Stack (Apache + MySQL + PHP) | 3 min |
| lemp-stack | LEMP Stack (Nginx + MySQL + PHP) | 3 min |
| docker | Docker + Docker Compose | 2 min |
| nodejs-pm2 | Node.js LTS + PM2 | 1 min |
| python-env | Python 3 + pip + virtualenv | 1 min |
| swap-file | Create and Enable Swap File | 30 sec |
| set-timezone | Set Server Timezone | 10 sec |

**Security**
| Slug | Title | Time |
|---|---|---|
| initial-hardening | Initial Server Security Hardening | 2 min |
| ufw-setup | UFW Firewall Setup | 1 min |
| fail2ban | Fail2Ban Install + Config | 1 min |
| ssh-key-auth | Enforce SSH Key Auth Only | 1 min |
| letsencrypt | Certbot + SSL Certificate | 2 min |
| security-audit | Full Security Audit Report | 2 min |

**Backup & Restore**
| Slug | Title | Time |
|---|---|---|
| mysql-backup-local | MySQL Auto Backup (local) | 1 min |
| mysql-backup-s3 | MySQL Auto Backup to S3 | 2 min |
| postgres-backup | PostgreSQL Auto Backup | 1 min |
| rclone-setup | Rclone Cloud Sync Setup | 3 min |

**App Deployment**
| Slug | Title | Time |
|---|---|---|
| wordpress | WordPress (Nginx + MySQL) | 5 min |
| ghost-cms | Ghost CMS | 5 min |
| nextcloud | Nextcloud | 8 min |
| portainer | Portainer (Docker UI) | 1 min |
| uptime-kuma | Uptime Kuma | 1 min |
| gitea | Gitea (self-hosted Git) | 3 min |
| n8n | n8n (workflow automation) | 2 min |
| vaultwarden | Vaultwarden (Bitwarden) | 2 min |
| nodejs-app-github | Deploy Node.js App from GitHub | 3 min |

**Monitoring**
| Slug | Title | Time |
|---|---|---|
| netdata | Netdata Real-time Monitoring | 2 min |
| prometheus-grafana | Prometheus + Grafana Stack | 5 min |
| disk-alert | Disk Usage Email Alert | 1 min |

**Maintenance**
| Slug | Title | Time |
|---|---|---|
| full-update | Full System Update + Cleanup | 2 min |
| clean-logs | Clear Old Logs + Temp Files | 1 min |
| find-large-files | Large Files Report | 30 sec |

**Control Panels** — category `control-panel`. Each runs a shared **pre-flight guard** (root + clean-box + supported-OS + RAM checks) before the official vendor installer, aborting with a plain-English message on a dirty/unsupported server, and shows a panel URL/login **access card** on success.

*Free / open-source*
| Slug | Title | Notes |
|---|---|---|
| cyberpanel | CyberPanel (OpenLiteSpeed) | Ubuntu 20.04/22.04, AlmaLinux 8 · admin-password input |
| hestiacp | HestiaCP | Ubuntu/Debian · email + password + hostname inputs |
| aapanel | aaPanel | Ubuntu/Debian/CentOS/AlmaLinux · login printed in install log |
| cloudpanel | CloudPanel | Debian 11/12, Ubuntu 22.04/24.04 · 2 GB RAM · set admin on first visit |

*Premium (license required)*
| Slug | Title | Notes |
|---|---|---|
| cpanel-whm | cPanel / WHM | AlmaLinux/Rocky/CloudLinux/CentOS7/Ubuntu (not Debian) · 2 GB RAM · WHM :2087 · 15-day trial |
| plesk | Plesk | Ubuntu/Debian/AlmaLinux/Rocky/CentOS 8-9 · 2 GB RAM · :8443 · admin-password input · trial on first login |
| directadmin | DirectAdmin | AlmaLinux/Rocky/Ubuntu/Debian · :2222 · **license key required** |

> ⚠️ Control-panel playbooks use official vendor installers and are `bash -n` syntax-checked, but were **not** run end-to-end (each needs a *fresh* VPS). CyberPanel drives an interactive installer via piped answers (version-sensitive); the other six are non-interactive by design. Validate on a clean box before relying on them.

---

### Windows Server Playbooks

**Server Setup**
| Slug | Title | Time |
|---|---|---|
| win-iis | Install IIS Web Server | 2 min |
| win-docker | Install Docker Desktop / Docker Engine | 3 min |
| win-nodejs | Install Node.js LTS + PM2 | 2 min |
| win-chocolatey | Install Chocolatey Package Manager | 1 min |
| win-openssh | Enable OpenSSH Server | 1 min |

**Security**
| Slug | Title | Time |
|---|---|---|
| win-firewall | Configure Windows Firewall Rules | 2 min |
| win-updates | Enable Automatic Windows Updates | 1 min |
| win-rdp-secure | Harden RDP Access | 2 min |
| win-audit | Windows Security Audit Report | 3 min |

**App Deployment**
| Slug | Title | Time |
|---|---|---|
| win-wordpress-iis | WordPress on IIS + MySQL | 8 min |
| win-sqlserver-express | SQL Server Express Install | 5 min |
| win-aspnet | ASP.NET Core App Deploy | 3 min |

---

## 🗓️ Scheduler — Natural Language to Cron

```
"every night at 2am"              → 0 2 * * *
"every Sunday at midnight"        → 0 0 * * 0
"every hour"                      → 0 * * * *
"every 15 minutes"                → */15 * * * *
"first day of every month at 3am" → 0 3 1 * *
"every weekday at 9am"            → 0 9 * * 1-5
"twice a day"                     → 0 9,21 * * *
```

AI parses natural language → cron expression → shown to user for confirmation before saving.

---

## 🔑 Environment Variables (.env)

```bash
# App
APP_ENV=development
APP_NAME=ServerAlly
SECRET_KEY=                     # python -c "import secrets; print(secrets.token_hex(32))"
ENCRYPTION_KEY=                 # python -c "import secrets; print(secrets.token_hex(32))"

# Database
DATABASE_URL=postgresql+asyncpg://servermind:password@localhost:5432/servermind

# Redis
REDIS_URL=redis://localhost:6379/0

# Claude API
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514

# JWT
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS
ALLOWED_ORIGINS=http://localhost:5173

# Email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
EMAIL_FROM=noreply@serverally.ai

# Cloudflare R2
R2_ACCOUNT_ID=
R2_ACCESS_KEY=
R2_SECRET_KEY=
R2_BUCKET=serverally-logs

# Frontend
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
VITE_APP_NAME=ServerAlly
VITE_APP_TAGLINE=Your AI companion to manage, automate, and secure any server — without the expertise.
```

---

## 📋 Build Phases & Checklist

### ✅ Phase 0 — Project Scaffold
- [x] Create full folder structure
- [x] docker-compose.yml (postgres 16 + redis 7)
- [x] .env + .env.example
- [x] .gitignore
- [x] Backend: FastAPI skeleton + /health endpoint
- [x] Backend: config.py with Pydantic settings
- [x] Frontend: React + Vite + TypeScript
- [x] Frontend: TailwindCSS + shadcn/ui
- [x] Frontend: React Router layout
- [x] Frontend: react-i18next setup (en + bn locales)
- [x] Confirm everything runs locally

### ✅ Phase 1 — Auth System
- [x] users table + migration (with preferred_language field)
- [x] crypto_service.py (AES-256-GCM)
- [x] /auth endpoints (register, login, refresh, me)
- [x] JWT middleware
- [x] Language preference endpoint
- [x] Frontend: Login + Register pages
- [x] Frontend: authStore (Zustand)
- [x] Frontend: Protected route wrapper
- [x] Frontend: Language selector on register + settings

### ✅ Phase 2 — Linux Server Management (SSH)
- [x] servers table + migration
- [x] ssh_service.py (Paramiko: connect, test, execute, stream)
- [x] connection_manager.py (routes by connection_type)
- [x] metrics_service.py (CPU/RAM/disk via SSH)
- [x] OS detection on server add
- [x] /servers CRUD + test + detect + metrics endpoints
- [x] Frontend: Add Server modal
- [x] Frontend: Server list + Server detail with metrics

### ✅ Phase 2B — Windows Server Management (WinRM)
- [x] winrm_service.py (pywinrm: test/execute/execute_stream/close; NTLM transport; 5985 HTTP / 5986 HTTPS by port; session cache; CLIXML error cleanup; runs in ThreadPoolExecutor) + requests-ntlm dep
- [x] connection_manager routes connection_type=='winrm' for test/execute/execute_stream/close
- [x] Windows metrics collection (PowerShell Win32_OperatingSystem/Processor/LogicalDisk → same JSON keys as Linux; load avg null)
- [x] Windows OS detection (PowerShell Win32_OperatingSystem caption/version + PROCESSOR_ARCHITECTURE)
- [x] Windows safety blocklist already wired in safety_service (os_family=='windows' → WINDOWS_BLOCKED)
- [x] create_server sets shell='powershell' for winrm; AddServerModal defaults port 5985 + forces password/NTLM; interactive PTY terminal guarded to SSH-only (winrm uses AI Chat which streams via execute_stream)
- [x] Tested: winrm_service execute/test/stream, connection_manager routing, Windows metrics+detect parsing — all via mocked pywinrm (no live Windows host available for a real WinRM handshake; security/playbook Windows batteries now activate automatically for winrm servers)

### ✅ Phase 3 — AI Chat + Terminal
- [x] command_logs table + migration
- [x] ai_service.py (plan_commands with OS + language awareness)
- [x] safety_service.py (Linux + Windows blocklists)
- [x] WebSocket terminal handler (/ws/terminal + /ws/chat)
- [x] /api/servers/{id}/history + /api/commands/{id} endpoints
- [x] Frontend: XTerminal.tsx (xterm.js with PTY + resize)
- [x] Frontend: ChatWindow.tsx with multilingual support
- [x] Frontend: CommandPlan.tsx (show plan before executing)
- [x] Frontend: ChatMessage.tsx, ChatInput.tsx components
- [x] Frontend: useWebSocket.ts hook
- [x] Chat + Terminal routes wired into ServerDetail

### ✅ Phase 4 — Playbooks (Script Library)
- [x] playbooks + playbook_runs tables + migration
- [x] Dual script support (bash + powershell per playbook)
- [x] Seed all official Linux playbooks
- [x] Seed all official Windows playbooks
- [x] /playbooks endpoints
- [x] Frontend: Playbooks page (OS filter + category tabs + search)
- [x] Frontend: PlaybookCard, ScriptPreview, RunPlaybookModal

### ✅ Phase 5 — AI Script Generator
- [x] user_scripts table + migration (in 004, already ran)
- [x] ai_service.generate_script() (bash or PowerShell based on server OS)
- [x] /scripts endpoints (list, create, get, update, delete, generate)
- [x] Frontend: ScriptGenerator.tsx (OS selector, examples, Monaco editor, save)
- [x] Frontend: MyScripts.tsx (filter, search, detail panel, run via WS)

### ✅ Phase 6 — Scheduler
- [x] scheduled_tasks table + migration (005_create_scheduled_tasks.py)
- [x] scheduler_service.py (APScheduler AsyncIOScheduler, load_all_tasks on startup)
- [x] Natural language → cron (AI-assisted via ai_service.parse_schedule + /api/parse-schedule endpoint)
- [x] /schedules endpoints (list, create, update, delete, toggle, run-now)
- [x] Frontend: Scheduler.tsx (task cards, new task modal with live cron preview)

### ✅ Phase 7 — Hosting Mode
- [x] hosting_service.py — adapter architecture (_Adapter base + per-panel subclasses) with uniform async dispatch; requests via asyncio.to_thread, verify=False (self-signed panels), HostingError → HTTP 502
- [x] CyberPanelAdapter (cloud JSON API, port 8090; adminUser/adminPass in each POST): verifyLogin, fetchWebsites, createWebsite, submitWebsiteDeletion, issueSSL, createDatabase
- [x] CpanelAdapter (UAPI, port 2083; `Authorization: cpanel user:token`): list_domains, list/create databases, list/create email
- [x] PleskAdapter (REST API v2, port 8443; Basic auth): server, list/create domains
- [x] connection_manager routes connection_type=='hosting' → hosting_service.test_connection
- [x] Hosting-aware AI prompt: hosting servers get _HOSTING_NOTE → AI returns empty commands[] and panel UI steps instead of shell commands
- [x] /api/servers/{id}/hosting/* router: websites (list/create/delete/ssl), databases (list/create), email (list/create); reads=view, writes=need_execute
- [x] Frontend: AddServerModal panel-type selector (CyberPanel/cPanel/Plesk) with auto port + password/token labels; create_server stays connection_type='hosting'
- [x] Frontend: Hosting.tsx dashboard (Websites/Databases/Email tabs, create modals, Issue-SSL + delete actions) + api/hosting.ts + conditional Hosting link in ServerDetail
- [x] Tested: all three adapters' auth/parse/error paths + dispatch via mocked requests (no live panel available; endpoint strings follow documented vendor APIs and need live validation per panel version)

### ✅ Phase 8 — File Manager
- [x] file_service.py (SFTP via Paramiko pool, async ThreadPoolExecutor, 2 MB read cap, binary detection)
- [x] /files endpoints (list, read, write, mkdir, delete, rename, upload multipart, download octet-stream)
- [x] Frontend: FileManager.tsx (breadcrumb nav, file table, Monaco Editor panel, download via apiClient blob)
- [x] Files quick-link added to ServerDetail.tsx

### ✅ Phase 9 — Monitoring & Alerts
- [x] server_metrics + alerts tables + migration (006_create_metrics_and_alerts.py)
- [x] metrics_worker.py (APScheduler job every 5 min, 7-day retention, marks server online/offline)
- [x] alert_worker.py (threshold checks, 1-hr cooldown) + notification_service.py (email SMTP + webhook/Slack)
- [x] /alerts CRUD + toggle + test + /metrics/history endpoints (hours param, up to 168h)
- [x] Frontend: Monitoring.tsx (stat cards, 3 area charts, time window selector, alert rules manager)

### ✅ Phase 10 — Security Audit
- [x] security_scans table + model + migration (007_create_security_scans.py)
- [x] security_service.py (single-script section battery; 19 Linux checks across ssh/firewall/updates/accounts/filesystem/services/hardening/kernel; 5 Windows/PowerShell checks staged for Phase 2B; severity scoring 0-100 + A-F grade; all read-only probes)
- [x] /api/servers/{id}/security (history) + /api/servers/{id}/security/scan endpoints
- [x] Frontend: Security.tsx (score ring, severity count chips, grouped findings with copyable fix commands, passing-checks toggle, scan history) + api/security.ts
- [x] Security quick-link added to ServerDetail.tsx

### ✅ Phase 11 — Backups
- [x] backups + backup_runs tables + models + migration (008_create_backups.py)
- [x] backup_service.py (files=tar.gz, mysql=mysqldump, postgres=pg_dump; gzip to dest_dir; retention prune of oldest beyond keep-N; restore via tar -x / mysql / psql; shlex-quoted commands; DB passwords AES-256-GCM at rest and passed via MYSQL_PWD/PGPASSWORD env, never on argv)
- [x] Optional cron scheduling integrated with APScheduler (schedule_backup/unschedule_backup/load_all_backups on startup; job-id namespaced "backup:")
- [x] /backups endpoints (list, create, update, delete, run, history, restore) — restore picks given run or latest successful backup
- [x] Frontend: Backups.tsx (job cards, type-aware New/Edit modal with NL→cron preview via parseSchedule, run/restore/history, destructive restore confirm) + api/backups.ts
- [x] Backups quick-link added to ServerDetail.tsx

### ✅ Phase 12 — Team Management
- [x] team_members + server_access tables + migration (009_create_team_tables.py)
- [x] team_service.py — access model (owner/admin/operator/viewer) + get_access/accessible_servers primitives; invite/accept (email-bound token)/list/role/remove + per-server access set/get
- [x] dependencies/access.py — resolve_server(need_execute, need_manage) shared by all server-scoped routers
- [x] Role enforcement on every execution path (CLAUDE.md rule 7): websocket terminal+chat+playbook-run, files write/mkdir/delete/rename/upload, backups create/run/restore, security scan, scheduler create — all require can_execute; servers update/delete require owner/admin (need_manage). A viewer can NEVER execute even if granted can_execute (role override, unit-tested against Postgres).
- [x] Read endpoints (servers list/detail, commands history, monitoring, files read, security history, backups list) made team-aware via accessible_servers / get_access
- [x] /team endpoints (list, invite, update role, remove, get/set access, accept/{token})
- [x] Frontend: Team.tsx (member list, role selector, invite modal, per-server access editor, shareable invite link) + AcceptInvite.tsx route + api/team.ts

### ✅ Phase 13 — Production Deploy
- [x] docker-compose.prod.yml (backend + frontend services; managed Postgres/Redis via env, optional `selfhost` profile for bundled pg+redis; backend runs migrations then uvicorn single-process; healthchecks; internal network)
- [x] Frontend build → static files (multi-stage Dockerfile node→nginx; nginx.conf serves SPA + proxies /api and /ws to backend, gzip, asset caching, security headers; .dockerignore)
- [x] CyberPanel subdomain + reverse proxy → documented in DEPLOY.md (OLS rewrite → 127.0.0.1:8080, WebSocket proxy context)
- [x] CyberPanel Let's Encrypt SSL → documented in DEPLOY.md (issue + force-HTTPS)
- [x] Sentry integration (sentry-sdk[fastapi]; conditional init on SENTRY_DSN; env+release tags; never breaks startup)
- [x] Production env vars (config: APP_VERSION, ENABLE_SCHEDULER, SENTRY_DSN; .env.example updated; .gitignore now excludes .env.prod/.env.* but keeps .env.example; APP_ENV=production hides /docs)
- [x] Scheduler-safety: ENABLE_SCHEDULER flag gates APScheduler/metrics/backup jobs so horizontal web scaling doesn't fire jobs N times
- [x] Smoke test all platforms → DEPLOY.md §8 checklist (Linux SSH, Windows WinRM, hosting, playbooks/scripts/scheduler/security/backups/team/websockets)
- [x] DEPLOY.md runbook (datastores → .env.prod → build → reverse proxy → SSL → Sentry → smoke tests → operations/scaling/backup notes)
- [x] Verified: backend imports (83 routes), `docker compose config` valid for default + selfhost profiles

---

## 💡 Future Features Backlog

### Intelligence
- [ ] Proactive AI suggestions based on server health
- [ ] AI anomaly detection (unusual CPU/RAM patterns)
- [ ] Auto-healing: detect crashed services → restart automatically
- [ ] AI server health score (0-100) with recommendations
- [ ] Context memory: AI remembers what's installed per server

### Integrations
- [ ] GitHub: deploy from repo to server
- [ ] DigitalOcean API: import droplets
- [ ] Hetzner API: import cloud servers
- [ ] AWS EC2: import instances
- [ ] Cloudflare API: manage DNS from ServerAlly
- [ ] Slack bot: alerts + commands from Slack
- [ ] Telegram bot: mobile management
- [ ] Zapier / n8n webhooks

### Developer Tools
- [ ] Docker management UI (containers, images, volumes)
- [ ] NGINX config builder (GUI → generates config)
- [ ] Database GUI (query MySQL/PostgreSQL in browser)
- [ ] Git deploy: pull + restart in one step
- [ ] CI/CD webhooks on GitHub push

### Platform
- [ ] Command marketplace (community scripts)
- [ ] Script rating + comments
- [ ] More languages (Turkish, Indonesian, Urdu, Malay)
- [ ] Dark/light mode toggle
- [ ] Desktop app (Electron)
- [ ] Mobile app (React Native)
- [ ] CLI: `servermind run "install nginx" --server myserver`
- [ ] API access for users (build on top of ServerAlly)
- [ ] White-label for agencies
- [ ] **Self-hosted licensed edition** — license system (online activation + periodic re-check + grace period), one-command installer + setup wizard, multi-provider bring-your-own AI key (Claude/OpenAI/Gemini) **or** an optional hosted "ServerAlly AI" subscription, in-app updater; sell keys via Lemon Squeezy/Gumroad/Paddle. Target agencies/MSPs. See [docs/SELF-HOSTED-LICENSING.md](docs/SELF-HOSTED-LICENSING.md)

---

## 🚦 Coding Standards

### Python
- Type hints on all parameters and returns
- Async/await for all I/O
- FastAPI `Depends()` for dependency injection
- `logging` module only — no `print()`
- `HTTPException` for all HTTP errors
- Pydantic schemas for all request/response
- Docstring on every function

### TypeScript
- No `any` types
- TanStack Query for all server data
- Zustand for client-only state
- Split components over 150 lines
- shadcn/ui before custom components
- JSDoc on exported functions and hooks

### Git Commits
```
feat: add WinRM connection service for Windows Server
fix: handle PowerShell output encoding on Windows
chore: add windows_blocked patterns to safety_service
docs: update Phase 2B checklist in CLAUDE.md
refactor: extract connection routing to connection_manager
i18n: add Bengali translations for chat UI
```

---

## 🐛 Decisions Log

| Date | Decision | Reason |
|---|---|---|
| Day 1 | Product name: ServerAlly | Clear, memorable, AI-native |
| Day 1 | Tagline: Manage any server in natural language | Clear double meaning, six words |
| Day 1 | Removed "Linux" from positioning | Support any OS — bigger market |
| Day 1 | Python + FastAPI backend | Best LLM ecosystem |
| Day 1 | Paramiko for SSH (Linux) | Mature, battle-tested |
| Day 1 | pywinrm for WinRM (Windows) | Standard Python WinRM library |
| Day 1 | connection_manager.py routing pattern | Single entry point for all OS types |
| Day 1 | Multilingual AI from day one | Huge market in non-English regions |
| Day 1 | Hosting mode (Phase 7) | Massive shared hosting user base |
| Day 1 | Supabase free tier for prod DB | Zero cost |
| Day 1 | Upstash free tier for prod Redis | Zero cost |
| Day 1 | CyberPanel VPS for hosting | Zero extra infra cost |
| Day 1 | Monaco Editor for scripts | VS Code editor — familiar to users |
| 2026-06-23 | Control panels via official vendor installers + shared pre-flight guard | Vendor-supported & reliable; guard blocks dirty/unsupported servers with a plain message (non-technical UX) |
| 2026-06-23 | Playbooks declare `access_info`; frontend renders the access card client-side | Show panel/app URL + login after install without storing any secret server-side |
| 2026-06-23 | `execute_stream` merges stderr & raises on non-zero exit | stderr was dropped (live output looked frozen) and failed runs falsely reported success |
| 2026-06-23 | Built Dashboard, Activity Log (+ `/api/activity`), Settings pages | Replaced Phase-1 placeholders with real, data-driven pages |
| 2026-06-23 | Local dev: backend :8888, frontend :5190, Vite proxy → 127.0.0.1 | 8000/8080/5173 taken by other local projects; IPv4 avoids the localhost→::1 miss (see OPS.md) |
| 2026-06-28 | Offer a self-hosted, licensed edition (not only SaaS) | Privacy — credentials never leave the customer's box — is a strong differentiator for a credentials-handling tool; near-zero infra cost/liability; app already Docker-packaged. Target agencies/MSPs. See docs/SELF-HOSTED-LICENSING.md |
| 2026-06-29 | Multi-provider AI via `llm_service` (bring-your-own-key) | Decouple from a single vendor; customers use Claude/OpenAI/Gemini/OpenAI-compatible with their own key — foundation for the self-hosted edition. `anthropic` stays the default (backward-compatible). See docs/UPDATE-20-MULTI-PROVIDER-AI.md |
| 2026-06-29 | Hosted "ServerAlly AI" subscription via a standalone gateway (`gateway/`) | Customers without an AI key can use our AI for a subscription — broader reach + recurring revenue. OpenAI-compatible proxy: validates the subscription token, forwards to our upstream key, meters monthly usage. Billing-webhook + token metering are follow-ups. See docs/UPDATE-20-MULTI-PROVIDER-AI.md |
| 2026-06-29 | Per-playbook OS guard (Tier 1) — infer supported OS from the script; grey-out/refuse incompatible servers | Stop cryptic cross-OS failures (apt on AlmaLinux); be honest about which OS each playbook supports. Inferred from package manager (apt→Debian/Ubuntu, dnf→RHEL); never blocks on unknown OS. Tier 2 = make popular playbooks multi-distro. See docs/UPDATE-21-OS-GUARD.md |
| 2026-06-29 | Multi-distro web stacks (Tier 2) — WordPress/LAMP/LEMP run on Debian/Ubuntu + RHEL via a shared `_DISTRO` layer | Fix within-family failures (mysql-server on Debian, php8.2 on Ubuntu) + extend to RHEL. MariaDB everywhere, unversioned PHP (runtime-detected fpm service/socket), apt\|dnf, ufw\|firewalld, SELinux. `supported_os` now includes almalinux/rocky/centos so Tier 1 allows them. RHEL path needs a live smoke test. See docs/UPDATE-22-MULTI-DISTRO.md |
| 2026-06-29 | Per-server "Installed" tab — records (re-derived access cards) + live read-only scan | Recover post-install info after the run window is closed; show what's actually on the box. Latest successful run per (playbook, URL) with `access_info` resolved, plus an SSH probe (OS/web/db/runtimes/containers/panels/ports). Secret-named install inputs are encrypted at rest (AES-256-GCM via `secret_vars`; migration 017 backfills) and masked in the view — all credentials encrypted at rest. See docs/UPDATE-23-INSTALLED.md |
| 2026-06-29 | **Renamed ServerMind → ServerAlly** + new tagline | "ServerMind" was already taken by ≥2 same-category products (servermind.io control plane; servermind.dev — a near-identical AI VPS assistant) plus a hardware reseller, with every major TLD gone → brand collision + SEO/trademark risk. Rebranded all user-facing strings, docs, env, and the AI gateway/subscription naming; **kept infra identifiers** (DB name/user `servermind`, container names, the `servermind` AI-provider key) to avoid breakage. New tagline: "Your AI companion to manage, automate, and secure any server — without the expertise." Domain targets: `serverallyhq.com` / `serverally.ai` (bare `serverally.com` is taken). |
| 2026-07-02 | AI persona named **Ally**; **Free + Pro** plans locked; AI packaging = **one subscription, AI included (quota) + optional BYO-key escape valve** (never a second bill) | Ally = the ServerAlly brand as a companion. Resolves the "pay twice for AI?" question: software and AI-fuel are one purchase; hosted AI is bundled with a monthly "actions" quota, own-key is an optional toggle. Free = feel the magic on 1–2 servers + ~30 AI actions/mo (no automation/fleet/team); Pro = unlimited servers + full Ally (fleet/batch/memory/proactive) + automation (scheduler/backups/alerts) + team. BYO-key UI demoted from Settings for cloud (`SHOW_AI_PROVIDER_SETTINGS=false`; self-hosted keeps it). **No billing/entitlement code yet** — full spec in [docs/PRICING-FREE-VS-PRO.md](docs/PRICING-FREE-VS-PRO.md). |
| 2026-07-02 | **"Ally Brain" prompt roadmap** — shipped Phase 1 (shared `_PERSONA` across chat/fleet/explain/script prompts) + Phase 2 (conversation memory: client sends last 8 chat turns → `_history_block` in the system prompt) | Prompts had no persona ("ServerAlly AI") and chat was stateless — follow-ups like "now add SSL to it" lost all context. Client-sent history works with saved threads and the multi-provider single-turn `llm_service.complete`; sanitized in the ws layer + double-capped in ai_service (8 turns × 1500 chars). Server-derived text always enters prompts as data-not-instructions (same pattern as `page_context`). Remaining phases: 3 = server profile context (installed/metrics/security/recent commands — data already in DB), 4 = fleet health numbers in fleet chat, 5 = prompt golden tests. |
| 2026-07-03 | **Ally Brain Phase 3** — per-server chat now carries a live server profile (`ai_context_service.build_server_profile` → `_server_profile_block` in the system prompt) | "Why is my server slow?" now gets answered with the server's real numbers instead of guesses. Profile = latest metrics + last security grade + playbook-installed titles + recent AI requests, each line with its age — all from tables we already fill (read-only DB, never SSH at chat time). No secrets by construction: titles/numbers/user's own requests only — no outputs, no access cards, no credentials. Best-effort (failure never blocks chat), data-not-instructions framing, 2000-char cap. |
| 2026-07-03 | **Ally Brain Phase 4** — fleet chat's server list now carries per-server health lines (`ai_context_service.build_fleet_health` → `fleet_chat(health=…)`) | "Which server needs attention?" is now answered with actual numbers ("TestServer1 — CPU 83%") instead of guesses. One line per server: latest CPU/RAM/disk + last security grade, each with its age. Exactly 2 DISTINCT-ON queries for the whole fleet (no N+1, never SSH), capped at 30 servers with health lines, best-effort (failure never blocks chat). Remaining: 5 = prompt golden tests. |
| 2026-07-03 | **AI metering design locked** — flat plan → "action" allowance → our own ledger (`ai_usage`) + monthly counter at the two choke points (`llm_service` cloud / `gateway` self-hosted); see [docs/AI-METERING.md](docs/AI-METERING.md) | Anthropic offers no per-customer allocation, so metering is ours by construction. Actions charged per user request (batch = N, utility parses free, our errors free, BYO-key unmetered); ledger stores counts only, never content. Rails: plan cap + rate limit + provider spend cap + model routing + prompt caching. Build order: 1 ledger+counter (collects real cost data), 2 entitlement wall, 3 billing webhook. |
| 2026-07-03 | **Ally Brain Phase 5 — Ally's long-term memory** (`ally_memories`, migration 020): Ally saves short notes while working (server facts / user preferences / lessons) via an optional `"remember"` field in its chat JSON; injected next turn as a capped WHAT-ALLY-REMEMBERS block | Chat forgot everything learned in conversation ("this server runs the client's shop") the moment it closed — memory is also a promised Pro feature. Trust rules: secret-filter (`_looks_secret` regexes) drops anything credential-like before saving; fully user-visible + deletable (Settings "What Ally remembers" + per-server "Ally remembers" widget, `/api/memories` endpoints); injected as data-not-instructions; capped 30/server + 20/user with dedupe + oldest-eviction; best-effort (never breaks chat). Preferences are about the person → always user-scoped; facts/lessons stick to the server. |
| 2026-07-03 | **Ally Skills Phase A** — packaged expert procedures (`backend/app/skills/*.md`, 9 seeded: wordpress-rescue, server-slow-triage, disk-cleanup, mysql-performance, ssl-troubles, nginx-errors, docker-troubles, security-incident, email-deliverability) matched deterministically per chat message and injected into planning | Generic "expert sysadmin" prompts improvise on specific high-stakes jobs; a skill hands Ally the specialist's procedure (diagnostic order, read-only-first commands, pitfalls, verify, rollback). `skill_service`: frontmatter-parsed repo files (trusted authored content — the ONE block Ally is meant to follow, with an "ignore if it doesn't fit" escape valve), zero-cost trigger matching (one skill max per message, priority tie-break, OS-gated), safety layer still validates every command. Ledger rows tag the skill used (`ai_usage.skill`, migration 021) so we learn which skills earn their tokens. Phase B later: skill menu + Ally-requested skills. |
| 2026-07-03 | **Ally Missions Phase 1** — the agentic ops loop (approve once → plan a step → run → observe → repeat, ≤20 steps) + first mission runbook **github-deploy**; see [docs/ALLY-MISSIONS.md](docs/ALLY-MISSIONS.md) | "Host this GitHub repo" can't be planned up front (the repo's contents decide later steps) — chat now OFFERS a mission (`"mission"` in the plan contract, nudged when a `mode: mission` skill matches), and `_run_mission` works it step-by-step over the chat WS with per-step safety validation, mid-mission approvals for risky steps, a Stop button, a 20-step budget, hosting-API guard (needs SSH), 1 action + fully-ledgered token cost (`feature="mission"`), and a memory note on completion. **Deliberately ONE agent, no sub-agent swarm** — server ops is sequential; a swarm multiplies metered cost and failure modes without adding speed (parallel case = existing batch runner). Verified: 21-check offline battery + real-backend round trip in the browser (found & fixed a React ref-timing bug that swallowed mission endings). |
| 2026-07-03 | **Ally Skills Phase B** — smart skill routing (model-as-router) + the generalist protocol | Keyword triggers have high precision but poor recall: paraphrases ("blank page" ≠ "white screen") and ALL non-English input missed — fatal for an 8-language product. Now: keyword hit → inject as before (free); miss → a one-line skill MENU (~100 tokens, OS-filtered, `skill_service.menu_for`) rides the normal planning call and the model may reply `use_skill: <slug>` → ONE re-plan with the full skill injected (validated slug + OS gate; honored only when the menu was actually offered; ledger attributes via the meta holder). Verified with a Bengali "white page" message routing to wordpress-rescue. Plus an always-on generalist protocol in the base prompt (unfamiliar request → clarify once → read-only facts → hypothesis → smallest reversible change → verify → honest no). Embeddings/pgvector deliberately deferred — the model-as-router needs no new provider/infra and fits the one-subscription model. Next in track: the flywheel (no-skill ledger analytics + mission-transcript → draft skill → human review). |
| 2026-07-03 | **Ally Context C2 — "Ask Ally about this file"**: File Manager publishes the open text file as page context so Ally can explain/review it | Reuses the existing page-context pipeline (like My Scripts) — but file content is **secret-redacted in the browser** (`lib/redactSecrets.ts`) before it can reach the prompt: a wp-config `define`, env `KEY=val`, YAML/JSON, `scheme://user:pass@`, PEM private-key blocks, and standalone tokens (sk-/pk-/ghp_/AKIA/xox/JWT) are masked to `[secret hidden]` while keys/structure stay readable. The editor still shows real values (user edits them); an "Ask Ally" button + a "N hidden" shield chip appear on the toolbar; content capped 8000 chars. Verified: 15-case redaction battery + LIVE end-to-end on TestServer3 (opened a fake `.env`, confirmed the transmitted `page_context` had `leakedCount:0`, 3 masks, structure preserved). Redaction is client-side by design (the browser already holds the real file; the point is not to re-transmit secrets to the AI). |
| 2026-07-03 | **Ally Context C1 — Live Look**: problem reports trigger a fast read-only SSH snapshot (services/disk/memory/load/top/curl/error-log) injected before Ally plans | Stored profile numbers are minutes-to-days old; an expert LOOKS first. `live_look_service`: a FIXED read-only probe bundle (never AI-chosen — like the metrics/installed probes, skips safety_service), one SSH round trip, 12s timeout, 60s per-server cache, SSH-Linux-only, best-effort (never blocks chat). Triggered by a matched diagnostic skill OR problem-word regex. Injected as a data-framed "LIVE SNAPSHOT" leading the volatile tail (fresh → not cached). Verified against live TestServers (real services/disk/load/HTTP-200/error-logs incl. attacker probes); live run caught + fixed a failed-units glyph-vs-name extraction bug. Follow-ups: C2 "Ask Ally about this file", surfacing the snapshot visually, Windows/WinRM probe. |
| 2026-07-03 | **Ally Context C3 — cache-ready prompts + provider prompt caching + savings telemetry** | Provider caching charges ~10% for a repeated identical prompt PREFIX, so prompts are now laid out stable-first (persona/rules/server identity/skill/menu) with all per-message content (live profile with its ages, memories, page context, history, fleet list, mission transcript) in a volatile tail. `llm_service.complete(system, …, system_volatile=…)`: Anthropic gets two system blocks with `cache_control: ephemeral` on the stable one; OpenAI-protocol providers benefit automatically from the ordering. Ledger gains `cache_read/write_tokens` (migration 022) and cache-aware `cost_usd` (reads 0.1×, writes 1.25×, OpenAI reads 0.5×). Missions win most (append-only transcript = near-perfect hits). Expected: input cost down ~50–70% in active chats. Verified: stable prefix byte-identical across turns with changing profile/history, correct block marking, telemetry capture, exact cost math (16 checks). |
| 2026-07-03 | **AI metering Bricks 1+2 SHIPPED; Brick 3 (payments) HALTED** — `ai_usage` ledger (migration 019) + `users.plan`, `metering_service` (contextvar collector, gate, price table), `entitlements.py`, usage hooks in `llm_service`, gates+ledger on chat/fleet/batch/script-gen/schedule-parse, `GET /api/usage/me`, Settings "Ally usage" card, chat `quota_exceeded` bubble, gateway `usage_records` + real usage passthrough | The meter runs from day one (every call recorded with exact provider token counts + cost estimate) while the wall stays dormant: `ENFORCE_AI_QUOTA=false` by default (cloud flips it on). Metering never punishes the customer — gate/record failures log and continue; our errors ledger at 0 actions. **No payment-provider code** (PM: provider undecided) — `users.plan` is manual until then. Verified: 15-check metering battery vs the real dev DB + full backend suite (78 pass) + gateway tests + live Settings card. |

---

## 🚀 How to Run Locally

> On this machine, local dev runs on **backend :8888 / frontend :5190** (8000/8080/5173 are used by other local projects) — see **OPS.md** for the exact start/stop commands. The generic commands below use the documented defaults.

```bash
# First time
cd servermind
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY minimum

# Start infrastructure
docker compose up -d

# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload --port 8000

# Frontend (new terminal tab)
cd frontend
npm install
npm run dev
# → http://localhost:5173

# Useful
alembic revision --autogenerate -m "description"
alembic upgrade head
open http://localhost:8000/docs
```

---

## 📌 CURRENT STATUS → ALL PHASES COMPLETE 🎉

Every build phase (0–13, incl. 2B) is done. ServerAlly is feature-complete:
auth, Linux SSH + Windows WinRM + hosting-panel management, AI chat/terminal,
playbooks, AI script generator, scheduler, file manager, monitoring & alerts,
security audit, backups, team management with role enforcement, and a production
deployment story (see DEPLOY.md).

**What's left is operational, not build work:**
- Run `DEPLOY.md` against a real VPS + managed Postgres/Redis.
- Validate the WinRM handshake against a live Windows Server, and the hosting
  adapters against a live CyberPanel/cPanel/Plesk (endpoints follow documented
  APIs but were only mock-tested).
- Consider the **Future Features Backlog** above for what to build next.

**Post-launch additions (2026-06-23):**
- **Dashboard, Activity Log, Settings** pages built (replaced placeholders); new `GET /api/activity` (AI commands + playbook-run feed) and an `access_info` column on `playbooks` (migration 010).
- **Playbook execution hardened** — live stderr streaming + non-zero-exit detection; the run modal shows live output, an ETA bar, and a post-run access card (URL/login).
- **Docker-based playbooks** self-install Docker via an `ensure_docker` preamble (idempotent).
- **Control-panel playbooks** added (free: CyberPanel/HestiaCP/aaPanel/CloudPanel; premium: cPanel/Plesk/DirectAdmin) behind a pre-flight guard — see the Script Library. **Need live validation on a fresh VPS** (official installers; CyberPanel's is piped-answer/version-sensitive).
- **Local dev** moved to backend :8888 / frontend :5190, Vite proxy on 127.0.0.1 (see OPS.md).

When starting new work, read this entire file first and keep the phase
checklists + Decisions Log up to date. Never deviate from the tech stack without
updating this file first.
