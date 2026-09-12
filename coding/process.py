from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from .models import CodingTask, TaskState


class ProcessManager:
    def __init__(self) -> None:
        self._processes: dict[str, subprocess.Popen] = {}
        self._opencode_path: str | None = None

    def find_opencode(self) -> str | None:
        if self._opencode_path:
            return self._opencode_path
        exe = "opencode.ps1" if sys.platform == "win32" else "opencode"
        try:
            result = subprocess.run(
                ["where", exe] if sys.platform == "win32" else ["which", exe],
                capture_output=True, text=True, timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0 and result.stdout.strip():
                path = result.stdout.strip().splitlines()[0]
                self._opencode_path = path
                return path
        except Exception:
            pass
        for candidate in [
            r"C:\Users\94\AppData\Roaming\npm\opencode.ps1",
            r"C:\Users\94\AppData\Roaming\npm\opencode.cmd",
            "/usr/local/bin/opencode",
            "/usr/bin/opencode",
        ]:
            if os.path.isfile(candidate):
                self._opencode_path = candidate
                return candidate
        return None

    async def run_opencode(
        self,
        task: CodingTask,
        project_root: str,
        prompt: str,
        timeout: int = 300,
    ) -> tuple[bool, str, str]:
        opencode = self.find_opencode()
        if not opencode:
            return False, "", "Development engine executable not found"

        # Write prompt to temp file — avoids PowerShell escaping issues
        prompt_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.txt', delete=False, encoding='utf-8'
            ) as f:
                f.write(prompt)
                prompt_file = f.name

            if sys.platform == "win32":
                cmd = ["powershell", "-NoProfile", "-Command",
                       f"& '{opencode}' run -m 'opencode/mimo-v2.5-free' --file '{prompt_file}'"]
            else:
                cmd = [opencode, "run", "-m", "opencode/mimo-v2.5-free", "--file", prompt_file]

            env = os.environ.copy()
            env["OPENCODE_PROJECT_ROOT"] = project_root

            task.state = TaskState.EXECUTING
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=project_root,
                env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self._processes[task.task_id] = proc
            try:
                stdout, stderr = await asyncio.wait_for(
                    asyncio.to_thread(proc.communicate),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                self._kill_process(proc)
                return False, "", f"Task timed out after {timeout}s"
            finally:
                self._processes.pop(task.task_id, None)

            out = stdout.decode("utf-8", errors="replace") if stdout else ""
            err = stderr.decode("utf-8", errors="replace") if stderr else ""
            success = proc.returncode == 0
            return success, out, err

        except Exception as e:
            self._processes.pop(task.task_id, None)
            return False, "", str(e)
        finally:
            # Cleanup temp prompt file
            if prompt_file:
                try:
                    os.unlink(prompt_file)
                except OSError:
                    pass

    def cancel(self, task_id: str) -> bool:
        proc = self._processes.pop(task_id, None)
        if proc:
            self._kill_process(proc)
            return True
        return False

    def _kill_process(self, proc: subprocess.Popen) -> None:
        try:
            if sys.platform == "win32":
                proc.kill()
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    @property
    def active_count(self) -> int:
        return len(self._processes)
