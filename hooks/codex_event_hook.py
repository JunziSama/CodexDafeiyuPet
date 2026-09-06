"""One-shot, non-blocking Codex lifecycle event sender.

The script intentionally discards prompt text, cwd, transcript paths, tool
arguments and tool responses after extracting boolean/numeric status flags.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from controller.config import default_data_dir
from controller.events import adapt_codex_event


MAX_STDIN_BYTES = 1024 * 1024
MAX_WIRE_BYTES = 32 * 1024


def _read_input() -> dict[str, Any]:
    raw = sys.stdin.buffer.read(MAX_STDIN_BYTES + 1)
    if len(raw) > MAX_STDIN_BYTES:
        raise ValueError("hook input too large")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("hook input must be an object")
    return value


def _send(event: dict[str, Any]) -> bool:
    data_dir = Path(os.environ.get("DAFEIYU_CONTROLLER_DATA_DIR") or default_data_dir())
    try:
        token = (data_dir / "bridge-token").read_text(encoding="ascii").strip()
    except OSError:
        return False
    event["token"] = token
    wire = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if len(wire) > MAX_WIRE_BYTES:
        return False
    port = int(os.environ.get("DAFEIYU_CONTROLLER_PORT", "46837"))
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.15) as connection:
            connection.settimeout(0.15)
            connection.sendall(wire)
            response = connection.recv(256)
        decoded = json.loads(response.decode("utf-8"))
        return isinstance(decoded, dict) and decoded.get("ok") is True
    except (OSError, ValueError):
        return False


def _write_audit(data_dir: Path, event: dict[str, Any], send_ok: bool) -> None:
    """Overwrite one bounded, privacy-safe status record for tray diagnostics."""
    value = {
        "timestamp": int(time.time()),
        "event": str(event.get("event") or "")[:64],
        "modelSlug": str(event.get("modelSlug") or "")[:96],
        "modelLabel": str(event.get("modelLabel") or "Codex")[:96],
        "toolCategory": str(event.get("toolCategory") or "")[:64],
        "sendOk": bool(send_ok),
    }
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        target = data_dir / "hook-audit.json"
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, target)
    except OSError:
        pass


def main() -> int:
    event_name = ""
    try:
        payload = _read_input()
        event_name = str(payload.get("hook_event_name") or "")
        event = adapt_codex_event(payload)
        data_dir = Path(os.environ.get("DAFEIYU_CONTROLLER_DATA_DIR") or default_data_dir())
        send_ok = _send(event)
        _write_audit(data_dir, event, send_ok)
    except Exception:
        # Observability must never block, approve, deny, or otherwise alter Codex.
        pass
    if event_name == "Stop":
        # Stop requires JSON stdout on a successful command hook.
        sys.stdout.write("{}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
