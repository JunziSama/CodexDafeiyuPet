from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="离屏验证增强桌宠告别协议")
    parser.add_argument("--package-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--mode",
        choices=("current_then_farewell", "farewell_only", "current_only", "bubble_sync"),
        default="farewell_only",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.package_root.resolve()
    runtime = root / "runtime"
    entry = runtime / "eac_entry.py"
    if not entry.is_file():
        raise FileNotFoundError(entry)

    env = os.environ.copy()
    env.update({
        "QT_QPA_PLATFORM": "offscreen",
        "PYTHONPATH": os.pathsep.join([str(runtime / "vendor"), str(runtime)]),
        "DSH_PET_VISIBLE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    output: queue.Queue[str] = queue.Queue()
    errors: list[str] = []

    with tempfile.TemporaryDirectory(prefix="dafeiyu-farewell-") as data_dir:
        env["DSH_PET_DATA_DIR"] = data_dir
        (Path(data_dir) / "config.json").write_text(
            json.dumps({"version": 5, "exit_animation_mode": args.mode}),
            encoding="utf-8",
        )
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

        def wait_kind(kind: str, timeout: float) -> dict:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    line = output.get(timeout=min(0.5, max(0.01, deadline - time.monotonic())))
                except queue.Empty:
                    continue
                try:
                    value = json.loads(line)
                except ValueError:
                    continue
                if value.get("protocolVersion") == 1 and value.get("kind") == kind:
                    return value
            raise TimeoutError(f"未收到 {kind}；stderr={errors!r}")

        try:
            wait_kind("ready", min(15.0, args.timeout))
            assert process.stdin is not None
            for message in (
                {
                    "protocolVersion": 1,
                    "kind": "hello",
                    "state": "IDLE",
                    "message": "smoke",
                    "detail": "Codex · 等待下一次任务",
                    "agentLabel": "Codex",
                    "visible": True,
                },
                {
                    "protocolVersion": 1,
                    "kind": "farewell",
                    "state": "DISCONNECTED",
                    "message": "Codex 已关闭，下次见",
                    "detail": "Codex · 本次陪伴结束",
                    "agentLabel": "Codex",
                    "animation": "点击回应 - 元气挥手",
                    "bubbleDurationMs": 6000,
                    "playbackSpeed": 1.0,
                    "visible": True,
                },
            ):
                process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            process.stdin.flush()
            wait_kind("farewell-complete", args.timeout)
            process.stdin.write(json.dumps({"protocolVersion": 1, "kind": "shutdown"}) + "\n")
            process.stdin.flush()
            process.wait(timeout=7)
            if process.returncode != 0:
                raise RuntimeError(f"桌宠退出码 {process.returncode}；stderr={errors!r}")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=3)

    print(f"farewell-protocol-ok:{args.mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
