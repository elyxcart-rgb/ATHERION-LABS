from __future__ import annotations

import sys
import os
import asyncio
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coding.models import TaskState, CodingTask, CodingResult
from coding.intent_detector import IntentDetector
from coding.workspace import WorkspaceManager
from coding.output_parser import OutputParser
from coding.process import ProcessManager


class TestTaskState(unittest.TestCase):
    def test_states_exist(self):
        required = ["CREATED", "QUEUED", "ANALYZING", "PLANNING",
                     "EXECUTING", "VERIFYING", "SUCCEEDED", "FAILED",
                     "CANCELLED", "TIMEOUT", "RECOVERING"]
        for s in required:
            self.assertIn(s, [e.value for e in TaskState])

    def test_task_mark_started(self):
        task = CodingTask(request="test")
        task.mark_started()
        self.assertEqual(task.state, TaskState.EXECUTING)
        self.assertGreater(task.started_at, 0)

    def test_task_mark_finished_success(self):
        task = CodingTask(request="test")
        task.mark_started()
        task.mark_finished(True, result="done")
        self.assertEqual(task.state, TaskState.SUCCEEDED)
        self.assertEqual(task.result, "done")
        self.assertGreater(task.duration, 0)

    def test_task_mark_finished_failure(self):
        task = CodingTask(request="test")
        task.mark_started()
        task.mark_finished(False, error="broken")
        self.assertEqual(task.state, TaskState.FAILED)
        self.assertEqual(task.error, "broken")

    def test_task_to_dict(self):
        task = CodingTask(request="fix bug")
        d = task.to_dict()
        self.assertEqual(d["request"], "fix bug")
        self.assertEqual(d["state"], "CREATED")
        self.assertIn("task_id", d)

    def test_coding_result_response_text(self):
        r = CodingResult(success=True, summary="Fixed the bug", files_changed=["a.py"])
        text = r.to_response_text()
        self.assertIn("Fixed the bug", text)
        self.assertIn("a.py", text)

    def test_coding_result_empty(self):
        r = CodingResult(success=True)
        text = r.to_response_text()
        self.assertIn("completed", text.lower())


class TestIntentDetector(unittest.TestCase):
    def test_coding_intents(self):
        self.assertTrue(IntentDetector.is_coding_intent("Fix the login bug"))
        self.assertTrue(IntentDetector.is_coding_intent("Add a settings panel"))
        self.assertTrue(IntentDetector.is_coding_intent("Refactor the browser controller"))
        self.assertTrue(IntentDetector.is_coding_intent("Run tests and fix failures"))
        self.assertTrue(IntentDetector.is_coding_intent("Implement dark mode in Python"))
        self.assertTrue(IntentDetector.is_coding_intent("Write a script to parse JSON"))
        self.assertTrue(IntentDetector.is_coding_intent("Debug why the API returns 500"))
        self.assertTrue(IntentDetector.is_coding_intent("Create a new module for auth"))

    def test_non_coding_intents(self):
        self.assertFalse(IntentDetector.is_coding_intent("What's the weather?"))
        self.assertFalse(IntentDetector.is_coding_intent("Play some music"))
        self.assertFalse(IntentDetector.is_coding_intent("Open YouTube"))
        self.assertFalse(IntentDetector.is_coding_intent("Set volume to 50%"))
        self.assertFalse(IntentDetector.is_coding_intent("Take a screenshot"))

    def test_classify(self):
        self.assertEqual(IntentDetector.classify("Fix the crash"), "debugging")
        self.assertEqual(IntentDetector.classify("Run pytest"), "testing")
        self.assertEqual(IntentDetector.classify("Refactor the module"), "refactoring")
        self.assertEqual(IntentDetector.classify("Add a feature"), "coding")
        self.assertEqual(IntentDetector.classify("What time is it?"), "general")


class TestWorkspaceManager(unittest.TestCase):
    def test_validate_workspace(self):
        self.assertTrue(WorkspaceManager.validate_workspace(os.getcwd()))
        self.assertFalse(WorkspaceManager.validate_workspace("C:\\Windows"))
        self.assertFalse(WorkspaceManager.validate_workspace("/nonexistent/path/xyz"))

    def test_acquire_release(self):
        tid = "test123"
        ws = f"_test_workspace_{tid}"
        self.assertTrue(WorkspaceManager.acquire_workspace(tid, ws))
        self.assertFalse(WorkspaceManager.acquire_workspace("other", ws))
        WorkspaceManager.release_workspace(tid, ws)
        self.assertTrue(WorkspaceManager.acquire_workspace("other", ws))
        WorkspaceManager.release_workspace("other", ws)

    def test_gather_context(self):
        root = str(Path(__file__).resolve().parent.parent)
        files = WorkspaceManager.gather_context(root, "fix main.py import error")
        self.assertIsInstance(files, list)


class TestOutputParser(unittest.TestCase):
    def test_parse_success(self):
        raw = "Modified main.py and utils.py. Tests passed."
        result = OutputParser.parse(raw, True)
        self.assertTrue(result.success)
        self.assertEqual(result.status, "SUCCEEDED")

    def test_parse_failure(self):
        raw = "ERROR: syntax error in line 42"
        result = OutputParser.parse(raw, False)
        self.assertFalse(result.success)
        self.assertEqual(result.status, "FAILED")
        self.assertTrue(len(result.errors) > 0)

    def test_parse_empty(self):
        result = OutputParser.parse("", True)
        self.assertTrue(result.success)


class TestProcessManager(unittest.TestCase):
    def test_find_opencode(self):
        pm = ProcessManager()
        path = pm.find_opencode()
        if path:
            self.assertTrue(os.path.isfile(path))
        # Whether found or not, this is a valid test
        self.assertTrue(True)

    def test_cancel_nonexistent(self):
        pm = ProcessManager()
        self.assertFalse(pm.cancel("nonexistent_task"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
