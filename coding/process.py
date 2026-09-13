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

        # Try where/which first
        try:
            result = subprocess.run(
                ["where", "opencode.exe"] if sys.platform == "win32" else ["which", "opencode"],
                capture_output=True, text=True, timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0 and result.stdout.strip():
                path = result.stdout.strip().splitlines()[0]
                if os.path.isfile(path) and os.path.getsize(path) > 1000:
                    self._opencode_path = path
                    return path
        except Exception:
            pass

        # Candidate paths — prefer the actual .exe binary (large file)
        candidates = []
        if sys.platform == "win32":
            npm_global = os.path.join(os.environ.get("APPDATA", ""), "npm")
            node_modules = os.path.join(npm_global, "node_modules")
            candidates = [
                # Prefer the actual binary from the platform-specific package
                os.path.join(node_modules, "opencode-windows-x64-baseline", "bin", "opencode.exe"),
                os.path.join(node_modules, "opencode-ai", "bin", "opencode.exe"),
                os.path.join(npm_global, "opencode.exe"),
            ]
        else:
            candidates = [
                "/usr/local/bin/opencode",
                "/usr/bin/opencode",
                os.path.expanduser("~/.local/bin/opencode"),
            ]

        for candidate in candidates:
            if os.path.isfile(candidate) and os.path.getsize(candidate) > 1000:
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
            return False, "", "Development engine executable not found. Install with: npm install -g opencode-ai"

        # Write prompt to temp file for OpenCode to read
        prompt_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.txt', delete=False, encoding='utf-8',
                dir=project_root
            ) as f:
                f.write(prompt)
                prompt_file = f.name

            # Build command:
            # opencode run -m <model> --auto --dir <project_root> "message"
            # --auto: auto-approve file writes (non-interactive)
            # --dir: set working directory
            # The prompt file is attached via --file, message tells what to do

            message = f"Read and execute the coding task described in the attached file '{os.path.basename(prompt_file)}'. All output files must go in: {project_root}"

            # Message MUST come before --file to avoid being consumed as a file argument
            cmd = [opencode, "run",
                   "-m", "opencode/mimo-v2.5-free",
                   "--auto",
                   "--dir", project_root,
                   message,
                   "--file", prompt_file]

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
