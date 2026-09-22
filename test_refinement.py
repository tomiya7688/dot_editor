"""Issue #3: refinement isolation across resolution, persistence and history."""
from __future__ import annotations

from fractions import Fraction
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from pixel_backend import PixelCanvas
from pixel_layers import LayeredPixelCanvas
from resolution_field import ResolutionField

CHILDREN = ((0, 0), (1, 0), (0, 1), (1, 1))
CLEAR = (0, 0, 0, 0)
RED = (180, 40, 50, 255)
BLUE = (40, 60, 180, 128)


def patterned_canvas() -> PixelCanvas:
    image = Image.new("RGBA", (16, 12))
    image.putdata([(60 + 2*x, 80 + 3*y, 100 + x + y, 200)
                   for y in range(12) for x in range(16)])
    canvas = PixelCanvas(16, 12)
    canvas.import_image(image)
    canvas.set_resolution(4, 3)
    canvas.split_cell(1, 1)
    return canvas


def reload_canvas(canvas: PixelCanvas) -> PixelCanvas:
    return PixelCanvas.from_source(json.loads(json.dumps(canvas.to_source())))


def metadata_canvas(expanded: bool = False, point=(0, 0), size=16) -> PixelCanvas:
    # The field is transparent; the only colored data is the retained parent.
    canvas = PixelCanvas(size)
    canvas.split_cell(*point)
    canvas.paint(*point, RED)
    if not expanded:
        canvas.collapse_cell(*point)
    return canvas


class RefinementTests(unittest.TestCase):
    def test_child_paint_keeps_parent_in_all_quadrants_and_policies(self):
        for policy in ("preserve", "discard"):
            for child in CHILDREN:
                with self.subTest(policy=policy, child=child):
                    canvas = patterned_canvas()
                    parent = canvas.sample(1, 1)
                    before = canvas.to_source()  # Also warm the projection cache.
                    siblings = {p: canvas.sample(1, 1, p) for p in CHILDREN}
                    self.assertTrue(canvas.paint(1, 1, BLUE, child=child, detail_policy=policy))
                    self.assertEqual(canvas.sample(1, 1), parent)
                    self.assertEqual(canvas.image.getpixel((1, 1)), parent)
                    self.assertEqual(canvas.sample(1, 1, child), BLUE)
                    for other in CHILDREN:
                        if other != child:
                            self.assertEqual(canvas.sample(1, 1, other), siblings[other])
                    after = canvas.to_source()
                    self.assertTrue(canvas.undo())
                    self.assertEqual(canvas.to_source(), before)
                    self.assertTrue(canvas.redo())
                    self.assertEqual(canvas.to_source(), after)
                    canvas = reload_canvas(canvas)
                    canvas.collapse_cell(1, 1)
                    self.assertEqual(canvas.render().getpixel((1, 1)), parent)
                    canvas.set_resolution(7, 5)
                    canvas.set_resolution(23, 17)
                    canvas = reload_canvas(canvas)
                    canvas.set_resolution(4, 3)
                    canvas.split_cell(1, 1)
                    self.assertEqual(canvas.sample(1, 1), parent)
                    self.assertEqual(canvas.sample(1, 1, child), BLUE)
                    self.assertEqual(canvas.to_source(), after)

    def test_child_erase_keeps_parent_in_all_quadrants_and_policies(self):
        for policy in ("preserve", "discard"):
            for child in CHILDREN:
                with self.subTest(policy=policy, child=child):
                    canvas = patterned_canvas()
                    parent = canvas.sample(1, 1)
                    siblings = {p: canvas.sample(1, 1, p) for p in CHILDREN}
                    canvas.paint(1, 1, CLEAR, erase=True, child=child, detail_policy=policy)
                    self.assertEqual(canvas.sample(1, 1), parent)
                    self.assertEqual(canvas.sample(1, 1, child), CLEAR)
                    for other in CHILDREN:
                        if other != child:
                            self.assertEqual(canvas.sample(1, 1, other), siblings[other])
                    canvas = reload_canvas(canvas)
                    canvas.collapse_cell(1, 1)
                    self.assertEqual(canvas.render().getpixel((1, 1)), parent)
                    canvas.split_cell(1, 1)
                    self.assertEqual(canvas.sample(1, 1, child), CLEAR)

    def test_child_edit_without_finer_field_keeps_parent(self):
        for policy in ("preserve", "discard"):
            canvas = PixelCanvas(4)
            canvas.paint(1, 1, RED)
            canvas.split_cell(1, 1)
            canvas.paint(1, 1, BLUE, child=(1, 1), detail_policy=policy)
            self.assertEqual(canvas.sample(1, 1), RED)
            self.assertEqual(canvas.sample(1, 1, (1, 1)), BLUE)

    def test_child_edits_do_not_touch_spatial_exterior(self):
        for policy in ("preserve", "discard"):
            canvas = patterned_canvas()
            reference = canvas.render_resolution(73, 61)
            canvas.paint(1, 1, BLUE, child=(1, 1), detail_policy=policy)
            result = canvas.render_resolution(73, 61)
            for y in range(61):
                for x in range(73):
                    px, py = Fraction(2*x+1, 146), Fraction(2*y+1, 122)
                    inside = Fraction(3, 8) <= px < Fraction(1, 2) and Fraction(1, 2) <= py < Fraction(2, 3)
                    if not inside:
                        self.assertEqual(result.getpixel((x, y)), reference.getpixel((x, y)))

    def test_parent_preserve_still_keeps_independent_children(self):
        canvas = patterned_canvas()
        field = canvas.to_source()["retained_field"]
        children = [canvas.sample(1, 1, p) for p in CHILDREN]
        canvas.paint(1, 1, RED)
        self.assertEqual(canvas.sample(1, 1), RED)
        self.assertEqual([canvas.sample(1, 1, p) for p in CHILDREN], children)
        self.assertEqual(canvas.to_source()["retained_field"], field)
        canvas = reload_canvas(canvas)
        canvas.set_resolution(23, 17)
        canvas.set_resolution(4, 3)
        self.assertEqual(canvas.sample(1, 1), RED)
        self.assertEqual([canvas.sample(1, 1, p) for p in CHILDREN], children)

    def test_other_grid_coarse_edit_still_updates_retained_bases(self):
        canvas = patterned_canvas()
        parent = canvas.sample(1, 1)
        canvas.set_resolution(2, 1)
        anchor = canvas.sample(0, 0)
        replacement = tuple(v+5 if i < 3 else v for i, v in enumerate(anchor))
        canvas.paint(0, 0, replacement)
        canvas.set_resolution(4, 3)
        self.assertEqual(canvas.sample(1, 1), tuple(v+5 if i < 3 else v for i, v in enumerate(parent)))

    def test_cross_grid_discard_detects_parent_only_detail(self):
        for expanded in (False, True):
            with self.subTest(expanded=expanded):
                canvas = metadata_canvas(expanded)
                canvas.split_cell(15, 15)
                canvas.paint(15, 15, BLUE)
                canvas.collapse_cell(15, 15)
                canvas.set_resolution(7)
                before = canvas.to_source()
                self.assertTrue(canvas.has_detail_at(0, 0))
                self.assertEqual(canvas.discard_detail(0, 0), 1)
                after = canvas.to_source()
                self.assertFalse(canvas.has_detail_at(0, 0))
                self.assertEqual(canvas.discard_detail(0, 0), 0)
                self.assertTrue(canvas.undo())
                self.assertEqual(canvas.to_source(), before)
                self.assertTrue(canvas.redo())
                self.assertEqual(canvas.to_source(), after)
                canvas = reload_canvas(canvas)
                canvas.set_resolution(16)
                self.assertEqual(canvas.sample(0, 0), CLEAR)
                self.assertFalse(canvas.has_detail_at(0, 0))
                self.assertEqual(canvas.sample(15, 15), BLUE)
                canvas.split_cell(0, 0)
                for child in CHILDREN:
                    self.assertEqual(canvas.sample(0, 0, child), CLEAR)

    def test_cross_grid_same_color_discard_paint_is_not_noop(self):
        canvas = metadata_canvas()
        canvas.set_resolution(7)
        self.assertTrue(canvas.paint(0, 0, CLEAR, detail_policy="discard"))
        self.assertFalse(canvas.paint(0, 0, CLEAR, detail_policy="discard"))
        canvas.set_resolution(16)
        self.assertEqual(canvas.sample(0, 0), CLEAR)
        self.assertEqual(canvas.to_source()["retained_splits"], [])

    def test_cross_grid_same_color_discard_fill_is_not_noop(self):
        canvas = metadata_canvas()
        canvas.set_resolution(7)
        before = canvas.to_source()
        self.assertEqual(canvas.fill(0, 0, CLEAR, detail_policy="discard"), 1)
        self.assertEqual(canvas.fill(0, 0, CLEAR, detail_policy="discard"), 0)
        self.assertTrue(canvas.undo())
        self.assertEqual(canvas.to_source(), before)
        self.assertTrue(canvas.redo())
        canvas.set_resolution(16)
        self.assertEqual(canvas.sample(0, 0), CLEAR)
        self.assertEqual(canvas.to_source()["retained_splits"], [])

    def test_cross_grid_discard_removes_contained_unpainted_split(self):
        canvas = PixelCanvas(16)
        canvas.split_cell(0, 0)
        canvas.set_resolution(7)
        self.assertEqual(canvas.discard_detail(0, 0), 1)
        canvas = reload_canvas(canvas)
        canvas.set_resolution(16)
        self.assertFalse(canvas.is_split(0, 0))
        self.assertEqual(canvas.to_source()["retained_splits"], [])

    def test_partial_metadata_overlap_updates_only_included_base(self):
        canvas = metadata_canvas(point=(2, 2))  # Center is inside cell (1,1) at 7x7.
        canvas.split_cell(1, 2)  # Its center is outside that target cell.
        canvas.paint(1, 2, BLUE)
        canvas.collapse_cell(1, 2)
        canvas.set_resolution(7)
        self.assertTrue(canvas.has_detail_at(1, 1))
        self.assertEqual(canvas.discard_detail(1, 1), 1)
        self.assertFalse(canvas.has_detail_at(1, 1))
        self.assertEqual(canvas.discard_detail(1, 1), 0)
        canvas = reload_canvas(canvas)
        canvas.set_resolution(16)
        self.assertEqual(canvas.sample(2, 2), CLEAR)
        self.assertEqual(canvas.sample(1, 2), BLUE)

    def test_metadata_discard_uses_half_open_sample_bounds(self):
        canvas = metadata_canvas(point=(1, 1), size=6)  # Center exactly (1/4,1/4).
        canvas.set_resolution(4)
        self.assertFalse(canvas.has_detail_at(0, 0))
        self.assertEqual(canvas.discard_detail(0, 0), 0)
        self.assertTrue(canvas.has_detail_at(1, 1))
        self.assertEqual(canvas.discard_detail(1, 1), 1)
        self.assertEqual(canvas.discard_detail(1, 1), 0)
        canvas.set_resolution(6)
        self.assertEqual(canvas.sample(1, 1), CLEAR)

    def test_discard_across_split_grids_preserves_exact_exterior(self):
        canvas = patterned_canvas()
        canvas.paint(1, 1, BLUE, child=(1, 1))
        canvas.set_resolution(7, 5)
        reference = canvas.render_resolution(73, 61)
        coarse = canvas.image
        before = canvas.to_source()
        canvas.discard_detail(1, 1, 2, 2)
        after = canvas.to_source()
        result = reload_canvas(canvas).render_resolution(73, 61)
        for y in range(61):
            for x in range(73):
                gx, gy = Fraction(2*x+1, 146)*7, Fraction(2*y+1, 122)*5
                inside = 1 <= gx < 3 and 1 <= gy < 3
                expected = coarse.getpixel((int(gx), int(gy))) if inside else reference.getpixel((x, y))
                self.assertEqual(result.getpixel((x, y)), expected)
        self.assertTrue(canvas.undo())
        self.assertEqual(canvas.to_source(), before)
        self.assertTrue(canvas.redo())
        self.assertEqual(canvas.to_source(), after)

    def test_failed_child_write_preserves_state_history_and_redo(self):
        for policy, method in (("preserve", "shift"), ("discard", "replace")):
            canvas = patterned_canvas()
            canvas.paint(0, 0, RED)
            canvas.undo()
            before = canvas.to_source()
            history, future = list(canvas._history), list(canvas._future)
            with patch.object(ResolutionField, method, side_effect=ValueError("budget exceeded")):
                with self.assertRaises(ValueError):
                    canvas.paint(1, 1, BLUE, child=(1, 1), detail_policy=policy)
            self.assertEqual(canvas.to_source(), before)
            self.assertEqual(canvas._history, history)
            self.assertEqual(canvas._future, future)
            self.assertTrue(canvas.redo())

    def test_read_only_views_and_child_noop_keep_history(self):
        canvas = patterned_canvas()
        before = canvas.to_source()
        history = len(canvas._history)
        for child in CHILDREN:
            self.assertFalse(canvas.paint(1, 1, canvas.sample(1, 1, child), child=child))
        canvas.image.putpixel((1, 1), RED)
        canvas.render()
        canvas.render_resolution(23, 17)
        self.assertEqual(canvas.to_source(), before)
        self.assertEqual(len(canvas._history), history)

    def test_legacy_refinement_migration_roundtrip(self):
        for expanded in (False, True):
            cell = {"x": 0, "y": 0, "children": [["#FF0000", "#0000FF80"], [None, "#00FF00"]]}
            if not expanded:
                cell["expanded"] = False
            canvas = PixelCanvas.from_source({"canvas_size": 2,
                "pixels": [["#112233", None], [None, None]], "refined_cells": [cell]})
            before = canvas.to_source()
            canvas.set_resolution(7, 5)
            canvas = reload_canvas(canvas)
            canvas.set_resolution(2)
            self.assertEqual(canvas.to_source(), before)
            self.assertEqual(canvas.sample(0, 0), (17, 34, 51, 255))
            self.assertEqual(canvas.sample(0, 0, (1, 0)), (0, 0, 255, 128))
            self.assertEqual(canvas.is_split(0, 0), expanded)

    def test_child_edit_layer_switch_save_load_and_png(self):
        canvas = LayeredPixelCanvas(4, 3)
        canvas.fill(0, 0, (20, 30, 40, 255))
        background = canvas.active.to_source()
        canvas.add_layer("人物")
        canvas.layers["人物"] = patterned_canvas()
        parent = canvas.sample(1, 1)
        before = canvas.to_source()
        canvas.paint(1, 1, BLUE, child=(1, 1))
        self.assertEqual(canvas.sample(1, 1), parent)
        after = canvas.to_source()
        self.assertTrue(canvas.undo())
        self.assertEqual(canvas.to_source(), before)
        self.assertTrue(canvas.redo())
        self.assertEqual(canvas.to_source(), after)
        rendered = canvas.composite()
        canvas.select_layer("背景")
        self.assertEqual(canvas.composite().tobytes(), rendered.tobytes())
        self.assertEqual(canvas.active.to_source(), background)
        canvas.set_resolution(7, 5)
        canvas.set_resolution(23, 17)
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)/"project.json"
            project.write_text(json.dumps(canvas.to_source(), ensure_ascii=False), encoding="utf-8")
            restored = LayeredPixelCanvas.from_source(json.loads(project.read_text(encoding="utf-8")))
            restored.set_resolution(4, 3)
            restored.select_layer("人物")
            self.assertEqual(restored.sample(1, 1), parent)
            self.assertEqual(restored.sample(1, 1, (1, 1)), BLUE)
            self.assertEqual(restored.layers["背景"].to_source(), background)
            self.assertEqual(restored.composite().tobytes(), rendered.tobytes())
            path = Path(directory)/"result.png"
            restored.save_png(path)
            with Image.open(path) as image:
                self.assertEqual(image.size, rendered.size)
                self.assertEqual(image.tobytes(), rendered.tobytes())
            restored.paint(1, 1, CLEAR, erase=True, child=(1, 1), detail_policy="discard")
            self.assertEqual(restored.composite().getpixel((3, 3)), (20, 30, 40, 255))
            self.assertEqual(restored.sample(1, 1), parent)

    def test_metadata_discard_is_layer_local_and_undoable(self):
        canvas = LayeredPixelCanvas(16)
        canvas.layers["背景"] = metadata_canvas()
        canvas.add_layer("人物")
        canvas.layers["人物"] = metadata_canvas()
        canvas.set_resolution(7)
        before = canvas.to_source()
        background = canvas.layers["背景"].to_source()
        self.assertEqual(canvas.discard_detail(0, 0), 1)
        self.assertEqual(canvas.layers["背景"].to_source(), background)
        after = canvas.to_source()
        self.assertTrue(canvas.undo())
        self.assertEqual(canvas.to_source(), before)
        self.assertTrue(canvas.redo())
        self.assertEqual(canvas.to_source(), after)
        canvas = LayeredPixelCanvas.from_source(json.loads(json.dumps(canvas.to_source())))
        canvas.set_resolution(16)
        self.assertEqual(canvas.sample(0, 0), CLEAR)
        canvas.select_layer("背景")
        self.assertEqual(canvas.sample(0, 0), RED)


    def fake_editor(self, backend):
        from dot_editor import PixelEditor
        editor = PixelEditor.__new__(PixelEditor)
        editor.backend = backend
        editor.num_pixels_x, editor.num_pixels_y = backend.resolution
        editor.canvas_width, editor.canvas_height = 640, 480
        editor.zoom_factor = 1.25
        editor.canvas = Mock()
        editor.canvas.canvasx.side_effect = lambda x: x + 60
        editor.canvas.canvasy.side_effect = lambda y: y + 40
        editor.history, editor.future = [], []
        editor.selected_cell = (1, 1)
        editor.tool = "brush"
        editor.current_color = (0, 0, 255)
        editor.current_detail_policy = lambda: "preserve"
        editor.create_grid = lambda: None
        editor.update_canvas = lambda: None
        editor.refresh_layer_list = lambda: None
        editor.report_error = lambda error: self.fail(str(error))
        editor.update_canvas_size()
        return editor

    def cli(self, *arguments):
        root = Path(__file__).resolve().parent
        result = subprocess.run(
            [sys.executable, str(root / "pixel_cli.py"), *map(str, arguments)],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", timeout=30,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        return result

    def test_gui_child_edit_recompose_history_and_cross_load(self):
        from pixel_cli import load_project
        for policy in ("preserve", "discard"):
            with self.subTest(policy=policy):
                layers = LayeredPixelCanvas(4, 3)
                layers.add_layer("人物")
                layers.layers["人物"] = patterned_canvas()
                parent = layers.sample(1, 1)
                editor = self.fake_editor(layers)
                editor.current_detail_policy = lambda: policy
                before = editor.backend.to_source()
                # Bottom-right child center, transformed through zoom and pan.
                editor.paint_pixel(SimpleNamespace(x=290, y=310))
                self.assertEqual(editor.backend.sample(1, 1, (1, 1)), (0, 0, 255, 255))
                self.assertEqual(editor.backend.sample(1, 1), parent)
                after = editor.backend.to_source()
                self.assertEqual(len(editor.history), 1)
                editor.undo()
                self.assertEqual(editor.backend.to_source(), before)
                editor.redo()
                self.assertEqual(editor.backend.to_source(), after)
                editor.selected_cell = (1, 1)
                editor.current_detail_policy = lambda: "preserve"
                editor.collapse_selected_cell()
                self.assertEqual(editor.backend.sample(1, 1), parent)
                editor.resize_logical_canvas(7, 5)
                editor.resize_logical_canvas(23, 17)
                saved = editor.backend.to_source()
                with tempfile.TemporaryDirectory() as directory:
                    project = Path(directory) / "gui.json"
                    with patch("dot_editor.filedialog.asksaveasfilename", return_value=str(project)):
                        editor.save_project()
                    loaded = load_project(project)
                    self.assertEqual(loaded.to_source(), saved)
                    with patch("dot_editor.filedialog.askopenfilename", return_value=str(project)):
                        editor.load_project()
                    editor.resize_logical_canvas(4, 3)
                    editor.selected_cell = (1, 1)
                    editor.split_selected_cell()
                    self.assertEqual(editor.backend.sample(1, 1), parent)
                    self.assertEqual(editor.backend.sample(1, 1, (1, 1)), (0, 0, 255, 255))
                    editor.refresh_composite()
                    self.assertEqual(editor.image.getpixel((280, 280)), (0, 0, 255, 255))

    def test_gui_cross_grid_discard_and_undo(self):
        layers = LayeredPixelCanvas(16)
        layers.layers["背景"] = metadata_canvas()
        editor = self.fake_editor(layers)
        editor.resize_logical_canvas(7)
        editor.selected_cell = (0, 0)
        before = editor.backend.to_source()
        history = len(editor.history)
        editor.discard_selected_detail()
        after = editor.backend.to_source()
        self.assertNotEqual(after, before)
        self.assertEqual(len(editor.history), history + 1)
        editor.discard_selected_detail()
        self.assertEqual(len(editor.history), history + 1)
        editor.undo()
        self.assertEqual(editor.backend.to_source(), before)
        editor.redo()
        self.assertEqual(editor.backend.to_source(), after)
        editor.resize_logical_canvas(16)
        self.assertEqual(editor.backend.sample(0, 0), CLEAR)

    def test_cli_child_parent_and_png_survive_resolution_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project, source, output = root/"art.json", root/"source.png", root/"art.png"
            Image.new("RGBA", (16, 12), (80, 100, 120, 255)).save(source)
            self.cli("new", "--resolution", 16, 12, "--output", project)
            self.cli("edit", "--project", project, "--import-image", source)
            self.cli("edit", "--project", project, "--resolution", 4, 3, "--split", 1, 1)
            self.cli("edit", "--project", project, "--paint-child", 1, 1, 1, 1, "#0000FF")
            report = json.loads(self.cli("inspect", "--project", project, "--sample", 1, 1).stdout)
            self.assertEqual(report["sample"]["rgba"], [80, 100, 120, 255])
            self.cli("edit", "--project", project, "--collapse", 1, 1)
            self.cli("edit", "--project", project, "--resolution", 7, 5)
            self.cli("edit", "--project", project, "--resolution", 23, 17)
            self.cli("edit", "--project", project, "--resolution", 4, 3, "--split", 1, 1)
            report = json.loads(self.cli("inspect", "--project", project, "--sample", 1, 1).stdout)
            self.assertEqual(report["sample"]["rgba"], [80, 100, 120, 255])
            self.cli("export", "--project", project, "--output", output)
            with Image.open(output) as image:
                self.assertEqual(image.size, (8, 6))
                self.assertEqual(image.getpixel((3, 3)), (0, 0, 255, 255))
                self.assertEqual(image.getpixel((2, 2)), (80, 100, 120, 255))

    def test_cli_discard_does_not_resurrect_hidden_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)/"art.json"
            self.cli("new", "--size", 16, "--output", project)
            # split precedes paint: the red value exists only in parent metadata.
            self.cli("edit", "--project", project, "--split", 0, 0,
                     "--paint", 0, 0, "#FF0000", "--collapse", 0, 0)
            self.cli("edit", "--project", project, "--split", 15, 15,
                     "--paint", 15, 15, "#0000FF", "--collapse", 15, 15)
            self.cli("edit", "--project", project, "--resolution", 7, 7)
            self.cli("edit", "--project", project, "--discard-detail", 0, 0)
            before = project.read_bytes(), project.stat().st_mtime_ns
            self.cli("edit", "--project", project, "--discard-detail", 0, 0)
            self.assertEqual((project.read_bytes(), project.stat().st_mtime_ns), before)
            self.cli("edit", "--project", project, "--resolution", 16, 16)
            report = json.loads(self.cli("inspect", "--project", project, "--sample", 0, 0).stdout)
            self.assertEqual(report["sample"]["rgba"], list(CLEAR))
            report = json.loads(self.cli("inspect", "--project", project, "--sample", 15, 15).stdout)
            self.assertEqual(report["sample"]["rgba"], [0, 0, 255, 255])


if __name__ == "__main__":
    unittest.main()
