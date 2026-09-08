from __future__ import annotations

import os
import tempfile
import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from controller.bridge import BridgeService, send_local_message
from controller.process_watch import ProcessInfo, is_codex_desktop_process
from controller.pet_process import PetProcess
from controller.single_instance import InstanceMutex


class FakeStream:
    def __init__(self):
        self.lines = []

    def write(self, value):
        self.lines.append(value)

    def flush(self):
        return None


class FakeProcess:
    def __init__(self):
        self.stdin = FakeStream()
        self.waited = False
        self.killed = False

    def poll(self):
        return None

    def wait(self, timeout=None):
        self.waited = True
        return 0

    def kill(self):
        self.killed = True


class BridgeAndProcessTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows named mutex")
    def test_instance_mutex_allows_only_one_controller(self):
        name = rf"Local\DafeiyuCodexCompanion.Test.{uuid.uuid4()}"
        first = InstanceMutex.acquire(name)
        second = InstanceMutex.acquire(name)
        try:
            self.assertTrue(first.acquired)
            self.assertFalse(second.acquired)
        finally:
            second.close()
            first.close()

    def test_process_match_requires_codex_package_path(self):
        self.assertTrue(is_codex_desktop_process(ProcessInfo(
            1,
            "ChatGPT.exe",
            r"C:\Program Files\WindowsApps\OpenAI.Codex_26.1_x64__id\app\ChatGPT.exe",
        )))
        self.assertFalse(is_codex_desktop_process(ProcessInfo(
            2,
            "ChatGPT.exe",
            r"C:\Program Files\WindowsApps\OpenAI.ChatGPT_1_x64__id\app\ChatGPT.exe",
        )))
        self.assertFalse(is_codex_desktop_process(ProcessInfo(
            3,
            "codex.exe",
            r"C:\Users\example\AppData\Local\OpenAI\Codex\bin\codex.exe",
        )))

    def test_bridge_requires_token(self):
        received = []
        service = BridgeService("127.0.0.1", 0, "correct-token-value-123456789", received.append)
        service.start()
        port = service.server.server_address[1]
        try:
            self.assertFalse(send_local_message("127.0.0.1", port, "wrong", {"kind": "control"}))
            self.assertTrue(send_local_message(
                "127.0.0.1", port, "correct-token-value-123456789", {"kind": "control", "action": "show"}
            ))
        finally:
            service.close()
        self.assertEqual(received, [{"kind": "control", "action": "show"}])

    def test_pet_close_sends_shutdown_and_waits_without_force_kill(self):
        from queue import Queue
        pet = PetProcess(Path.cwd(), Queue())
        process = FakeProcess()
        pet.process = process
        pet.close("controlled-smoke", timeout=0.1)
        self.assertTrue(process.waited)
        self.assertFalse(process.killed)
        self.assertIn('"kind":"shutdown"', "".join(process.stdin.lines))

    def test_pet_process_passes_exact_shared_data_dir(self):
        from queue import Queue
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = root / "runtime"
            runtime.mkdir()
            (runtime / "eac_entry.py").write_text("", encoding="utf-8")
            data_dir = root / "shared-data"
            fake = FakeProcess()
            fake.stdout = []
            fake.stderr = []
            with patch("controller.pet_process.subprocess.Popen", return_value=fake) as popen:
                pet = PetProcess(root, Queue(), data_dir)
                self.assertTrue(pet.start(False))
            env = popen.call_args.kwargs["env"]
            self.assertEqual(env["DSH_PET_DATA_DIR"], str(data_dir))
            self.assertEqual(env["DSH_PET_VISIBLE"], "0")

    def test_pet_restart_failures_back_off_and_lock_after_five(self):
        from queue import Queue
        pet = PetProcess(Path.cwd(), Queue())
        delays = []
        for expected in range(1, 6):
            count, delay, blocked = pet._register_failure()
            self.assertEqual(count, expected)
            delays.append(delay)
        self.assertEqual(delays, [1.5, 3.0, 6.0, 12.0, 30.0])
        self.assertTrue(blocked)
        self.assertTrue(pet.restart_blocked)
        pet.reset_failure_lock()
        self.assertFalse(pet.restart_blocked)
        self.assertEqual(pet.consecutive_failures, 0)

    def test_stable_runtime_resets_failure_streak(self):
        from queue import Queue
        pet = PetProcess(Path.cwd(), Queue())
        pet.process = FakeProcess()
        pet.started_at = 10.0
        pet.consecutive_failures = 4
        with patch("controller.pet_process.time.monotonic", return_value=71.0):
            pet.poll()
        self.assertEqual(pet.consecutive_failures, 0)
        self.assertFalse(pet.restart_blocked)

    def test_hook_script_sends_only_sanitized_event(self):
        received = []
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp)
            token = "test-hook-token-12345678901234567890"
            (data_dir / "bridge-token").write_text(token, encoding="ascii")
            service = BridgeService("127.0.0.1", 0, token, received.append)
            service.start()
            try:
                package_root = Path(__file__).resolve().parents[2]
                payload = {
                    "hook_event_name": "PostToolUse",
                    "session_id": "thr_1",
                    "turn_id": "turn_1",
                    "tool_use_id": "call_1",
                    "tool_name": "Bash",
                    "model": "gpt-5.6-sol",
                    "tool_input": {"command": "echo SECRET_VALUE"},
                    "tool_response": {"exit_code": 0, "output": "SECRET_VALUE"},
                }
                env = dict(__import__("os").environ)
                env["DAFEIYU_CONTROLLER_DATA_DIR"] = str(data_dir)
                env["DAFEIYU_CONTROLLER_PORT"] = str(service.server.server_address[1])
                result = subprocess.run(
                    [sys.executable, str(package_root / "hooks" / "codex_event_hook.py")],
                    input=__import__("json").dumps(payload),
                    text=True,
                    capture_output=True,
                    env=env,
                    timeout=3,
                    check=False,
                )
            finally:
                service.close()
            audit = __import__("json").loads((data_dir / "hook-audit.json").read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(len(received), 1)
        self.assertNotIn("SECRET_VALUE", repr(received[0]))
        self.assertEqual(received[0]["modelLabel"], "GPT-5.6 Sol")
        self.assertTrue(audit["sendOk"])
        self.assertEqual(audit["event"], "PostToolUse")
        self.assertNotIn("SECRET_VALUE", repr(audit))


if __name__ == "__main__":
    unittest.main()
