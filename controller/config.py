from __future__ import annotations

import json
import logging
import os
import secrets
from pathlib import Path
from typing import Any


DEFAULTS: dict[str, Any] = {
    "version": 3,
    "enhanced_enabled": False,
    "auto_accompany": True,
    "visible": True,
    "bridge_host": "127.0.0.1",
    "bridge_port": 46837,
    "process_poll_ms": 1500,
    "python_executable": "",
    "hook_event_count": 0,
    "hook_last_event": "",
    "hook_last_received_at": 0,
    "hook_last_model_slug": "",
    "hook_last_model_label": "Codex",
    "hook_last_applied": False,
    "hook_ignored_count": 0,
}


def default_data_dir() -> Path:
    return Path.home() / ".codex" / "dafeiyu-companion-data"


class ConfigStore:
    """Small atomic JSON store shared by the tray and one-shot launcher."""

    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.path = self.data_dir / "controller.json"
        self.token_path = self.data_dir / "bridge-token"
        self.data = dict(DEFAULTS)
        self.reload()

    def reload(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        try:
            loaded_version = int(raw.get("version") or 0)
        except (TypeError, ValueError):
            loaded_version = 0
        for key in DEFAULTS:
            if key in raw:
                self.data[key] = raw[key]
        self.data["enhanced_enabled"] = bool(self.data["enhanced_enabled"])
        self.data["auto_accompany"] = bool(self.data["auto_accompany"])
        self.data["visible"] = bool(self.data["visible"])
        self.data["bridge_host"] = "127.0.0.1"  # Never expose the bridge remotely.
        try:
            self.data["bridge_port"] = max(1024, min(65535, int(self.data["bridge_port"])))
            self.data["process_poll_ms"] = max(500, min(10000, int(self.data["process_poll_ms"])))
        except (TypeError, ValueError):
            self.data["bridge_port"] = DEFAULTS["bridge_port"]
            self.data["process_poll_ms"] = DEFAULTS["process_poll_ms"]
        self.data["python_executable"] = str(self.data.get("python_executable") or "")
        try:
            self.data["hook_event_count"] = max(0, int(self.data.get("hook_event_count") or 0))
            self.data["hook_last_received_at"] = max(0, int(self.data.get("hook_last_received_at") or 0))
            self.data["hook_ignored_count"] = max(0, int(self.data.get("hook_ignored_count") or 0))
        except (TypeError, ValueError):
            self.data["hook_event_count"] = 0
            self.data["hook_last_received_at"] = 0
            self.data["hook_ignored_count"] = 0
        self.data["hook_last_event"] = str(self.data.get("hook_last_event") or "")[:64]
        self.data["hook_last_model_slug"] = str(self.data.get("hook_last_model_slug") or "")[:96]
        self.data["hook_last_model_label"] = str(self.data.get("hook_last_model_label") or "Codex")[:96]
        if "hook_last_applied" in raw:
            self.data["hook_last_applied"] = bool(raw["hook_last_applied"])
        else:
            # Version 2 applied every accepted hook, so preserve the meaning of
            # its last received event when upgrading the diagnostic record.
            self.data["hook_last_applied"] = bool(
                loaded_version == 2 and self.data["hook_last_received_at"]
            )
        self.data["version"] = 3

    def hook_audit(self) -> dict[str, Any]:
        try:
            value = json.loads((self.data_dir / "hook-audit.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if key not in DEFAULTS:
            raise KeyError(key)
        self.data[key] = value
        self.save()

    def update(self, **values: Any) -> None:
        unknown = set(values) - set(DEFAULTS)
        if unknown:
            raise KeyError(next(iter(unknown)))
        self.data.update(values)
        self.save()

    def save(self) -> bool:
        temp = self.path.with_suffix(".tmp")
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            temp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp, self.path)
            return True
        except OSError as exc:
            logging.getLogger("dafeiyu.config").warning("controller config save failed: %s", type(exc).__name__)
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            return False

    def bridge_token(self) -> str:
        try:
            token = self.token_path.read_text(encoding="ascii").strip()
            if len(token) >= 32:
                return token
        except OSError:
            pass
        self.data_dir.mkdir(parents=True, exist_ok=True)
        token = secrets.token_urlsafe(32)
        temp = self.token_path.with_suffix(".tmp")
        temp.write_text(token, encoding="ascii")
        os.replace(temp, self.token_path)
        return token
