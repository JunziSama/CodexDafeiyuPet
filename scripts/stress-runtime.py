from __future__ import annotations

import argparse
import ctypes
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
from pathlib import Path


CUES = (
    ("THINKING", "task-thinking"),
    ("WORKING", "tool-working"),
    ("WORKING", "tool-finished"),
    ("WAITING", "approval-waiting"),
    ("SUCCESS", "task-success"),
    ("ERROR", "task-error"),
)


def windows_process_snapshot() -> dict[int, tuple[int, str]]:
    if os.name != "nt":
        return {}

    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.c_ulong), ("cntUsage", ctypes.c_ulong),
            ("th32ProcessID", ctypes.c_ulong), ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", ctypes.c_ulong), ("cntThreads", ctypes.c_ulong),
            ("th32ParentProcessID", ctypes.c_ulong), ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", ctypes.c_ulong), ("szExeFile", ctypes.c_wchar * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel32.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessEntry)]
    kernel32.Process32FirstW.restype = ctypes.c_int
    kernel32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessEntry)]
    kernel32.Process32NextW.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot in (None, ctypes.c_void_p(-1).value):
        return {}
    result: dict[int, tuple[int, str]] = {}
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            result[int(entry.th32ProcessID)] = (int(entry.th32ParentProcessID), entry.szExeFile)
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return result


def descendant_ids(root_pid: int, snapshot: dict[int, tuple[int, str]]) -> set[int]:
    descendants: set[int] = set()
    changed = True
    while changed:
        changed = False
        for pid, (parent, _name) in snapshot.items():
            if pid not in descendants and (parent == root_pid or parent in descendants):
                descendants.add(pid)
                changed = True
    return descendants


def windows_working_set(pid: int) -> int | None:
    if os.name != "nt":
        return None

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessMemoryCounters), ctypes.c_ulong]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    handle = kernel32.OpenProcess(0x1000 | 0x0010, False, pid)
    if not handle:
        return None
    try:
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return None
        return int(counters.WorkingSetSize)
    finally:
        kernel32.CloseHandle(handle)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="离屏快速切换和长时运行压力测试")
    parser.add_argument("--package-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--vendor-root", type=Path)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--soak-seconds", type=float, default=0.0)
    parser.add_argument("--interval", type=float, default=0.02)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.package_root.resolve()
    runtime = root / "runtime"
    vendor = (args.vendor_root or runtime / "vendor").resolve()
    entry = runtime / "eac_entry.py"
    if not entry.is_file():
        raise FileNotFoundError(entry)
    if not vendor.is_dir():
        raise FileNotFoundError(f"vendor runtime not found: {vendor}")

    env = os.environ.copy()
    env.update({
        "QT_QPA_PLATFORM": "offscreen",
        "PYTHONPATH": os.pathsep.join((str(vendor), str(runtime))),
        "DSH_PET_VISIBLE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    output: queue.Queue[str] = queue.Queue()
    errors: list[str] = []
    rss_samples: list[int] = []
    seen_ffmpeg: set[int] = set()
    max_ffmpeg = 0
    started = time.monotonic()

    with tempfile.TemporaryDirectory(prefix="dafeiyu-stress-") as data_dir:
        env["DSH_PET_DATA_DIR"] = data_dir
        process = subprocess.Popen(
            [os.fspath(Path(os.sys.executable)), os.fspath(entry)],
            cwd=root,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        def read_stdout() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                output.put(line.strip())

        def read_stderr() -> None:
            assert process.stderr is not None
            errors.extend(line.strip() for line in process.stderr if line.strip())

        threading.Thread(target=read_stdout, daemon=True).start()
        threading.Thread(target=read_stderr, daemon=True).start()

        try:
            def sample_processes() -> None:
                nonlocal max_ffmpeg
                rss = windows_working_set(process.pid)
                if rss is not None:
                    rss_samples.append(rss)
                snapshot = windows_process_snapshot()
                descendants = descendant_ids(process.pid, snapshot)
                ffmpeg = {
                    pid for pid in descendants
                    if "ffmpeg" in snapshot.get(pid, (0, ""))[1].lower()
                }
                seen_ffmpeg.update(ffmpeg)
                max_ffmpeg = max(max_ffmpeg, len(ffmpeg))

            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"runtime exited early ({process.returncode}): {errors!r}")
                try:
                    line = output.get(timeout=0.25)
                except queue.Empty:
                    continue
                try:
                    if json.loads(line).get("kind") == "ready":
                        break
                except ValueError:
                    continue
            else:
                raise TimeoutError(f"runtime did not become ready: {errors!r}")

            assert process.stdin is not None
            process.stdin.write(json.dumps({
                "protocolVersion": 1,
                "kind": "hello",
                "state": "IDLE",
                "agentLabel": "Codex",
                "visible": True,
            }) + "\n")
            for index in range(max(0, args.iterations)):
                state, cue = CUES[index % len(CUES)]
                process.stdin.write(json.dumps({
                    "protocolVersion": 1,
                    "kind": "state",
                    "state": state,
                    "animationCue": cue,
                    "agentLabel": "Codex",
                    "message": f"stress-{index}",
                }) + "\n")
                process.stdin.flush()
                if index % 10 == 0:
                    sample_processes()
                time.sleep(max(0.0, args.interval))

            soak_deadline = time.monotonic() + max(0.0, args.soak_seconds)
            next_progress = time.monotonic() + 60.0
            pulse = 0
            while time.monotonic() < soak_deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"runtime exited during soak ({process.returncode}): {errors!r}")
                state, cue = CUES[pulse % len(CUES)]
                process.stdin.write(json.dumps({
                    "protocolVersion": 1,
                    "kind": "state",
                    "state": state,
                    "animationCue": cue,
                    "agentLabel": "Codex",
                }) + "\n")
                process.stdin.flush()
                pulse += 1
                sample_processes()
                if time.monotonic() >= next_progress:
                    rss_now = rss_samples[-1] / (1024 * 1024) if rss_samples else 0.0
                    elapsed_now = time.monotonic() - started
                    print(
                        f"runtime-stress-progress elapsed={elapsed_now:.0f}s "
                        f"rss_mib={rss_now:.2f} ffmpeg_children_max={max_ffmpeg}",
                        flush=True,
                    )
                    next_progress += 60.0
                time.sleep(min(5.0, max(0.05, soak_deadline - time.monotonic())))

            process.stdin.write(json.dumps({"protocolVersion": 1, "kind": "shutdown"}) + "\n")
            process.stdin.flush()
            process.wait(timeout=15)
            if process.returncode != 0:
                raise RuntimeError(f"runtime exit code {process.returncode}: {errors!r}")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

    time.sleep(0.5)
    final_snapshot = windows_process_snapshot()
    lingering = sorted(
        pid for pid in seen_ffmpeg
        if pid in final_snapshot and "ffmpeg" in final_snapshot[pid][1].lower()
    )
    if lingering:
        raise RuntimeError(f"orphan ffmpeg processes remain: {lingering}")
    elapsed = time.monotonic() - started
    rss_min = min(rss_samples) / (1024 * 1024) if rss_samples else 0.0
    rss_max = max(rss_samples) / (1024 * 1024) if rss_samples else 0.0
    print(
        f"runtime-stress-ok iterations={args.iterations} soak_seconds={args.soak_seconds:g} "
        f"elapsed={elapsed:.2f} rss_mib={rss_min:.2f}..{rss_max:.2f} "
        f"ffmpeg_children_max={max_ffmpeg} ffmpeg_lingering=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
