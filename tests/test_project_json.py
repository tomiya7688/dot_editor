"""Issue #7: reject ambiguous/malformed JSON without losing editor state."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from pixel_commands import PixelCommandAPI, load_project


class ProjectJsonTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "project.json"

    def test_duplicate_keys_at_any_depth_are_rejected(self):
        for text in ('{"layers":[],"layers":[]}',
                     '{"extra":{"name":"first","name":"second"}}',
                     '{"name":1,"na\\u006de":2}'):
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                    load_project(self.path)
                self.assertEqual(self.path.read_text(encoding="utf-8"), text)

    def test_nonstandard_numbers_are_rejected_even_in_unknown_fields(self):
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                self.path.write_text('{"extra":' + constant + '}', encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "non-standard JSON constant"):
                    load_project(self.path)

    def test_deep_json_and_cli_failure_do_not_emit_traceback_or_write_output(self):
        self.path.write_text("[" * 10000 + "0" + "]" * 10000, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "nesting is too deep"):
            load_project(self.path)
        output = self.path.with_suffix(".png")
        result = subprocess.run(
            [sys.executable, "-m", "pixel_cli", "export", "--project", str(self.path),
             "--output", str(output)], capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("nesting is too deep", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(output.exists())

    def test_gui_failed_load_preserves_existing_document_and_history(self):
        from dot_editor import PixelEditor

        editor = PixelEditor.__new__(PixelEditor)
        editor.backend = PixelCommandAPI.new(2, layered=True).canvas
        editor.backend.paint(0, 0, (255, 0, 0, 255))
        original = editor.backend
        before = original.to_source()
        editor.report_error = Mock()
        editor.refresh_composite = Mock()
        editor.history = ["existing undo"]
        editor.future = ["existing redo"]
        for text in ('{"a":1,"a":2}', "[" * 10000 + "0" + "]" * 10000):
            self.path.write_text(text, encoding="utf-8")
            with patch("dot_editor.filedialog.askopenfilename", return_value=str(self.path)):
                editor.load_project()
            self.assertIs(editor.backend, original)
            self.assertEqual(editor.backend.to_source(), before)
            self.assertEqual(editor.history, ["existing undo"])
            self.assertEqual(editor.future, ["existing redo"])
        self.assertEqual(editor.report_error.call_count, 2)
        editor.refresh_composite.assert_not_called()
        self.assertTrue(editor.backend.undo())
        self.assertEqual(editor.backend.sample(0, 0)[3], 0)

    def test_valid_legacy_and_current_projects_still_load(self):
        legacy = {"canvas_size": 2, "pixels": [[None, None], [None, None]]}
        for source in (legacy, PixelCommandAPI.new(2, layered=True).canvas.to_source()):
            self.path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(load_project(self.path).resolution, (2, 2))

    def test_depth_limit_boundary(self):
        source = {"canvas_size": 2, "pixels": [[None, None], [None, None]]}
        # The root object counts as one container; unknown fields remain allowed.
        source["extra"] = json.loads("[" * 127 + "0" + "]" * 127)
        self.path.write_text(json.dumps(source), encoding="utf-8")
        self.assertEqual(load_project(self.path).resolution, (2, 2))
        source["extra"] = [source["extra"]]
        self.path.write_text(json.dumps(source), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "maximum 128"):
            load_project(self.path)


if __name__ == "__main__":
    unittest.main()
