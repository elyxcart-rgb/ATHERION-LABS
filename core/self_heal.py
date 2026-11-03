"""SONIC AI — Self-Heal Diagnostics.

Like Iron Man's self-repair suite: SONIC runs its own health checks and
auto-fixes common issues without bothering the user.

Public API:
    SelfHeal()
    .diagnose() -> list[Diagnostic]
    .repair(diagnostic) -> RepairResult
    .full_health_check() -> HealthReport

Categories:
    - memory:    RAM usage, swap, available memory
    - disk:      free space, temp cleanup candidates
    - network:   internet connectivity, DNS, gateway reachability
    - audio:     default output device, mic availability
    - process:   rogue processes, hung apps
    - sonicself: missing dependencies, broken imports
"""
from __future__ import annotations

import shutil
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional, Callable, Any


# ═════════════════════════════════════════════════════════════════════════════
# Diagnostic record
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class Diagnostic:
    """One health-check finding."""
    code: str                          # unique id, e.g. "DISK_LOW"
    category: str                      # memory|disk|network|audio|process|sonicself
    severity: str                      # ok|info|warning|critical
    title: str                         # short headline
    detail: str                        # what was found
    metric: Optional[float] = None     # numeric measurement (if any)
    threshold: Optional[float] = None  # threshold that was breached (if any)
    auto_repairable: bool = False
    repair_hint: str = ""              # human-readable description of fix
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RepairResult:
    """Outcome of an attempted repair."""
    diagnostic_code: str
    success: bool
    action_taken: str
    detail: str = ""
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HealthReport:
    """Full health snapshot."""
    timestamp: float
    overall: str                       # ok|warning|critical
    diagnostics: list[Diagnostic] = field(default_factory=list)
    auto_repairs: list[RepairResult] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "overall": self.overall,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "auto_repairs": [r.to_dict() for r in self.auto_repairs],
            "duration_ms": self.duration_ms,
        }

    def summary(self) -> str:
        crit = sum(1 for d in self.diagnostics if d.severity == "critical")
        warn = sum(1 for d in self.diagnostics if d.severity == "warning")
        ok = sum(1 for d in self.diagnostics if d.severity == "ok")
        parts = [f"{crit} critical", f"{warn} warning", f"{ok} ok"]
        return " | ".join(parts)


# ═════════════════════════════════════════════════════════════════════════════
# SelfHeal
# ═════════════════════════════════════════════════════════════════════════════

class SelfHeal:
    """Auto-diagnostics + auto-repair for SONIC AI itself."""

    def __init__(self, log_fn: Optional[Callable[[str], None]] = None):
        self._log = log_fn or (lambda msg: None)
        self._lock = threading.Lock()
        self._last_report: Optional[HealthReport] = None

    # ── Public ───────────────────────────────────────────────────────────────

    def full_health_check(self, auto_repair: bool = True) -> HealthReport:
        """Run all diagnostic checks. If auto_repair, fix what we can."""
        t0 = time.time()
        with self._lock:
            diagnostics: list[Diagnostic] = []
            repairs: list[RepairResult] = []

            for fn in (
                self._check_memory,
                self._check_disk,
                self._check_network,
                self._check_audio,
                self._check_sonicself,
                self._check_temp_files,
            ):
                try:
                    findings = fn()
                    diagnostics.extend(findings)
                except Exception as e:
                    self._log(f"diag {fn.__name__} failed: {e}")

            # Auto-repair the repairable ones
            if auto_repair:
                for d in diagnostics:
                    if d.auto_repairable and d.severity in ("warning", "critical"):
                        try:
                            result = self.repair(d)
                            repairs.append(result)
                        except Exception as e:
                            self._log(f"repair {d.code} failed: {e}")

            # Compute overall
            overall = "ok"
            if any(d.severity == "critical" for d in diagnostics):
                overall = "critical"
            elif any(d.severity == "warning" for d in diagnostics):
                overall = "warning"

            report = HealthReport(
                timestamp=time.time(),
                overall=overall,
                diagnostics=diagnostics,
                auto_repairs=repairs,
                duration_ms=(time.time() - t0) * 1000,
            )
            self._last_report = report
            return report

    def repair(self, d: Diagnostic) -> RepairResult:
        """Attempt to repair a specific diagnostic."""
        ts = time.time()
        if d.code == "TEMP_JUNK_HIGH":
            return self._repair_temp_cleanup(d, ts)
        if d.code == "DNS_RESOLUTION_FAILED":
            return self._repair_flush_dns(d, ts)
        if d.code == "AUDIO_NO_OUTPUT":
            return self._repair_audio_reconnect(d, ts)
        if d.code == "DISK_LOW":
            return self._repair_temp_cleanup(d, ts)
        return RepairResult(
            diagnostic_code=d.code, success=False,
            action_taken="none", detail="no auto-repair available",
            timestamp=ts,
        )

    def get_last_report(self) -> Optional[HealthReport]:
        with self._lock:
            return self._last_report

    # ── Diagnostic checks ────────────────────────────────────────────────────

    def _check_memory(self) -> list[Diagnostic]:
        out = []
        try:
            import psutil
            vm = psutil.virtual_memory()
            pct = vm.percent
            sev = "ok"
            if pct > 90: sev = "critical"
            elif pct > 75: sev = "warning"
            out.append(Diagnostic(
                code="MEM_USAGE_HIGH",
                category="memory",
                severity=sev,
                title=f"RAM usage {pct:.0f}%",
                detail=f"{vm.used // (1024**2)} MB used of {vm.total // (1024**2)} MB "
                       f"({vm.available // (1024**2)} MB available)",
                metric=pct, threshold=85.0,
                timestamp=time.time(),
            ))
        except Exception as e:
            out.append(Diagnostic(
                code="MEM_CHECK_FAILED", category="memory", severity="warning",
                title="Could not read memory stats",
                detail=str(e), timestamp=time.time(),
            ))
        return out

    def _check_disk(self) -> list[Diagnostic]:
        out = []
        try:
            usage = shutil.disk_usage(Path.home().anchor or "C:\\")
            free_gb = usage.free / (1024**3)
            pct = (usage.used / usage.total) * 100
            sev = "ok"
            auto = False
            if free_gb < 2:
                sev = "critical"; auto = True
            elif free_gb < 10:
                sev = "warning"; auto = True
            out.append(Diagnostic(
                code="DISK_LOW",
                category="disk",
                severity=sev,
                title=f"Disk {pct:.0f}% full",
                detail=f"{free_gb:.1f} GB free of {usage.total / (1024**3):.0f} GB",
                metric=pct, threshold=90.0,
                auto_repairable=auto,
                repair_hint="Run temp cleanup to reclaim disk space",
                timestamp=time.time(),
            ))
        except Exception as e:
            out.append(Diagnostic(
                code="DISK_CHECK_FAILED", category="disk", severity="warning",
                title="Could not read disk stats",
                detail=str(e), timestamp=time.time(),
            ))
        return out

    def _check_network(self) -> list[Diagnostic]:
        out = []
        # 1. Internet connectivity
        try:
            socket.setdefaulttimeout(3)
            socket.create_connection(("1.1.1.1", 53), timeout=3).close()
            out.append(Diagnostic(
                code="NET_INTERNET_OK", category="network", severity="ok",
                title="Internet reachable", detail="1.1.1.1:53 connected",
                timestamp=time.time(),
            ))
        except Exception as e:
            out.append(Diagnostic(
                code="NET_INTERNET_DOWN", category="network", severity="critical",
                title="No internet connectivity",
                detail=str(e), timestamp=time.time(),
            ))

        # 2. DNS
        try:
            ip = socket.gethostbyname("www.google.com")
            out.append(Diagnostic(
                code="DNS_OK", category="network", severity="ok",
                title="DNS resolving", detail=f"www.google.com → {ip}",
                timestamp=time.time(),
            ))
        except Exception as e:
            out.append(Diagnostic(
                code="DNS_RESOLUTION_FAILED", category="network",
                severity="warning", title="DNS resolution failed",
                detail=str(e),
                auto_repairable=True,
                repair_hint="Flush DNS cache (ipconfig /flushdns)",
                timestamp=time.time(),
            ))
        return out

    def _check_audio(self) -> list[Diagnostic]:
        out = []
        try:
            # Try Windows audio API
            from .audio_devices import list_audio_devices  # type: ignore
            devices = list_audio_devices()
            if not devices:
                raise RuntimeError("no audio devices found")
            out.append(Diagnostic(
                code="AUDIO_OK", category="audio", severity="ok",
                title="Audio devices detected",
                detail=f"{len(devices)} devices",
                metric=float(len(devices)),
                timestamp=time.time(),
            ))
        except Exception as e:
            out.append(Diagnostic(
                code="AUDIO_NO_OUTPUT", category="audio",
                severity="warning", title="Audio device detection failed",
                detail=str(e),
                auto_repairable=True,
                repair_hint="Reconnect audio device or restart audio service",
                timestamp=time.time(),
            ))
        return out

    def _check_sonicself(self) -> list[Diagnostic]:
        """Check that SONIC's own dependencies are healthy."""
        out = []
        critical_deps = ["PyQt6", "psutil", "PIL"]
        for dep in critical_deps:
            try:
                __import__(dep)
            except ImportError:
                out.append(Diagnostic(
                    code=f"MISSING_DEP_{dep.upper()}",
                    category="sonicself",
                    severity="critical",
                    title=f"Missing dependency: {dep}",
                    detail=f"import {dep} failed",
                    auto_repairable=False,
                    repair_hint=f"pip install {dep}",
                    timestamp=time.time(),
                ))
        if not any(d.code.startswith("MISSING_DEP_") for d in out):
            out.append(Diagnostic(
                code="SONIC_DEPS_OK", category="sonicself", severity="ok",
                title="Core dependencies present",
                detail="PyQt6, psutil, PIL all importable",
                timestamp=time.time(),
            ))
        return out

    def _check_temp_files(self) -> list[Diagnostic]:
        out = []
        try:
            temp = Path(os.environ.get("TEMP") or os.environ.get("TMP") or "C:/Windows/Temp")
            if temp.exists():
                total = 0
                count = 0
                for f in temp.iterdir():
                    try:
                        if f.is_file():
                            total += f.stat().st_size
                            count += 1
                    except Exception:
                        continue
                mb = total / (1024**2)
                sev = "ok"
                auto = False
                if mb > 5000: sev = "critical"; auto = True
                elif mb > 1000: sev = "warning"; auto = True
                out.append(Diagnostic(
                    code="TEMP_JUNK_HIGH",
                    category="disk",
                    severity=sev,
                    title=f"Temp folder {mb:.0f} MB",
                    detail=f"{count} files in {temp}",
                    metric=mb, threshold=1000.0,
                    auto_repairable=auto,
                    repair_hint="Clean temp folder",
                    timestamp=time.time(),
                ))
        except Exception:
            pass
        return out

    # ── Repairs ──────────────────────────────────────────────────────────────

    def _repair_temp_cleanup(self, d: Diagnostic, ts: float) -> RepairResult:
        """Delete files in temp folder that are older than 7 days."""
        deleted = 0
        freed_bytes = 0
        try:
            temp = Path(os.environ.get("TEMP") or "C:/Windows/Temp")
            cutoff = time.time() - 7 * 86400
            for f in temp.iterdir():
                try:
                    if f.is_file() and f.stat().st_mtime < cutoff:
                        size = f.stat().st_size
                        f.unlink()
                        deleted += 1
                        freed_bytes += size
                except Exception:
                    continue
            return RepairResult(
                diagnostic_code=d.code, success=True,
                action_taken=f"deleted {deleted} temp files",
                detail=f"freed {freed_bytes // (1024**2)} MB",
                timestamp=ts,
            )
        except Exception as e:
            return RepairResult(
                diagnostic_code=d.code, success=False,
                action_taken="cleanup failed",
                detail=str(e), timestamp=ts,
            )

    def _repair_flush_dns(self, d: Diagnostic, ts: float) -> RepairResult:
        try:
            subprocess.run(
                ["ipconfig", "/flushdns"],
                capture_output=True, text=True, timeout=10,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
            return RepairResult(
                diagnostic_code=d.code, success=True,
                action_taken="flushed DNS cache",
                detail="ipconfig /flushdns executed",
                timestamp=ts,
            )
        except Exception as e:
            return RepairResult(
                diagnostic_code=d.code, success=False,
                action_taken="flush DNS failed", detail=str(e), timestamp=ts,
            )

    def _repair_audio_reconnect(self, d: Diagnostic, ts: float) -> RepairResult:
        try:
            # Try restarting Windows audio service
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Restart-Service Audiosrv -Force"],
                capture_output=True, text=True, timeout=15,
            )
            return RepairResult(
                diagnostic_code=d.code, success=True,
                action_taken="restarted Windows audio service",
                detail="Audiosrv restarted",
                timestamp=ts,
            )
        except Exception as e:
            return RepairResult(
                diagnostic_code=d.code, success=False,
                action_taken="audio restart failed",
                detail=str(e), timestamp=ts,
            )


# Need os for temp path
import os
