"""Metrics service — collect CPU/RAM/disk/uptime from remote servers via SSH."""
from __future__ import annotations

import json
import logging

from app.models.server import Server
from app.schemas.monitoring import ServerMetricOut
from app.services import connection_manager

logger = logging.getLogger(__name__)

# Single-shot Python script that outputs JSON metrics without requiring any packages.
# Falls back gracefully when /proc is unavailable.
# Pure-shell metrics — works on any Linux, including images without python3 (e.g.
# AlmaLinux/Rocky 8). CPU from /proc/stat, RAM from /proc/meminfo, disk from df,
# load from /proc/loadavg, uptime from /proc/uptime.
_METRICS_SCRIPT = r"""read _ u n s i io q sq st r < /proc/stat 2>/dev/null
u=${u:-0}; n=${n:-0}; s=${s:-0}; i=${i:-0}; io=${io:-0}; q=${q:-0}; sq=${sq:-0}; st=${st:-0}
TOT=$((u+n+s+i+io+q+sq+st))
CPU=$(awk "BEGIN{if($TOT>0)printf \"%.1f\",(1-($i+$io)/$TOT)*100;else print 0}")
MT=$(awk '/^MemTotal:/{print $2}' /proc/meminfo 2>/dev/null)
MA=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo 2>/dev/null)
DF=$(df -kP / 2>/dev/null | awk 'NR==2{print $2" "$4}')
DT=$(echo "$DF" | awk '{print $1}'); DA=$(echo "$DF" | awk '{print $2}')
read L1 L5 L15 r2 < /proc/loadavg 2>/dev/null
UP=$(awk '{print int($1)}' /proc/uptime 2>/dev/null)
printf '{"cpu":%s,"ram_total_kb":%s,"ram_avail_kb":%s,"disk_total_bytes":%s,"disk_free_bytes":%s,"load1":%s,"load5":%s,"load15":%s,"uptime":%s}\n' "${CPU:-0}" "${MT:-0}" "${MA:-0}" "$(( ${DT:-0} * 1024 ))" "$(( ${DA:-0} * 1024 ))" "${L1:-0}" "${L5:-0}" "${L15:-0}" "${UP:-0}"
"""

# Pure-shell OS detection — works on any Linux, including minimal images without
# python3 (e.g. AlmaLinux/Rocky 8, Alpine). Sources /etc/os-release for the distro
# and uses uname -m for the architecture.
_DETECT_SCRIPT = r"""ARCH=$(uname -m 2>/dev/null || echo unknown)
ID=linux; VERSION_ID=; PRETTY_NAME=Linux
[ -r /etc/os-release ] && . /etc/os-release
PN=$(printf '%s' "${PRETTY_NAME:-Linux}" | tr -d '"')
PANEL=
[ -x /usr/bin/cyberpanel ] || [ -d /usr/local/CyberCP ] && PANEL=cyberpanel
[ -d /usr/local/cpanel ] && PANEL=cpanel
[ -d /usr/local/psa ] || [ -x /usr/sbin/plesk ] && PANEL=plesk
printf '{"os_type":"%s","os_version":"%s","arch":"%s","pretty_name":"%s","panel":"%s"}\n' "${ID:-linux}" "${VERSION_ID:-}" "$ARCH" "$PN" "$PANEL"
"""

# ── Windows (PowerShell) variants — emit the same JSON keys as the Linux scripts ──

_WIN_METRICS_SCRIPT = r"""
$os = Get-CimInstance Win32_OperatingSystem
$cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
$uptime = [int]((Get-Date) - $os.LastBootUpTime).TotalSeconds
[pscustomobject]@{
  cpu = $cpu
  ram_total_kb = [int64]$os.TotalVisibleMemorySize
  ram_avail_kb = [int64]$os.FreePhysicalMemory
  disk_total_bytes = [int64]$disk.Size
  disk_free_bytes = [int64]$disk.FreeSpace
  load1 = $null
  load5 = $null
  load15 = $null
  uptime = $uptime
} | ConvertTo-Json -Compress
"""

_WIN_DETECT_SCRIPT = r"""
$os = Get-CimInstance Win32_OperatingSystem
[pscustomobject]@{
  os_type = 'windows'
  os_version = $os.Version
  arch = $env:PROCESSOR_ARCHITECTURE
  pretty_name = $os.Caption
} | ConvertTo-Json -Compress
"""


def _is_windows(server: Server) -> bool:
    return (
        server.connection_type == "winrm"
        or (server.os_type or "").lower() == "windows"
        or (server.shell or "").lower() == "powershell"
    )


async def get_metrics(server: Server) -> dict:
    """Return current CPU/RAM/disk/load metrics for the server."""
    script = _WIN_METRICS_SCRIPT if _is_windows(server) else _METRICS_SCRIPT
    stdout, _, _ = await connection_manager.execute(server, script)
    raw = stdout.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Metrics parse failed for server %s: %r", server.id, raw)
        return {}

    ram_total_kb = data.get("ram_total_kb") or 0
    ram_avail_kb = data.get("ram_avail_kb") or 0
    ram_used_kb = ram_total_kb - ram_avail_kb

    disk_total_b = data.get("disk_total_bytes") or 0
    disk_free_b = data.get("disk_free_bytes") or 0
    disk_used_b = disk_total_b - disk_free_b

    ram_percent = round(ram_used_kb / ram_total_kb * 100, 1) if ram_total_kb else None
    disk_percent = round(disk_used_b / disk_total_b * 100, 1) if disk_total_b else None

    return {
        "cpu_percent": data.get("cpu"),
        "ram_percent": ram_percent,
        "ram_used_mb": ram_used_kb // 1024 if ram_total_kb else None,
        "ram_total_mb": ram_total_kb // 1024 if ram_total_kb else None,
        "disk_percent": disk_percent,
        "disk_used_gb": round(disk_used_b / 1024 ** 3, 2) if disk_total_b else None,
        "disk_total_gb": round(disk_total_b / 1024 ** 3, 2) if disk_total_b else None,
        "load_1": data.get("load1"),
        "load_5": data.get("load5"),
        "load_15": data.get("load15"),
        "uptime_seconds": data.get("uptime"),
    }


async def detect_os(server: Server) -> dict:
    """Auto-detect OS type, version, and architecture."""
    script = _WIN_DETECT_SCRIPT if _is_windows(server) else _DETECT_SCRIPT
    stdout, _, _ = await connection_manager.execute(server, script)
    raw = stdout.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("OS detect parse failed for server %s: %r", server.id, raw)
        fallback = "windows" if _is_windows(server) else "linux"
        return {"os_type": fallback, "os_version": "", "arch": "unknown"}

    return {
        "os_type": data.get("os_type", "linux"),
        "os_version": data.get("os_version", ""),
        "arch": data.get("arch", "unknown"),
        "pretty_name": data.get("pretty_name", "Linux"),
        # Control panel installed on the box (cyberpanel/cpanel/plesk) — lets an SSH
        # server expose Hosting via the panel's CLI (H1). Empty string = none.
        "panel": data.get("panel", "") or None,
    }
