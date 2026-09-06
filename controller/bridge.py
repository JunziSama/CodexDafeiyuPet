from __future__ import annotations

import hmac
import json
import socket
import socketserver
import threading
from collections.abc import Callable
from typing import Any


MAX_MESSAGE_BYTES = 32 * 1024


class BridgeRequestHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server: "BridgeServer" = self.server  # type: ignore[assignment]
        self.request.settimeout(0.5)
        chunks = bytearray()
        try:
            while len(chunks) <= MAX_MESSAGE_BYTES:
                part = self.request.recv(4096)
                if not part:
                    break
                chunks.extend(part)
                if b"\n" in part:
                    break
            raw = bytes(chunks).split(b"\n", 1)[0]
            if not raw or len(raw) > MAX_MESSAGE_BYTES:
                raise ValueError("invalid message size")
            message = json.loads(raw.decode("utf-8"))
            if not isinstance(message, dict):
                raise ValueError("message must be an object")
            supplied = str(message.pop("token", ""))
            if not hmac.compare_digest(supplied, server.token):
                raise PermissionError("invalid token")
            server.on_message(message)
            response = {"ok": True}
        except Exception as exc:
            response = {"ok": False, "error": type(exc).__name__}
        try:
            self.request.sendall((json.dumps(response) + "\n").encode("utf-8"))
        except OSError:
            pass


class BridgeServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], token: str, on_message: Callable[[dict[str, Any]], None]) -> None:
        self.token = token
        self.on_message = on_message
        super().__init__(address, BridgeRequestHandler)


class BridgeService:
    def __init__(self, host: str, port: int, token: str, on_message: Callable[[dict[str, Any]], None]) -> None:
        self.server = BridgeServer((host, port), token, on_message)
        self.thread = threading.Thread(target=self.server.serve_forever, name="dafeiyu-bridge", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1.0)


def send_local_message(host: str, port: int, token: str, message: dict[str, Any], timeout: float = 0.25) -> bool:
    payload = dict(message)
    payload["token"] = token
    data = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if len(data) > MAX_MESSAGE_BYTES:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout) as connection:
            connection.settimeout(timeout)
            connection.sendall(data)
            response = connection.recv(256)
        decoded = json.loads(response.decode("utf-8"))
        return isinstance(decoded, dict) and decoded.get("ok") is True
    except (OSError, ValueError):
        return False
