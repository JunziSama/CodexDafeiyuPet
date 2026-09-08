from __future__ import annotations

import unittest

from controller.events import adapt_codex_event, model_label, runtime_message


class EventAdapterTests(unittest.TestCase):
    def test_prompt_text_is_never_forwarded(self):
        secret = "test-secret-user-prompt"
        event = adapt_codex_event({
            "hook_event_name": "UserPromptSubmit",
            "session_id": "thr_1",
            "turn_id": "turn_1",
            "prompt": secret,
            "cwd": "C:/private",
        })
        self.assertNotIn(secret, repr(event))
        self.assertNotIn("private", repr(event))
        self.assertEqual(event["state"], "THINKING")

    def test_tool_input_and_response_are_reduced_to_safe_status(self):
        secret = "TOKEN=super-secret"
        event = adapt_codex_event({
            "hook_event_name": "PostToolUse",
            "session_id": "thr_1",
            "turn_id": "turn_1",
            "tool_use_id": "call_1",
            "tool_name": "Bash",
            "tool_input": {"command": f"echo {secret}"},
            "tool_response": {"exit_code": 1, "output": secret},
        })
        self.assertTrue(event["failed"])
        self.assertEqual(event["state"], "ERROR")
        self.assertNotIn(secret, repr(event))

    def test_runtime_translation_is_protocol_v1(self):
        event = adapt_codex_event({
            "hook_event_name": "PreToolUse",
            "session_id": "thr_1",
            "turn_id": "turn_1",
            "tool_use_id": "call_1",
            "tool_name": "apply_patch",
            "model": "gpt-5.6-sol",
        })
        message = runtime_message(event, visible=False)
        self.assertEqual(message["protocolVersion"], 1)
        self.assertEqual(message["state"], "WORKING")
        self.assertFalse(message["visible"])
        self.assertEqual(message["agentLabel"], "GPT-5.6 Sol")
        self.assertEqual(message["detail"], "GPT-5.6 Sol · 正在执行任务")
        self.assertEqual(message["animationCue"], "tool-working")

    def test_each_hook_maps_to_a_bounded_animation_cue(self):
        cases = {
            "UserPromptSubmit": "task-thinking",
            "PreToolUse": "tool-working",
            "PermissionRequest": "approval-waiting",
            "Stop": "task-success",
        }
        for event_name, cue in cases.items():
            with self.subTest(event=event_name):
                event = adapt_codex_event({"hook_event_name": event_name})
                self.assertEqual(runtime_message(event)["animationCue"], cue)
        ok = adapt_codex_event({"hook_event_name": "PostToolUse", "tool_response": {}})
        failed = adapt_codex_event({"hook_event_name": "PostToolUse", "tool_response": {"failed": True}})
        self.assertEqual(runtime_message(ok)["animationCue"], "tool-finished")
        self.assertEqual(runtime_message(failed)["animationCue"], "task-error")

    def test_model_labels_are_bounded_and_unknown_values_fall_back(self):
        self.assertEqual(model_label("gpt-5.6-terra"), "GPT-5.6 Terra")
        self.assertEqual(model_label("gpt-5.5"), "GPT-5.5")
        self.assertEqual(model_label("private model with spaces"), "Codex")
        event = adapt_codex_event({
            "hook_event_name": "SessionStart",
            "session_id": "thr_1",
            "model": "gpt-5.6-luna",
        })
        self.assertEqual(event["modelSlug"], "gpt-5.6-luna")
        self.assertEqual(event["modelLabel"], "GPT-5.6 Luna")


if __name__ == "__main__":
    unittest.main()
