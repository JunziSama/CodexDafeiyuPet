from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from queue import Queue
from typing import Any


class PetProcess:
    """Supervise the existing JSON-lines pet runtime without importing Qt."""

    def __init__(self, package_root: Path, event_queue: Queue, data_dir: Path | None = None) -> None:
        self.package_root = Path(package_root)
        self.runtime_entry = self.package_root / "runtime" / "eac_entry.py"
        self.event_queue = event_queue
        self.data_dir = Path(data_dir) if data_dir is not None else None
        self.process: subprocess.Popen[str] | None = None
        self.ready = False
        self.expected_stop: str | None = None
        self.stop_deadline = 0.0

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, visible: bool = True) -> bool:
        if self.running:
            return True
        if not self.runtime_entry.is_file():
            self.event_queue.put({"source": "pet", "kind": "start-error", "detail": "runtime-not-found"})
            return False
        env = os.environ.copy()
        runtime_dir = self.package_root / "runtime"
        vendor_dir = runtime_dir / "vendor"
        current_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join(
            [str(vendor_dir), str(runtime_dir)] + ([current_pythonpath] if current_pythonpath else [])
        )
        env["DSH_PET_APP_DIR_NAME"] = "codex-dafeiyu-enhanced"
        if self.data_dir is not None:
            # Scheduled tasks launched from the Codex desktop process can inherit
            # its AppContainer APPDATA.  An exact path keeps the pet and controller
            # on the same persistent configuration regardless of their parent.
            env["DSH_PET_DATA_DIR"] = str(self.data_dir)
        env["DSH_PET_VISIBLE"] = "1" if visible else "0"
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        try:
            self.process = subprocess.Popen(
                [sys.executable, str(self.runtime_entry)],
                cwd=str(self.package_root),
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=flags,
            )
        except OSError as exc:
            self.process = None
            self.event_queue.put({"source": "pet", "kind": "start-error", "detail": type(exc).__name__})
            return False
        self.ready = False
        self.expected_stop = None
        threading.Thread(target=self._read_stdout, args=(self.process,), daemon=True).start()
        threading.Thread(target=self._read_stderr, args=(self.process,), daemon=True).start()
        return True

    def send(self, message: dict[str, Any]) -> bool:
        process = self.process
        if process is None or process.poll() is not None or process.stdin is None:
            return False
        try:
            process.stdin.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
            process.stdin.flush()
            return True
        except (OSError, ValueError):
            return False

    def stop(self, reason: str) -> None:
        if not self.running:
            return
        self.expected_stop = reason
        self.stop_deadline = time.monotonic() + 5.0
        self.send({"protocolVersion": 1, "kind": "shutdown", "reason": reason})

    def close(self, reason: str = "controller-exit", timeout: float = 5.0) -> None:
        """Gracefully stop, then force termination so no orphan pet remains."""
        process = self.process
        if process is None:
            return
        self.stop(reason)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                pass
        self.process = None
        self.ready = False
        self.expected_stop = None

    def poll(self) -> None:
        process = self.process
        if process is None:
            return
        code = process.poll()
        if code is None and self.expected_stop and time.monotonic() >= self.stop_deadline:
            process.kill()
            return
        if code is None:
            return
        expected = self.expected_stop
        self.process = None
        self.ready = False
        self.expected_stop = None
        self.event_queue.put({"source": "pet", "kind": "exit", "code": code, "expected": expected})

    def _read_stdout(self, process: subprocess.Popen[str]) -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict) and value.get("protocolVersion") == 1:
                self.event_queue.put({"source": "pet", **value})

    @staticmethod
    def _read_stderr(process: subprocess.Popen[str]) -> None:
        if process.stderr is None:
            return
        for line in process.stderr:
            line = line.strip()
            if line:
                logging.getLogger("dafeiyu.pet").warning("pet runtime: %s", line[:500])
