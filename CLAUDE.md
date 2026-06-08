# ServerMind — Claude Code Master Instructions
> **VERSION 3.0** — Updated with official name/tagline, Windows Server support, WinRM layer, hosting environment mode, multilingual AI, and full feature roadmap.
> Read this file FULLY before doing anything. Update checklists as you complete tasks.

---

## 🧠 Product Identity

**Product Name:** ServerMind
**Tagline:** Manage any server in natural language
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

ServerMind AI responds in the user's preferred language.
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
You are ServerMind AI, an expert server administrator.
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
You are ServerMind Script Generator.
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
- Clear header comment (title, description, author: ServerMind AI, date)
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

When `connection_type = "hosting"`, ServerMind connects via panel API instead of raw SSH.

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
APP_NAME=ServerMind
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
EMAIL_FROM=noreply@servermind.ai

# Cloudflare R2
R2_ACCOUNT_ID=
R2_ACCESS_KEY=
R2_SECRET_KEY=
R2_BUCKET=servermind-logs

# Frontend
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
VITE_APP_NAME=ServerMind
VITE_APP_TAGLINE=Manage any server in natural language
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

### ⬜ Phase 2 — Linux Server Management (SSH)
- [ ] servers table + migration
- [ ] ssh_service.py (Paramiko: connect, test, execute, stream)
- [ ] connection_manager.py (routes by connection_type)
- [ ] metrics_service.py (CPU/RAM/disk via SSH)
- [ ] OS detection on server add
- [ ] /servers CRUD + test + detect + metrics endpoints
- [ ] Frontend: Add Server modal
- [ ] Frontend: Server list + Server detail with metrics

### ⬜ Phase 2B — Windows Server Management (WinRM)
- [ ] winrm_service.py (pywinrm: connect, test, execute, stream)
- [ ] Windows metrics collection (PowerShell commands)
- [ ] Windows OS detection
- [ ] Windows safety blocklist in safety_service.py
- [ ] Test: connect Windows Server → run PowerShell command → stream output

### ⬜ Phase 3 — AI Chat + Terminal
- [ ] command_logs table + migration
- [ ] ai_service.py (plan_commands with OS + language awareness)
- [ ] safety_service.py (Linux + Windows blocklists)
- [ ] WebSocket terminal handler
- [ ] /chat endpoints
- [ ] Frontend: XTerminal.tsx (xterm.js)
- [ ] Frontend: ChatWindow.tsx with multilingual support
- [ ] Frontend: CommandPlan.tsx (show plan before executing)
- [ ] Frontend: useWebSocket.ts hook
- [ ] Test: Linux + Windows commands in multiple languages

### ⬜ Phase 4 — Playbooks (Script Library)
- [ ] playbooks + playbook_runs tables + migration
- [ ] Dual script support (bash + powershell per playbook)
- [ ] Seed all official Linux playbooks
- [ ] Seed all official Windows playbooks
- [ ] /playbooks endpoints
- [ ] Frontend: Playbooks page (OS filter + category tabs + search)
- [ ] Frontend: PlaybookCard, ScriptPreview, RunPlaybookModal

### ⬜ Phase 5 — AI Script Generator
- [ ] user_scripts table + migration
- [ ] ai_service.generate_script() (bash or PowerShell based on server OS)
- [ ] /scripts endpoints
- [ ] Frontend: ScriptGenerator.tsx
- [ ] Frontend: MyScripts.tsx

### ⬜ Phase 6 — Scheduler
- [ ] scheduled_tasks table + migration
- [ ] scheduler_service.py (APScheduler)
- [ ] Natural language → cron (AI-assisted)
- [ ] /schedules endpoints
- [ ] Frontend: Scheduler.tsx

### ⬜ Phase 7 — Hosting Mode
- [ ] hosting_service.py (CyberPanel API)
- [ ] hosting_service.py (cPanel UAPI)
- [ ] hosting_service.py (Plesk REST API)
- [ ] Hosting-specific AI prompt adjustments
- [ ] /servers with connection_type='hosting'
- [ ] Frontend: Add Hosting Account modal (panel type selector)
- [ ] Frontend: Hosting-specific dashboard (sites, DBs, email)
- [ ] Test: Connect CyberPanel → create site → issue SSL

### ⬜ Phase 8 — File Manager
- [ ] file_service.py (SFTP for Linux, SMB/WinRM for Windows, API for hosting)
- [ ] /files endpoints
- [ ] Frontend: FileManager.tsx + Monaco Editor

### ⬜ Phase 9 — Monitoring & Alerts
- [ ] server_metrics + alerts tables + migration
- [ ] metrics_worker.py (collect every 5 min)
- [ ] alert_worker.py + notification_service.py
- [ ] /alerts + /metrics/history endpoints
- [ ] Frontend: Monitoring.tsx

### ⬜ Phase 10 — Security Audit
- [ ] security_service.py (Linux checks + Windows checks)
- [ ] /security/scan endpoint
- [ ] Frontend: Security.tsx

### ⬜ Phase 11 — Backups
- [ ] backup_service.py
- [ ] /backups endpoints
- [ ] Frontend: Backups.tsx

### ⬜ Phase 12 — Team Management
- [ ] team_members + server_access tables + migration
- [ ] Role enforcement on all command endpoints
- [ ] Invite flow
- [ ] Frontend: Team.tsx

### ⬜ Phase 13 — Production Deploy
- [ ] docker-compose.prod.yml
- [ ] Frontend build → static files
- [ ] CyberPanel subdomain + reverse proxy
- [ ] CyberPanel Let's Encrypt SSL
- [ ] Sentry integration
- [ ] Production environment variables
- [ ] Smoke test all platforms (Linux SSH, Windows WinRM, CyberPanel hosting)

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
- [ ] Cloudflare API: manage DNS from ServerMind
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
- [ ] API access for users (build on top of ServerMind)
- [ ] White-label for agencies

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
| Day 1 | Product name: ServerMind | Clear, memorable, AI-native |
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

---

## 🚀 How to Run Locally

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

## 📌 CURRENT TASK → START HERE

**Phase 0: Project Scaffold**

Read this entire file first.
Then build the complete folder structure, docker-compose.yml,
FastAPI skeleton with /health, and React + Vite + Tailwind + i18n scaffold.

Check off each Phase 0 item as completed.
Update the Decisions Log for any tech choices that change.
Never deviate from the tech stack without updating this file first.
