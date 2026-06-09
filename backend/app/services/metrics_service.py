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
_METRICS_SCRIPT = r"""python3 -c "
import json, os, time
try:
    s=open('/proc/stat').readline().split()[1:]
    t,i=sum(int(x) for x in s),int(s[3])
    cpu=round((1-i/t)*100,1)
except:
    cpu=None
try:
    m={l.split(':')[0].strip():int(l.split(':')[1].split()[0]) for l in open('/proc/meminfo') if l.split(':')[0].strip() in ('MemTotal','MemAvailable')}
    ram_total_kb,ram_avail_kb=m['MemTotal'],m['MemAvailable']
except:
    ram_total_kb=ram_avail_kb=None
try:
    st=os.statvfs('/')
    disk_total=st.f_blocks*st.f_frsize
    disk_free=st.f_bavail*st.f_frsize
except:
    disk_total=disk_free=None
try:
    la=open('/proc/loadavg').read().split()
    load1,load5,load15=float(la[0]),float(la[1]),float(la[2])
except:
    load1=load5=load15=None
try:
    uptime=int(float(open('/proc/uptime').read().split()[0]))
except:
    uptime=None
print(json.dumps({'cpu':cpu,'ram_total_kb':ram_total_kb,'ram_avail_kb':ram_avail_kb,'disk_total_bytes':disk_total,'disk_free_bytes':disk_free,'load1':load1,'load5':load5,'load15':load15,'uptime':uptime}))
" 2>/dev/null || echo '{"error":"python3 unavailable"}'
"""

_DETECT_SCRIPT = r"""python3 -c "
import json, platform, subprocess
info={}
try:
    with open('/etc/os-release') as f:
        for line in f:
            k,_,v=line.strip().partition('=')
            info[k]=v.strip('\"')
except:
    pass
print(json.dumps({'os_type':info.get('ID','linux'),'os_version':info.get('VERSION_ID',''),'arch':platform.machine(),'pretty_name':info.get('PRETTY_NAME','Linux')}))
" 2>/dev/null || echo '{"os_type":"linux","os_version":"","arch":"unknown","pretty_name":"Linux"}'
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
    }
