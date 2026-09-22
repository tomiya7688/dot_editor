"""Non-destructive resolution, serialization, CLI and GUI regression tests."""
from __future__ import annotations

import copy
from fractions import Fraction
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
from pixel_cli import load_project, save_project
from pixel_layers import LayeredPixelCanvas
from resolution_field import ResolutionField, cell_box

ROOT = Path(__file__).resolve().parent


class ResolutionTests(unittest.TestCase):
    def patterned(self, width=16, height=None):
        height = width if height is None else height
        image = Image.new("RGBA", (width, height))
        image.putdata([(70 + x % 40, 90 + y % 40, 110 + (x + y) % 40, 150 + (x * y) % 70)
                       for y in range(height) for x in range(width)])
        model = PixelCanvas(width, height)
        model.import_image(image)
        return model, image

    def cli(self, *arguments, code=0):
        result = subprocess.run([sys.executable, str(ROOT / "pixel_cli.py"), *map(str, arguments)],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                encoding="utf-8", timeout=30,
                                env={**os.environ, "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1"})
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        return result

    def fake_editor(self, backend=None):
        from dot_editor import PixelEditor
        editor = PixelEditor.__new__(PixelEditor)
        editor.backend = LayeredPixelCanvas(16) if backend is None else backend
        editor.num_pixels_x, editor.num_pixels_y = editor.backend.resolution
        editor.canvas_width, editor.canvas_height = 640, 480
        editor.zoom_factor = 1.0
        editor.canvas = Mock()
        editor.canvas.canvasx.side_effect = lambda x: x
        editor.canvas.canvasy.side_effect = lambda y: y
        editor.history, editor.future = [], []
        editor.selected_cell = None
        editor.tool = "brush"
        editor.current_color = (255, 128, 64)
        editor.create_grid = lambda: None
        editor.update_canvas = lambda: None
        editor.refresh_layer_list = lambda: None
        editor.update_canvas_size()
        return editor

    def test_arbitrary_resolution_roundtrip(self):
        model, image = self.patterned()
        before = model.to_source()
        for shape in ((7, 7), (23, 17), (1, 31), (31, 1), (16, 16)):
            model.set_resolution(*shape)
        self.assertEqual(model.image.tobytes(), image.tobytes())
        self.assertEqual(model.to_source(), before)

    def test_rectangular_roundtrip(self):
        model, _ = self.patterned(23, 17)
        before = model.to_source()
        for shape in ((7, 5), (41, 13), (23, 17)):
            model.set_resolution(*shape)
        self.assertEqual(model.to_source(), before)

    def test_downscale_without_data_loss(self):
        model = PixelCanvas(16)
        model.paint(0, 0, (255, 0, 0, 255))  # Not sampled by a 1x1 view.
        field = model.to_source()["retained_field"]
        model.set_resolution(1)
        self.assertEqual(model.sample(0, 0), (0, 0, 0, 0))
        self.assertTrue(model.has_detail)
        self.assertEqual(model.to_source()["retained_field"], field)
        model.set_resolution(16)
        self.assertEqual(model.sample(0, 0), (255, 0, 0, 255))

    def test_fine_edits_on_unaligned_grid_survive_roundtrip(self):
        model, _ = self.patterned()
        model.set_resolution(23, 17)
        self.assertTrue(model.paint(22, 16, (23, 45, 67, 255), detail_policy="discard"))
        before = model.to_source()
        model.set_resolution(7)
        model.set_resolution(16)
        model.set_resolution(23, 17)
        self.assertEqual(model.to_source(), before)
        self.assertEqual(model.sample(22, 16), (23, 45, 67, 255))

    def test_coarse_edit_preserves_detail(self):
        model, original = self.patterned()
        model.set_resolution(7)
        base = model.sample(2, 3)
        replacement = (120, 130, 140, 200)
        delta = tuple(n - o for n, o in zip(replacement, base))
        self.assertTrue(model.paint(2, 3, replacement))
        self.assertEqual(model.sample(2, 3), replacement)
        self.assertTrue(model.has_detail_at(2, 3))
        model.set_resolution(16)
        for y in range(16):
            for x in range(16):
                inside = 2 <= Fraction(2*x+1, 32)*7 < 3 and 3 <= Fraction(2*y+1, 32)*7 < 4
                expected = original.getpixel((x, y))
                if inside:
                    expected = tuple(c+d for c, d in zip(expected, delta))
                self.assertEqual(model.sample(x, y), expected, (x, y))

    def test_coarse_edit_retains_unclipped_samples(self):
        image = Image.new("RGBA", (16, 16))
        image.putdata([(240+x, 80+y, 100, 255) for y in range(16) for x in range(16)])
        model = PixelCanvas(16)
        model.import_image(image)
        model.set_resolution(7)
        anchor = model.sample(1, 1)
        model.paint(1, 1, (255, 100, 120, 255))
        model = PixelCanvas.from_source(model.to_source())
        model.paint(1, 1, (200, 100, 120, 255))
        self.assertEqual(model.sample(1, 1), (200, 100, 120, 255))
        model.set_resolution(16)
        for x in (2, 3, 4):
            self.assertEqual(model.sample(x, 3)[0], image.getpixel((x, 3))[0]+200-anchor[0])

    def test_coarse_edit_discards_detail(self):
        model, original = self.patterned()
        model.set_resolution(7)
        replacement = (23, 45, 67, 255)
        model.paint(1, 1, replacement, detail_policy="discard")
        self.assertFalse(model.has_detail_at(1, 1))
        model.set_resolution(16)
        for y in range(16):
            for x in range(16):
                inside = 1 <= Fraction(2*x+1, 32)*7 < 2 and 1 <= Fraction(2*y+1, 32)*7 < 2
                self.assertEqual(model.sample(x, y), replacement if inside else original.getpixel((x, y)))

    def test_discard_detail_is_local(self):
        model, _ = self.patterned()
        model.set_resolution(7)
        reference = model.render_resolution(79, 53)
        coarse = model.image
        self.assertEqual(model.discard_detail(1, 2, 2, 1), 2)
        result = model.render_resolution(79, 53)
        for y in range(53):
            for x in range(79):
                gx, gy = Fraction(2*x+1, 2*79)*7, Fraction(2*y+1, 2*53)*7
                expected = coarse.getpixel((int(gx), int(gy))) if 1 <= gx < 3 and 2 <= gy < 3 else reference.getpixel((x, y))
                self.assertEqual(result.getpixel((x, y)), expected)

    def test_undo_restores_discarded_detail(self):
        model, _ = self.patterned()
        model.set_resolution(7)
        before = model.to_source()
        model.discard_detail(1, 1, 2, 2)
        after = model.to_source()
        self.assertNotEqual(before, after)
        self.assertTrue(model.undo())
        self.assertEqual(model.to_source(), before)
        self.assertTrue(model.redo())
        self.assertEqual(model.to_source(), after)
        self.assertEqual(model.discard_detail(1, 1, 2, 2), 0)

    def test_global_discard_is_explicit_and_undoable(self):
        model, image = self.patterned()
        before = model.to_source()
        model.set_resolution(7, detail_policy="discard")
        self.assertFalse(model.has_detail)
        self.assertEqual(model.retained_resolution, (7, 7))
        model.set_resolution(16)
        self.assertNotEqual(model.image.tobytes(), image.tobytes())
        self.assertTrue(model.undo())
        self.assertTrue(model.undo())
        self.assertEqual(model.to_source(), before)

    def test_split_collapse_global_roundtrip(self):
        for expanded in (False, True):
            with self.subTest(expanded=expanded):
                model = PixelCanvas(4)
                model.paint(1, 1, (255, 0, 0, 255))
                model.split_cell(1, 1)
                model.paint(1, 1, (0, 0, 255, 128), child=(1, 0))
                model.paint(1, 1, (0, 255, 0, 255))
                if not expanded:
                    model.collapse_cell(1, 1)
                before = model.to_source()
                model.set_resolution(7, 3)
                model.set_resolution(23, 17)
                model = PixelCanvas.from_source(model.to_source())
                model.set_resolution(4)
                self.assertEqual(model.to_source(), before)
                self.assertEqual(model.sample(1, 1, (1, 0)), (0, 0, 255, 128))

    def test_split_at_another_grid_restores_its_own_metadata(self):
        model, _ = self.patterned()
        model.set_resolution(7)
        model.split_cell(3, 2)
        model.paint(3, 2, (12, 34, 56, 255), child=(1, 0), detail_policy="discard")
        before = model.to_source()
        model.set_resolution(23, 17)
        model.set_resolution(7)
        self.assertEqual(model.to_source(), before)

    def test_save_load_preserves_resolution_history(self):
        model, image = self.patterned()
        model.set_resolution(7)
        model.set_resolution(23, 17)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"p.json"
            save_project(model, p)
            restored = load_project(p)
            restored.set_resolution(16)
            self.assertEqual(restored.image.tobytes(), image.tobytes())

    def test_layer_resolution_change_is_atomic_and_undoable(self):
        layers = LayeredPixelCanvas(16)
        layers.paint(1, 1, (12, 34, 56, 255))
        layers.add_layer("人物")
        layers.paint(14, 13, (23, 45, 67, 128))
        before = layers.to_source()
        layers.set_resolution(23, 17)
        self.assertEqual({c.resolution for c in layers.layers.values()}, {(23, 17)})
        self.assertEqual(layers.active_layer, "人物")
        self.assertTrue(layers.undo())
        self.assertEqual(layers.to_source(), before)
        self.assertTrue(layers.redo())
        self.assertEqual(layers.resolution, (23, 17))
        layers.set_resolution(16)
        self.assertEqual(layers.to_source(), before)

    def test_failed_layer_resize_keeps_all_layers_and_history(self):
        layers = LayeredPixelCanvas(16)
        layers.add_layer("人物")
        before = layers.to_source()
        history = len(layers._history)
        original = PixelCanvas.set_resolution
        calls = 0
        def fail_second(canvas, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError("simulated allocation limit")
            return original(canvas, *args, **kwargs)
        with patch.object(PixelCanvas, "set_resolution", fail_second):
            with self.assertRaises(ValueError):
                layers.set_resolution(7, detail_policy="discard")
        self.assertEqual(layers.to_source(), before)
        self.assertEqual(len(layers._history), history)

    def test_discard_is_local_to_active_layer(self):
        layers = LayeredPixelCanvas(16)
        layers.layers["背景"] = self.patterned()[0]
        layers.add_layer("人物")
        layers.active.import_image(self.patterned()[1])
        layers.set_resolution(7)
        background = layers.layers["背景"].to_source()
        layers.discard_detail(1, 1)
        self.assertEqual(layers.layers["背景"].to_source(), background)

    def test_invalid_resolution_leaves_history_and_future_unchanged(self):
        model, _ = self.patterned()
        model.paint(0, 0, (11, 22, 33, 255))
        model.undo()
        before = model.to_source()
        history, future = len(model._history), len(model._future)
        for dims in ((0, 1), (-1, 1), (True, 2), (3.0, 2), (4097, 1), (4096, 4096)):
            with self.subTest(dims=dims), self.assertRaises(ValueError):
                model.set_resolution(*dims)
        self.assertEqual(model.to_source(), before)
        self.assertEqual((len(model._history), len(model._future)), (history, future))
        self.assertFalse(model.set_resolution(16))
        self.assertEqual(len(model._future), future)

    def test_safe_dimension_limit_is_not_a_preset_limit(self):
        for dims in ((1, 1), (3, 5), (7, 7), (23, 17), (4096, 1), (1, 4096)):
            with self.subTest(dims=dims):
                self.assertEqual(PixelCanvas(*dims).resolution, dims)

    def test_rgba_roundtrip_including_hidden_transparent_rgb(self):
        model = PixelCanvas(3, 2)
        for x, c in enumerate(((1, 2, 3, 0), (4, 5, 6, 128), (7, 8, 9, 255))):
            model.paint(x, 1, c)
        restored = PixelCanvas.from_source(model.to_source())
        restored.set_resolution(1)
        restored.set_resolution(3, 2)
        self.assertEqual(restored.to_source(), model.to_source())

    def test_legacy_project_migrates_and_retains_children(self):
        old = {"canvas_size": 2, "pixels": [["#FF0000", None], [None, None]],
               "refined_cells": [{"x": 0, "y": 0, "expanded": False,
                                  "children": [["#FF0000", "#0000FF"], [None, "#FF0000"]]}]}
        model = PixelCanvas.from_source(old)
        model.set_resolution(7, 3)
        model = PixelCanvas.from_source(model.to_source())
        model.set_resolution(2)
        self.assertFalse(model.is_split(0, 0))
        self.assertEqual(model.sample(0, 0, (1, 0)), (0, 0, 255, 255))

    def test_invalid_v2_is_rejected(self):
        model, _ = self.patterned()
        source = model.to_source()
        variants = []
        value = copy.deepcopy(source); value["version"] = 99; variants.append(value)
        value = copy.deepcopy(source); value["resolution"] = [True, 16]; variants.append(value)
        value = copy.deepcopy(source); value["pixels"][0][0] = None; variants.append(value)
        value = copy.deepcopy(source); value["retained_field"][0]["offset"][0] = 1_000_001; variants.append(value)
        value = copy.deepcopy(source); value["retained_field"][0]["clip"][0] = [0, 0]; variants.append(value)
        value = copy.deepcopy(source); value["retained_field"].append(value["retained_field"][0]); variants.append(value)
        for value in variants:
            with self.subTest(value=value.get("version")), self.assertRaises(ValueError):
                PixelCanvas.from_source(value)

    def test_overlapping_patches_with_equal_total_area_rejected(self):
        model = PixelCanvas(2)
        model.paint(0, 0, (1, 2, 3, 255))
        source = model.to_source()
        tile = copy.deepcopy(source["retained_field"][0])
        tile["clip"] = [[0, 1], [0, 1], [1, 1], [1, 2]]
        tile["extent"] = copy.deepcopy(tile["clip"])
        with self.assertRaises(ValueError):
            ResolutionField.from_source([tile, tile])

    def test_cli_complete_non_interactive_scenario(self):
        with tempfile.TemporaryDirectory() as d:
            path, output = Path(d)/"art.json", Path(d)/"out.png"
            self.cli("new", "--size", 16, "--layered", "--output", path)
            for x, y, color in ((2, 2, "#FF0000"), (3, 3, "#0000FF"), (14, 14, "#00FF00")):
                self.cli("edit", "--project", path, "--paint", x, y, color)
            before = load_project(path).to_source()
            self.cli("edit", "--project", path, "--resolution", 7, 7)
            self.cli("edit", "--project", path, "--resolution", 23, 17)
            report = json.loads(self.cli("inspect", "--project", path).stdout)
            self.assertEqual(report["resolution"], [23, 17])
            self.cli("edit", "--project", path, "--resolution", 16, 16)
            self.assertEqual(load_project(path).to_source(), before)
            self.cli("edit", "--project", path, "--resolution", 7, 7)
            self.cli("edit", "--project", path, "--discard-detail", 1, 1)
            self.cli("edit", "--project", path, "--resolution", 16, 16)
            actual = load_project(path)
            self.assertEqual(actual.sample(2, 2), (0, 0, 255, 255))
            self.assertEqual(actual.sample(14, 14), (0, 255, 0, 255))
            self.cli("export", "--project", path, "--output", output, "--resolution", 23, 17)
            with Image.open(output) as image:
                self.assertEqual(image.size, (23, 17))
                self.assertEqual(image.tobytes(), actual.render_resolution(23, 17).tobytes())

    def test_cli_preserve_and_discard_match_backend(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"art.json"
            for policy in ("preserve", "discard"):
                model, _ = self.patterned()
                model.set_resolution(7)
                save_project(model, path)
                expected = PixelCanvas.from_source(model.to_source())
                expected.paint(1, 2, (120, 130, 140, 255), detail_policy=policy)
                self.cli("edit", "--project", path, "--paint", 1, 2, "#78828C", "--detail-policy", policy)
                self.assertEqual(load_project(path).to_source(), expected.to_source())

    def test_cli_rectangular_new_and_bounds(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"art.json"
            self.cli("new", "--resolution", 3, 5, "--output", path)
            self.cli("edit", "--project", path, "--paint", 2, 4, "#123456")
            self.assertEqual(load_project(path).sample(2, 4), (18, 52, 86, 255))
            before = path.read_bytes()
            self.cli("edit", "--project", path, "--paint", 3, 4, "#123456", code=2)
            self.cli("edit", "--project", path, "--paint", 2, 5, "#123456", code=2)
            self.assertEqual(path.read_bytes(), before)

    def test_cli_invalid_following_edit_does_not_save_resolution_change(self):
        with tempfile.TemporaryDirectory() as d:
            path, output = Path(d)/"art.json", Path(d)/"out.json"
            save_project(self.patterned()[0], path)
            before = path.read_bytes()
            output.write_text("keep", encoding="utf-8")
            self.cli("edit", "--project", path, "--resolution", 7, 7,
                     "--paint", 7, 0, "#FFFFFF", "--output", output, code=2)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(output.read_text(), "keep")
            self.cli("edit", "--project", path, "--resolution", 16, 16)
            self.assertEqual(path.read_bytes(), before)

    def test_cli_export_resolution_is_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            path, output = Path(d)/"art.json", Path(d)/"out.png"
            model, original = self.patterned()
            model.set_resolution(7)
            save_project(model, path)
            before = path.read_bytes()
            self.cli("export", "--project", path, "--resolution", 16, 16, "--output", output)
            with Image.open(output) as image:
                self.assertEqual(image.tobytes(), original.tobytes())
            self.assertEqual(path.read_bytes(), before)

    def test_gui_rectangle_pointer_maps_bottom_right(self):
        editor = self.fake_editor(LayeredPixelCanvas(23, 17))
        editor.paint_pixel(SimpleNamespace(x=639, y=479))
        self.assertEqual(editor.backend.sample(22, 16), (255, 128, 64, 255))
        before = editor.backend.to_source()
        editor.paint_pixel(SimpleNamespace(x=-1, y=0))
        editor.paint_pixel(SimpleNamespace(x=640, y=480))
        self.assertEqual(editor.backend.to_source(), before)

    def test_gui_pointer_after_zoom_and_pan(self):
        editor = self.fake_editor(LayeredPixelCanvas(23, 17))
        editor.zoom_factor = 2
        editor.canvas.canvasx.side_effect = lambda x: x+1000
        editor.canvas.canvasy.side_effect = lambda y: y+800
        editor.paint_pixel(SimpleNamespace(x=279, y=159))
        self.assertEqual(editor.backend.sample(22, 16), (255, 128, 64, 255))

    def test_gui_resolution_larger_than_display_does_not_divide_by_zero(self):
        editor = self.fake_editor(LayeredPixelCanvas(1001, 17))
        editor.set_display_size(100, 100)
        editor.paint_pixel(SimpleNamespace(x=99, y=99))
        self.assertEqual(editor.backend.sample(990, 16), (255, 128, 64, 255))

    def test_gui_resolution_roundtrip_and_undo(self):
        editor = self.fake_editor()
        editor.backend.active.import_image(self.patterned()[1])
        before = editor.backend.to_source()
        editor.resize_logical_canvas(7)
        editor.resize_logical_canvas(23, 17)
        self.assertEqual((editor.num_pixels_x, editor.num_pixels_y), (23, 17))
        editor.undo()
        self.assertEqual(editor.backend.resolution, (7, 7))
        editor.undo()
        self.assertEqual(editor.backend.to_source(), before)
        editor.redo()
        self.assertEqual(editor.backend.resolution, (7, 7))
        editor.resize_logical_canvas(16)
        self.assertEqual(editor.backend.to_source(), before)

    def test_gui_policy_is_passed_to_backend(self):
        for policy in ("preserve", "discard"):
            editor = self.fake_editor()
            editor.backend.active.import_image(self.patterned()[1])
            editor.resize_logical_canvas(7)
            editor.detail_policy = SimpleNamespace(get=lambda: policy)
            expected = LayeredPixelCanvas.from_source(editor.backend.to_source())
            expected.paint(1, 1, (255, 128, 64, 255), detail_policy=policy)
            editor.paint_pixel(SimpleNamespace(x=100, y=100))
            self.assertEqual(editor.backend.to_source(), expected.to_source())

    def test_gui_and_cli_project_roundtrip(self):
        from dot_editor import filedialog
        editor = self.fake_editor(LayeredPixelCanvas(23, 17))
        editor.backend.paint(22, 16, (12, 34, 56, 128))
        editor.backend.split_cell(22, 16)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"art.json"
            with patch.object(filedialog, "asksaveasfilename", return_value=str(path)):
                editor.save_project()
            self.assertEqual(load_project(path).to_source(), editor.backend.to_source())
            self.cli("edit", "--project", path, "--resolution", 7, 5)
            with patch.object(filedialog, "askopenfilename", return_value=str(path)):
                editor.load_project()
            self.assertEqual((editor.num_pixels_x, editor.num_pixels_y), (7, 5))
            editor.resize_logical_canvas(23, 17)
            self.assertTrue(editor.backend.is_split(22, 16))
            self.assertEqual(editor.backend.sample(22, 16, (0, 0)), (12, 34, 56, 128))

    def test_display_resize_does_not_change_document_or_history(self):
        editor = self.fake_editor(LayeredPixelCanvas(23, 17))
        editor.backend.paint(3, 2, (12, 34, 56, 255))
        before = editor.backend.to_source()
        backend = editor.backend
        editor.future.append("sentinel")
        editor.set_display_size(800, 300)
        self.assertIs(editor.backend, backend)
        self.assertEqual(editor.backend.to_source(), before)
        self.assertEqual(editor.future, ["sentinel"])

    def test_optional_compaction_is_lossless(self):
        model, _ = self.patterned()
        expected, _ = self.patterned()
        expected.paint(1, 1, (12, 34, 56, 255), detail_policy="discard")
        with patch("resolution_field.MAX_TILES", 1):
            model.paint(1, 1, (12, 34, 56, 255), detail_policy="discard")
        self.assertEqual(model.retained_patch_count, 1)
        self.assertEqual(model.render_resolution(37, 31).tobytes(), expected.render_resolution(37, 31).tobytes())

    def test_field_rejects_resource_limit_without_partial_mutation(self):
        model, _ = self.patterned()
        model.set_resolution(7)
        before = model.to_source()
        with patch.object(ResolutionField, "_checked", side_effect=ValueError("simulated patch budget")):
            with self.assertRaises(ValueError):
                model.paint(1, 1, (12, 34, 56, 255))
        self.assertEqual(model.to_source(), before)


if __name__ == "__main__":
    unittest.main()
