"""
System Info - Real-time system information collection.

Provides on-demand system diagnostics (RAM, CPU, Disk, etc.) for the LLM
to answer questions like "Why is my Mac slow?" or "How much RAM do I have?"

Uses psutil for cross-platform system information gathering.
"""

import logging
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logging.warning(
        "psutil not installed. System info will be limited. "
        "Install with: pip install psutil"
    )


logger = logging.getLogger(__name__)


@dataclass
class CPUInfo:
    """CPU information."""
    percent: float
    cores_physical: int
    cores_logical: int
    per_core_percent: List[float]
    frequency_mhz: Optional[float]


@dataclass
class MemoryInfo:
    """RAM information."""
    total_gb: float
    used_gb: float
    available_gb: float
    percent: float
    swap_total_gb: float
    swap_used_gb: float
    swap_percent: float


@dataclass
class DiskInfo:
    """Disk/storage information for a single mount point."""
    mount_point: str
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float


@dataclass
class ProcessInfo:
    """Information about a running process."""
    pid: int
    name: str
    ram_mb: float
    cpu_percent: float


@dataclass
class BatteryInfo:
    """Battery information."""
    percent: float
    charging: bool
    plugged_in: bool
    time_remaining_mins: Optional[int]


@dataclass
class SystemSnapshot:
    """Complete system snapshot at a point in time."""
    timestamp: str
    cpu: Optional[CPUInfo]
    memory: Optional[MemoryInfo]
    disks: List[DiskInfo]
    processes_by_ram: List[ProcessInfo]
    processes_by_cpu: List[ProcessInfo]
    battery: Optional[BatteryInfo]
    uptime_hours: float


def bytes_to_gb(bytes_val: int) -> float:
    """Convert bytes to gigabytes, rounded to 1 decimal."""
    return round(bytes_val / (1024 ** 3), 1)


def bytes_to_mb(bytes_val: int) -> float:
    """Convert bytes to megabytes, rounded to 1 decimal."""
    return round(bytes_val / (1024 ** 2), 1)


def get_cpu_info() -> Optional[CPUInfo]:
    """Get CPU information."""
    if not PSUTIL_AVAILABLE:
        return None
    
    try:
        # Get CPU percent (blocking for 0.5s to measure)
        cpu_percent = psutil.cpu_percent(interval=0.5)
        per_core = psutil.cpu_percent(interval=0.1, percpu=True)
        
        # Get CPU frequency
        freq = psutil.cpu_freq()
        freq_mhz = freq.current if freq else None
        
        return CPUInfo(
            percent=cpu_percent,
            cores_physical=psutil.cpu_count(logical=False) or 0,
            cores_logical=psutil.cpu_count(logical=True) or 0,
            per_core_percent=per_core,
            frequency_mhz=freq_mhz,
        )
    except Exception as e:
        logger.error(f"Failed to get CPU info: {e}")
        return None


def get_memory_info() -> Optional[MemoryInfo]:
    """Get memory (RAM) information."""
    if not PSUTIL_AVAILABLE:
        return None
    
    try:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        return MemoryInfo(
            total_gb=bytes_to_gb(mem.total),
            used_gb=bytes_to_gb(mem.used),
            available_gb=bytes_to_gb(mem.available),
            percent=mem.percent,
            swap_total_gb=bytes_to_gb(swap.total),
            swap_used_gb=bytes_to_gb(swap.used),
            swap_percent=swap.percent,
        )
    except Exception as e:
        logger.error(f"Failed to get memory info: {e}")
        return None


def get_disk_info() -> List[DiskInfo]:
    """Get disk/storage information for all mounted partitions."""
    if not PSUTIL_AVAILABLE:
        return []
    
    disks = []
    try:
        # Get all disk partitions
        partitions = psutil.disk_partitions(all=False)
        
        for part in partitions:
            try:
                usage = psutil.disk_usage(part.mountpoint)
                # Skip very small partitions
                if usage.total < 1024 * 1024 * 100:  # < 100MB
                    continue
                
                disks.append(DiskInfo(
                    mount_point=part.mountpoint,
                    total_gb=bytes_to_gb(usage.total),
                    used_gb=bytes_to_gb(usage.used),
                    free_gb=bytes_to_gb(usage.free),
                    percent=usage.percent,
                ))
            except (PermissionError, OSError):
                continue
    except Exception as e:
        logger.error(f"Failed to get disk info: {e}")
    
    return disks


def get_top_processes(n: int = 5) -> tuple[List[ProcessInfo], List[ProcessInfo]]:
    """Get top N processes by RAM and CPU usage."""
    if not PSUTIL_AVAILABLE:
        return [], []
    
    processes = []
    try:
        # Get all processes with their info
        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent']):
            try:
                info = proc.info
                ram_mb = bytes_to_mb(info['memory_info'].rss) if info['memory_info'] else 0
                cpu_percent = info['cpu_percent'] or 0
                
                # Skip system/kernel processes with no RAM
                if ram_mb < 1:
                    continue
                
                processes.append(ProcessInfo(
                    pid=info['pid'],
                    name=info['name'] or 'Unknown',
                    ram_mb=ram_mb,
                    cpu_percent=cpu_percent,
                ))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception as e:
        logger.error(f"Failed to get process info: {e}")
        return [], []
    
    # Sort by RAM and CPU
    by_ram = sorted(processes, key=lambda p: p.ram_mb, reverse=True)[:n]
    by_cpu = sorted(processes, key=lambda p: p.cpu_percent, reverse=True)[:n]
    
    return by_ram, by_cpu


def get_battery_info() -> Optional[BatteryInfo]:
    """Get battery information (for laptops)."""
    if not PSUTIL_AVAILABLE:
        return None
    
    try:
        battery = psutil.sensors_battery()
        if battery is None:
            return None
        
        time_remaining = None
        if battery.secsleft > 0:
            time_remaining = int(battery.secsleft / 60)
        
        return BatteryInfo(
            percent=battery.percent,
            charging=battery.power_plugged and battery.percent < 100,
            plugged_in=battery.power_plugged or False,
            time_remaining_mins=time_remaining,
        )
    except Exception as e:
        logger.debug(f"Battery info not available: {e}")
        return None


def get_uptime_hours() -> float:
    """Get system uptime in hours."""
    if not PSUTIL_AVAILABLE:
        return 0.0
    
    try:
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        return round(uptime_seconds / 3600, 1)
    except Exception as e:
        logger.error(f"Failed to get uptime: {e}")
        return 0.0


def get_system_info(sections: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Get system information for the specified sections.
    
    Args:
        sections: List of sections to include. Options:
                  ["cpu", "memory", "disk", "processes", "battery", "all"]
                  If None or contains "all", returns everything.
    
    Returns:
        Dictionary with system information, ready to be sent to LLM.
    """
    if not PSUTIL_AVAILABLE:
        return {
            "error": "psutil not installed. Run: pip install psutil",
            "available": False,
        }
    
    # Normalize sections
    if sections is None or "all" in sections:
        sections = ["cpu", "memory", "disk", "processes", "battery"]
    
    result: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "uptime_hours": get_uptime_hours(),
    }
    
    if "cpu" in sections:
        cpu = get_cpu_info()
        if cpu:
            result["cpu"] = asdict(cpu)
    
    if "memory" in sections:
        mem = get_memory_info()
        if mem:
            result["memory"] = asdict(mem)
    
    if "disk" in sections:
        disks = get_disk_info()
        result["disks"] = [asdict(d) for d in disks]
    
    if "processes" in sections:
        by_ram, by_cpu = get_top_processes(5)
        result["processes"] = {
            "top_by_ram": [asdict(p) for p in by_ram],
            "top_by_cpu": [asdict(p) for p in by_cpu],
        }
    
    if "battery" in sections:
        battery = get_battery_info()
        if battery:
            result["battery"] = asdict(battery)
    
    return result


def format_system_info_for_llm(info: Dict[str, Any]) -> str:
    """
    Format system info as a human-readable string for the LLM context.
    
    Args:
        info: System info dictionary from get_system_info()
    
    Returns:
        Formatted string suitable for LLM context.
    """
    lines = [f"\n## System Information (as of {info.get('timestamp', 'now')})\n"]
    
    # Uptime
    uptime = info.get("uptime_hours", 0)
    if uptime:
        lines.append(f"**Uptime:** {uptime} hours\n")
    
    # CPU
    if "cpu" in info:
        cpu = info["cpu"]
        lines.append(f"### CPU")
        lines.append(f"- **Usage:** {cpu['percent']}%")
        lines.append(f"- **Cores:** {cpu['cores_physical']} physical, {cpu['cores_logical']} logical")
        if cpu.get("frequency_mhz"):
            lines.append(f"- **Frequency:** {cpu['frequency_mhz']:.0f} MHz")
        lines.append("")
    
    # Memory
    if "memory" in info:
        mem = info["memory"]
        lines.append(f"### Memory (RAM)")
        lines.append(f"- **Total:** {mem['total_gb']} GB")
        lines.append(f"- **Used:** {mem['used_gb']} GB ({mem['percent']}%)")
        lines.append(f"- **Available:** {mem['available_gb']} GB")
        if mem.get("swap_total_gb", 0) > 0:
            lines.append(f"- **Swap:** {mem['swap_used_gb']} / {mem['swap_total_gb']} GB ({mem['swap_percent']}%)")
        lines.append("")
    
    # Disk
    if "disks" in info and info["disks"]:
        lines.append(f"### Storage")
        for disk in info["disks"]:
            lines.append(f"- **{disk['mount_point']}:** {disk['free_gb']} GB free of {disk['total_gb']} GB ({disk['percent']}% used)")
        lines.append("")
    
    # Processes
    if "processes" in info:
        procs = info["processes"]
        if procs.get("top_by_ram"):
            lines.append(f"### Top Processes (by RAM)")
            for p in procs["top_by_ram"][:5]:
                lines.append(f"- **{p['name']}** (PID {p['pid']}): {p['ram_mb']} MB RAM, {p['cpu_percent']}% CPU")
            lines.append("")
        
        if procs.get("top_by_cpu"):
            # Only show if different from RAM list
            cpu_names = {p['name'] for p in procs.get("top_by_cpu", [])}
            ram_names = {p['name'] for p in procs.get("top_by_ram", [])}
            if cpu_names != ram_names:
                lines.append(f"### Top Processes (by CPU)")
                for p in procs["top_by_cpu"][:5]:
                    lines.append(f"- **{p['name']}** (PID {p['pid']}): {p['cpu_percent']}% CPU, {p['ram_mb']} MB RAM")
                lines.append("")
    
    # Battery
    if "battery" in info:
        bat = info["battery"]
        status = "Charging" if bat["charging"] else ("Plugged in" if bat["plugged_in"] else "On battery")
        time_str = f", {bat['time_remaining_mins']} min remaining" if bat.get("time_remaining_mins") else ""
        lines.append(f"### Battery")
        lines.append(f"- **Level:** {bat['percent']}% ({status}{time_str})")
        lines.append("")
    
    return "\n".join(lines)


# Quick test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    info = get_system_info(["all"])
    print(format_system_info_for_llm(info))
