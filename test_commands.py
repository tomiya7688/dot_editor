"""Shared Command API regressions for GUI/CUI/automation callers."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from pixel_backend import PixelCanvas
from pixel_commands import PixelCommandAPI, load_project
from pixel_layers import LayeredPixelCanvas

ROOT = Path(__file__).resolve().parent
RED = (255, 0, 0, 255)
GREEN = (0, 255, 0, 255)
BLUE = (0, 0, 255, 255)


class CommandApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def cli(self, *arguments: object, code: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(ROOT / "pixel_cli.py"), *(str(a) for a in arguments)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=40,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1"},
        )
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        return result

    def test_direct_api_matches_backend_for_core_edits(self) -> None:
        api = PixelCommandAPI.new(8, 6, layered=True)
        expected = LayeredPixelCanvas(8, 6)

        self.assertTrue(api.paint(1, 1, RED))
        self.assertTrue(expected.paint(1, 1, RED))
        self.assertTrue(api.split(1, 1))
        self.assertTrue(expected.split_cell(1, 1))
        self.assertTrue(api.paint(1, 1, BLUE, child=(1, 0)))
        self.assertTrue(expected.paint(1, 1, BLUE, child=(1, 0)))
        self.assertTrue(api.collapse(1, 1))
        self.assertTrue(expected.collapse_cell(1, 1))

        self.assertTrue(api.add_layer("人物"))
        expected.add_layer("人物")
        self.assertTrue(api.paint(2, 2, GREEN))
        self.assertTrue(expected.paint(2, 2, GREEN))
        self.assertTrue(api.set_resolution(7, 5))
        self.assertTrue(expected.set_resolution(7, 5))
        self.assertEqual(api.canvas.to_source(), expected.to_source())

        report = api.inspect_sample(2, 2)
        self.assertEqual(report["resolution"], [7, 5])
        self.assertEqual(report["project_type"], "layered")
        self.assertEqual(report["sample"]["layer"], "人物")

    def test_execute_is_stable_for_automation_callers(self) -> None:
        api = PixelCommandAPI.new(4, layered=True)
        self.assertTrue(api.execute("paint", x=1, y=1, color=RED))
        self.assertEqual(
            api.execute("sample", x=1, y=1),
            RED,
        )
        self.assertTrue(api.execute("split", x=1, y=1))
        self.assertTrue(
            api.execute("erase", x=1, y=1, child=(0, 0))
        )
        self.assertEqual(api.execute("sample", x=1, y=1, child=(0, 0))[3], 0)
        self.assertTrue(api.execute("add_layer", name="人物"))
        self.assertTrue(api.execute("move_layer", direction="down"))
        self.assertEqual(list(api.canvas.layers), ["人物", "背景"])
        self.assertTrue(api.execute("set_layer_visibility", visible=False))
        self.assertFalse(api.canvas.is_layer_visible())
        self.assertFalse(api.execute("set_layer_visibility", visible=False))
        self.assertFalse(api.inspect()["layers"][0]["visible"])
        self.assertTrue(api.execute("rename_layer", new_name="キャラ"))
        self.assertEqual(api.canvas.active_layer, "キャラ")
        self.assertEqual(list(api.canvas.layers), ["キャラ", "背景"])
        with self.assertRaisesRegex(ValueError, "unknown command"):
            api.execute("not-a-command")

    def test_project_io_and_export_share_api(self) -> None:
        project = self.root / "project.json"
        output = self.root / "output.png"
        api = PixelCommandAPI.new(4, 3, layered=True)
        api.paint(1, 1, RED)
        api.split(1, 1)
        api.paint(1, 1, BLUE, child=(1, 1))
        api.save(project)

        restored = PixelCommandAPI.load(project)
        self.assertEqual(restored.canvas.to_source(), api.canvas.to_source())
        restored.export_png(output)
        with Image.open(output) as image:
            self.assertEqual(image.size, (8, 6))
            self.assertEqual(image.getpixel((3, 3)), BLUE)

    def test_layer_sample_does_not_change_active_layer(self) -> None:
        api = PixelCommandAPI.new(4, layered=True)
        api.paint(0, 0, RED)
        api.add_layer("人物")
        api.paint(0, 0, BLUE)
        before = api.canvas.active_layer
        self.assertEqual(api.sample(0, 0, layer="背景"), RED)
        self.assertEqual(api.canvas.active_layer, before)
        self.assertEqual(api.sample(0, 0), BLUE)

    def test_flat_layer_operations_are_rejected(self) -> None:
        api = PixelCommandAPI.new(4)
        for operation in (
            lambda: api.add_layer("人物"),
            lambda: api.select_layer("背景"),
            lambda: api.remove_layer(),
            lambda: api.move_layer("up"),
            lambda: api.set_layer_visibility(False),
            lambda: api.rename_layer("新規"),
            lambda: api.sample(0, 0, layer="背景"),
        ):
            with self.subTest(operation=operation):
                with self.assertRaises(ValueError):
                    operation()

    def test_split_region_validates_rectangular_resolution_correctly(self) -> None:
        # Doubling 1800x500 is 3600x1000 (valid). Validating it as a
        # square 3600x3600 would incorrectly reject it by the pixel budget.
        api = PixelCommandAPI.new(1800, 500)
        self.assertEqual(api.split_region(0, 0, 1, 1), 1)
        self.assertTrue(api.is_split(0, 0))

    def test_split_region_prevalidates_split_budget(self) -> None:
        api = PixelCommandAPI.new(4)
        api.split(0, 0)
        before = api.canvas.to_source()
        with patch.object(PixelCanvas, "MAX_SPLITS", 1):
            with self.assertRaisesRegex(ValueError, "too many"):
                api.split_region(1, 0, 2, 1)
        self.assertEqual(api.canvas.to_source(), before)
        self.assertFalse(api.is_split(1, 0))

    def fake_editor(self):
        from dot_editor import PixelEditor
        editor = PixelEditor.__new__(PixelEditor)
        editor.backend = LayeredPixelCanvas(4)
        editor.num_pixels_x = editor.num_pixels_y = 4
        editor.canvas_width = editor.canvas_height = 400
        editor.zoom_factor = 1.0
        editor.canvas = Mock()
        editor.canvas.canvasx.side_effect = lambda value: value
        editor.canvas.canvasy.side_effect = lambda value: value
        editor.history, editor.future = [], []
        editor.selected_cell = None
        editor.tool = "brush"
        editor.current_color = (255, 0, 0)
        editor.current_detail_policy = lambda: "preserve"
        editor.report_error = lambda error: self.fail(str(error))
        editor._finish_edit = lambda before: None
        editor.refresh_composite = lambda: None
        editor.refresh_layer_list = lambda: None
        editor.create_grid = lambda: None
        editor.update_canvas = lambda: None
        return editor

    def test_canvas_image_is_centered_only_when_it_fits(self) -> None:
        from dot_editor import PixelEditor

        self.assertEqual(PixelEditor.image_origin(1000, 800, 640, 480), (180, 160))
        self.assertEqual(PixelEditor.image_origin(500, 300, 640, 480), (0, 0))

    def test_gui_handlers_route_through_command_api(self) -> None:
        from pixel_commands import PixelCommandAPI as Commands
        editor = self.fake_editor()
        calls: list[str] = []

        original_paint = Commands.paint
        original_split = Commands.split
        original_resolution = Commands.set_resolution

        def spy_paint(api, *args, **kwargs):
            calls.append("paint")
            return original_paint(api, *args, **kwargs)

        def spy_split(api, *args, **kwargs):
            calls.append("split")
            return original_split(api, *args, **kwargs)

        def spy_resolution(api, *args, **kwargs):
            calls.append("resolution")
            return original_resolution(api, *args, **kwargs)

        with patch.object(Commands, "paint", spy_paint),              patch.object(Commands, "split", spy_split),              patch.object(Commands, "set_resolution", spy_resolution):
            editor.paint_pixel(SimpleNamespace(x=150, y=150))
            editor.selected_cell = (1, 1)
            editor.split_selected_cell()
            editor.resize_logical_canvas(7, 5)

        self.assertEqual(calls, ["paint", "split", "resolution"])
        self.assertEqual(editor.backend.resolution, (7, 5))

    def test_cli_adapter_routes_edit_through_command_api(self) -> None:
        import pixel_cli
        project = self.root / "adapter.json"
        PixelCommandAPI.new(4, layered=True).save(project)
        calls: list[tuple[int, int]] = []
        original = PixelCommandAPI.paint

        def spy(api, x, y, color, **kwargs):
            calls.append((int(x), int(y)))
            return original(api, x, y, color, **kwargs)

        with patch.object(pixel_cli.PixelCommandAPI, "paint", spy):
            self.assertEqual(
                pixel_cli.main([
                    "edit", "--project", str(project),
                    "--paint", "2", "1", "#FF0000",
                ]),
                0,
            )
        self.assertEqual(calls, [(2, 1)])
        self.assertEqual(load_project(project).sample(2, 1), RED)

    def test_required_cui_roundtrip_scenario(self) -> None:
        project = self.root / "scenario.json"
        output = self.root / "scenario.png"
        self.cli("new", "--size", 16, "--layered", "--output", project)
        self.cli(
            "edit", "--project", project,
            "--split", 0, 0,
            "--paint-child", 0, 0, 1, 1, "#FF0000",
        )
        self.cli(
            "edit", "--project", project,
            "--split", 15, 15,
            "--paint-child", 15, 15, 1, 1, "#00FF00",
        )
        self.cli("edit", "--project", project, "--resolution", 7, 7)
        report = json.loads(
            self.cli("inspect", "--project", project).stdout
        )
        self.assertEqual(report["resolution"], [7, 7])
        self.assertTrue(report["has_detail"])

        self.cli("edit", "--project", project, "--resolution", 23, 17)
        report = json.loads(
            self.cli("inspect", "--project", project).stdout
        )
        self.assertEqual(report["resolution"], [23, 17])

        self.cli("edit", "--project", project, "--resolution", 7, 7)
        self.cli("edit", "--project", project, "--discard-detail", 0, 0)
        self.cli("edit", "--project", project, "--resolution", 16, 16)

        model = load_project(project)
        self.assertFalse(model.has_detail_at(0, 0))
        self.assertTrue(model.has_detail_at(15, 15))
        self.assertEqual(model.sample(0, 0), (0, 0, 0, 0))
        self.assertEqual(model.sample(15, 15, (1, 1)), GREEN)

        copied = self.root / "copy.json"
        PixelCommandAPI(model).save(copied)
        self.assertEqual(load_project(copied).to_source(), model.to_source())
        self.cli("export", "--project", copied, "--output", output)
        with Image.open(output) as image:
            self.assertEqual(image.size, (32, 32))
            self.assertEqual(image.getpixel((31, 31)), GREEN)

    def test_invalid_command_inputs_do_not_mutate_document(self) -> None:
        api = PixelCommandAPI.new(4, layered=True)
        before = api.canvas.to_source()
        for operation in (
            lambda: api.paint(4, 0, RED),
            lambda: api.split_region(3, 3, 2, 2),
            lambda: api.discard_detail(0, 0, 0, 1),
            lambda: api.inspect_sample(0, 0, layer="missing"),
        ):
            with self.subTest(operation=operation):
                with self.assertRaises((ValueError, IndexError, KeyError)):
                    operation()
                self.assertEqual(api.canvas.to_source(), before)


if __name__ == "__main__":
    unittest.main()
