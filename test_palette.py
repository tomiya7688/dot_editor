"""Headless regressions for persistent CLI sessions and failed edits."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from pixel_cli import run_palette
from pixel_commands import PixelCommandAPI, save_project

ROOT = Path(__file__).resolve().parent
RED = (255, 0, 0, 255)
BLUE = (0, 0, 255, 255)


class PaletteTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.project = self.root / "project.json"
        PixelCommandAPI.new(4, layered=True).save(self.project)

    def session(self, commands: str, code: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(ROOT / "pixel_cli.py"), "palette",
             "--project", str(self.project)],
            input=commands, capture_output=True, text=True, encoding="utf-8",
            cwd=self.root, timeout=20,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        return result

    def test_multiple_edits_inspect_and_export_in_one_process(self) -> None:
        output = self.root / "完成 image.png"
        result = self.session(
            'edit --add-layer "人物 layer"\n'
            'edit --paint 1 1 #FF0000\n'
            'edit --split 1 1\n'
            'edit --paint-child 1 1 1 0 #0000FF\n'
            'inspect --sample 1 1 --child 1 0\n'
            f'export --output "{output}" --size 8\nquit\n'
        )
        report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith("{")))
        self.assertEqual(report["sample"]["rgba"], list(BLUE))
        model = PixelCommandAPI.load(self.project)
        self.assertEqual(model.canvas.active_layer, "人物 layer")
        self.assertEqual(model.sample(1, 1, child=(1, 0)), BLUE)
        with Image.open(output) as image:
            self.assertEqual(image.size, (8, 8))
            self.assertEqual(image.getpixel((3, 2)), BLUE)

    def test_failed_line_never_leaks_partial_edits_into_later_save(self) -> None:
        result = self.session(
            'edit --add-layer leaked --paint 99 0 #FF0000\n'
            'edit --paint 0 0 #0000FF\ninspect\n', code=2,
        )
        self.assertIn("outside", result.stderr)
        model = PixelCommandAPI.load(self.project)
        self.assertEqual(len(model.canvas.layers), 1)
        self.assertEqual(model.sample(0, 0), BLUE)

    def test_help_errors_and_noops_do_not_rewrite_project(self) -> None:
        before = (self.project.read_bytes(), self.project.stat().st_mtime_ns)
        result = self.session(
            'help\nhelp edit\nunknown\nedit --paint 0\n'
            'edit --paint 0 0 #GGGGGG\n"unfinished\n'
            'edit --erase 0 0\ninspect\nquit\n', code=2,
        )
        self.assertIn("no changes", result.stdout)
        self.assertIn("No closing quotation", result.stderr)
        self.assertEqual((self.project.read_bytes(), self.project.stat().st_mtime_ns), before)

    def test_session_cannot_redirect_the_edit_project_or_output(self) -> None:
        other = self.root / "other.json"
        other.write_text("keep", encoding="utf-8")
        before = self.project.read_bytes()
        self.session(
            f'edit --project "{other}" --paint 0 0 #FF0000\n'
            f'edit --output "{other}" --paint 0 0 #FF0000\nquit\n', code=2,
        )
        self.assertEqual(other.read_text(encoding="utf-8"), "keep")
        self.assertEqual(self.project.read_bytes(), before)

    def test_failed_save_keeps_memory_and_file_ready_for_next_command(self) -> None:
        api = PixelCommandAPI.load(self.project)
        calls = 0

        def fail_once(canvas, path):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("simulated disk failure")
            save_project(canvas, path)

        stream = io.StringIO('edit --paint 0 0 #FF0000\nedit --paint 1 1 #0000FF\n')
        with patch("sys.stdin", stream), patch("pixel_cli.save_project", side_effect=fail_once):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(run_palette(api, self.project), 2)
        self.assertIn("simulated disk failure", errors.getvalue())
        self.assertEqual(api.sample(0, 0)[3], 0)
        self.assertEqual(api.sample(1, 1), BLUE)
        self.assertEqual(PixelCommandAPI.load(self.project).canvas.to_source(), api.canvas.to_source())

    def test_windows_backslashes_and_quoted_spaces_survive_parsing(self) -> None:
        api = PixelCommandAPI.load(self.project)
        filename = r"C:\art work\test.png"
        with patch("sys.stdin", io.StringIO(f'export --output "{filename}"\n')):
            with patch.object(api, "export_png") as export, redirect_stdout(io.StringIO()):
                self.assertEqual(run_palette(api, self.project), 0)
        export.assert_called_once_with(Path(filename), None, output_resolution=None)


if __name__ == "__main__":
    unittest.main()
