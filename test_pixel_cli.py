"""Non-interactive CLI regressions: run with python test_pixel_cli.py."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from pixel_backend import PixelCanvas
from pixel_cli import load_project, save_project
from pixel_layers import LayeredPixelCanvas

ROOT = Path(__file__).resolve().parent
RED = (255, 0, 0, 255)
BLUE = (0, 0, 255, 255)
GREEN = (0, 255, 0, 255)


class PixelCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.project = self.root / "project.json"

    def run_cli(self, *arguments: object, code: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(ROOT / "pixel_cli.py"), *(str(a) for a in arguments)],
            cwd=self.root, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, encoding="utf-8", timeout=20,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1"},
        )
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        return result

    def edit(self, *arguments: object, code: int = 0) -> subprocess.CompletedProcess[str]:
        return self.run_cli("edit", "--project", self.project, *arguments, code=code)

    def report(self, *arguments: object) -> dict:
        return json.loads(self.run_cli("inspect", "--project", self.project, *arguments).stdout)

    def new(self, layered: bool = False) -> None:
        extra = ["--layered"] if layered else []
        self.run_cli("new", "--size", 4, "--output", self.project, *extra)

    def refined(self, layered: bool = False) -> None:
        self.new(layered)
        self.edit("--paint", 1, 1, "#FF0000")
        self.edit("--split", 1, 1, "--paint-child", 1, 1, 1, 0, "#0000FF")

    def signature(self) -> tuple[bytes, int]:
        return self.project.read_bytes(), self.project.stat().st_mtime_ns

    def test_inspect_new_flat_project(self) -> None:
        self.new()
        before = self.signature()
        report = self.report()
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["project_type"], "flat")
        self.assertEqual(report["resolution"], [4, 4])
        self.assertEqual(report["native_resolution"], [4, 4])
        self.assertIsNone(report["active_layer"])
        self.assertFalse(report["has_detail"])
        self.assertEqual(report["layers"][0]["detail_cells"], [])
        self.assertEqual(self.signature(), before)

    def test_collapse_save_reload_reexpand_and_export(self) -> None:
        self.refined()
        self.edit("--collapse", 1, 1)
        before = self.signature()
        report = self.report("--sample", 1, 1, "--child", 1, 0)
        self.assertEqual(report["sample"]["rgba"], list(BLUE))
        self.assertEqual(report["layers"][0]["collapsed_detail_cells"], 1)
        self.assertEqual(report["layers"][0]["expanded_cells"], 0)
        self.assertEqual(report["native_resolution"], [4, 4])
        self.assertTrue(report["has_detail"])
        self.assertFalse(report["has_refinements"])
        self.assertEqual(self.signature(), before)
        copied = self.root / "copied.json"
        self.edit("--collapse", 1, 1, "--output", copied)
        self.assertEqual(self.signature(), before)
        self.assertEqual(load_project(copied).to_source(), load_project(self.project).to_source())
        self.run_cli("edit", "--project", copied, "--split", 1, 1)
        image_path = self.root / "image.png"
        self.run_cli("export", "--project", copied, "--output", image_path)
        expected = PixelCanvas(4)
        expected.paint(1, 1, RED)
        expected.split_cell(1, 1)
        expected.paint(1, 1, BLUE, child=(1, 0))
        with Image.open(image_path) as image:
            self.assertEqual(image.size, (8, 8))
            self.assertEqual(image.tobytes(), expected.render().tobytes())
        self.assertEqual(load_project(copied).to_source(), expected.to_source())

    def test_layer_order_can_be_changed_and_exported(self) -> None:
        self.new(layered=True)
        self.edit("--paint", 0, 0, "#FF0000")
        self.edit("--add-layer", "人物", "--paint", 0, 0, "#0000FF")
        before = load_project(self.project)
        self.assertEqual(before.composite().getpixel((0, 0)), BLUE)

        self.edit("--select-layer", "背景", "--move-layer", "up")
        after = load_project(self.project)
        self.assertEqual(list(after.layers), ["人物", "背景"])
        self.assertEqual(after.composite().getpixel((0, 0)), RED)
        self.assertEqual(after.active_layer, "背景")

    def test_layer_visibility_persists_and_affects_export(self) -> None:
        self.new(layered=True)
        self.edit("--paint", 0, 0, "#FF0000")
        self.edit("--add-layer", "人物", "--paint", 0, 0, "#0000FF")
        self.edit("--layer-visibility", "hide")

        hidden = load_project(self.project)
        self.assertFalse(hidden.is_layer_visible("人物"))
        self.assertEqual(hidden.composite().getpixel((0, 0)), RED)
        report = self.report()
        self.assertFalse(report["layers"][1]["visible"])

        self.edit("--layer-visibility", "show")
        restored = load_project(self.project)
        self.assertTrue(restored.is_layer_visible("人物"))
        self.assertEqual(restored.composite().getpixel((0, 0)), BLUE)

    def test_parent_edit_preserves_detail_by_default(self) -> None:
        self.refined()
        self.edit("--collapse", 1, 1)
        self.edit("--paint", 1, 1, "#00FF00")
        self.assertEqual(self.report("--sample", 1, 1)["sample"]["rgba"], list(GREEN))
        self.assertEqual(self.report("--sample", 1, 1, "--child", 1, 0)["sample"]["rgba"], list(BLUE))
        self.edit("--split", 1, 1)
        self.assertEqual(load_project(self.project).sample(1, 1, (1, 0)), BLUE)

    def test_parent_edit_discard_replaces_child_initial_color(self) -> None:
        self.refined()
        self.edit("--paint", 1, 1, "#00FF00", "--detail-policy", "discard")
        self.assertFalse(self.report()["has_detail"])
        self.edit("--split", 1, 1)
        model = load_project(self.project)
        for child in ((0, 0), (1, 0), (0, 1), (1, 1)):
            self.assertEqual(model.sample(1, 1, child), GREEN)

    def test_erase_preserve_and_discard(self) -> None:
        self.refined()
        self.edit("--erase", 1, 1)
        model = load_project(self.project)
        self.assertEqual(model.sample(1, 1)[3], 0)
        self.assertEqual(model.sample(1, 1, (1, 0)), BLUE)
        self.edit("--erase", 1, 1, "--detail-policy", "discard")
        self.assertFalse(self.report()["has_detail"])
        self.assertEqual(load_project(self.project).sample(1, 1)[3], 0)

    def test_child_erase_is_transparent(self) -> None:
        self.refined()
        self.edit("--erase-child", 1, 1, 1, 0)
        self.assertEqual(load_project(self.project).sample(1, 1, (1, 0))[3], 0)
        self.assertEqual(load_project(self.project).sample(1, 1, (0, 0)), RED)

    def test_collapse_discard(self) -> None:
        self.refined()
        self.edit("--collapse", 1, 1, "--detail-policy", "discard")
        self.assertFalse(self.report()["has_detail"])
        self.edit("--split", 1, 1)
        self.assertEqual(load_project(self.project).sample(1, 1, (1, 0)), RED)

    def test_discard_detail_is_local_to_region_and_layer(self) -> None:
        self.refined(layered=True)
        self.edit("--add-layer", "人物", "--paint", 2, 2, "#00FF00")
        self.edit("--split-region", 0, 0, 3, 3)
        original = load_project(self.project)
        background = original.layers["背景"].to_source()
        self.edit("--discard-detail", 0, 0, 2, 2)
        actual = load_project(self.project)
        self.assertEqual(actual.layers["背景"].to_source(), background)
        for y in range(3):
            for x in range(3):
                self.assertEqual(actual.has_detail_at(x, y), not (x < 2 and y < 2))
        self.assertEqual(actual.sample(2, 2, (1, 0)), GREEN)
        original.discard_detail(0, 0, 2, 2)
        self.assertEqual(actual.to_source(), original.to_source())

    def test_discard_single_cell(self) -> None:
        self.refined()
        self.edit("--discard-detail", 1, 1)
        self.assertFalse(self.report()["has_detail"])
        self.assertEqual(load_project(self.project).sample(1, 1), RED)

    def test_fill_same_color_discard_drops_detail(self) -> None:
        self.refined()
        self.edit("--fill", 1, 1, "#FF0000", "--detail-policy", "discard")
        self.assertFalse(self.report()["has_detail"])
        self.assertEqual(load_project(self.project).sample(1, 1), RED)

    def test_fill_same_color_preserve_is_noop(self) -> None:
        self.refined()
        before = self.signature()
        self.edit("--fill", 1, 1, "#FF0000")
        self.assertEqual(self.signature(), before)
        self.assertTrue(self.report()["has_detail"])

    def test_fill_policy_matches_backend(self) -> None:
        for policy in ("preserve", "discard"):
            with self.subTest(policy=policy):
                self.refined(layered=True)
                expected = load_project(self.project)
                expected.fill(1, 1, GREEN, detail_policy=policy)
                self.edit("--fill", 1, 1, "#00FF00", "--detail-policy", policy)
                self.assertEqual(load_project(self.project).to_source(), expected.to_source())

    def test_same_color_fill_discard_undo_and_redo(self) -> None:
        model = PixelCanvas(4)
        model.paint(1, 1, RED)
        model.paint(2, 1, RED)
        for x in (1, 2):
            model.split_cell(x, 1)
            model.paint(x, 1, BLUE, child=(0, 0))
        model.split_cell(0, 0)  # Different parent color, outside the fill region.
        before = model.to_source()
        self.assertEqual(model.fill(1, 1, RED, detail_policy="discard"), 2)
        after = model.to_source()
        self.assertFalse(model.has_detail_at(1, 1))
        self.assertTrue(model.has_detail_at(0, 0))
        self.assertTrue(model.undo())
        self.assertEqual(model.to_source(), before)
        self.assertTrue(model.redo())
        self.assertEqual(model.to_source(), after)
        self.assertEqual(model.fill(1, 1, RED, detail_policy="discard"), 0)

    def test_inspect_sample_layer_does_not_change_active_layer(self) -> None:
        self.refined(layered=True)
        self.edit("--add-layer", "人物")
        before = self.signature()
        report = self.report("--sample", 1, 1, "--child", 1, 0, "--layer", "背景")
        self.assertEqual(report["active_layer"], "人物")
        self.assertEqual(report["sample"]["layer"], "背景")
        self.assertEqual(report["sample"]["rgba"], list(BLUE))
        self.assertEqual([entry["name"] for entry in report["layers"]], ["背景", "人物"])
        self.assertEqual(self.signature(), before)

    def test_inspect_invalid_options_do_not_write(self) -> None:
        self.refined(layered=True)
        before = self.signature()
        cases = (
            ("--child", 0, 0), ("--layer", "背景"),
            ("--sample", 0, 0, "--child", 0, 0),
            ("--sample", 1, 1, "--child", 2, 0),
            ("--sample", -1, 0), ("--sample", 4, 0),
            ("--sample", 1, 1, "--layer", "missing"),
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                result = self.run_cli("inspect", "--project", self.project, *arguments, code=2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(self.signature(), before)

    def test_flat_project_rejects_named_layer_sample(self) -> None:
        self.new()
        self.run_cli("inspect", "--project", self.project, "--sample", 0, 0, "--layer", "背景", code=2)

    def test_invalid_regions_fail_without_partial_save(self) -> None:
        self.refined()
        before = self.signature()
        for region in ((1,), (1, 1, 2), (1, 1, 1, 1, 1), (1, 1, 0, 1),
                       (1, 1, -1, 1), (3, 3, 2, 2), (-1, 0), (4, 0)):
            with self.subTest(region=region):
                self.edit("--paint", 0, 0, "#00FF00", "--discard-detail", *region, code=2)
                self.assertEqual(self.signature(), before)

    def test_invalid_edits_do_not_save_earlier_operations(self) -> None:
        self.refined()
        before = self.signature()
        output = self.root / "output.json"
        output.write_text("do not overwrite", encoding="utf-8")
        cases = (
            ("--paint", 5, 0, "#00FF00"), ("--paint", "oops", 0, "#00FF00"),
            ("--paint-child", 1, 1, 5, 0, "#00FF00"),
            ("--paint-child", 2, 2, 0, 0, "#00FF00"),
            ("--paint", 1, 1, "#GGGGGG"), ("--split-region", 3, 3, 2, 2),
            ("--erase", -1, 0), ("--collapse", 4, 0),
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                self.edit("--split", 0, 0, "--output", output, *arguments, code=2)
                self.assertEqual(self.signature(), before)
                self.assertEqual(output.read_text(encoding="utf-8"), "do not overwrite")

    def test_discard_parent_then_child_edit_fails_transactionally(self) -> None:
        self.refined()
        before = self.signature()
        self.edit("--paint", 1, 1, "#00FF00", "--detail-policy", "discard",
                  "--paint-child", 1, 1, 0, 0, "#FF0000", code=2)
        self.assertEqual(self.signature(), before)

    def test_no_operation_and_invalid_policy_are_errors(self) -> None:
        self.new()
        self.edit(code=2)
        self.edit("--detail-policy", "preserve", code=2)
        self.edit("--paint", 0, 0, "#00FF00", "--detail-policy", "typo", code=2)

    def test_valid_idempotent_operations_succeed_without_write(self) -> None:
        self.refined()
        for arguments in (("--split", 1, 1), ("--paint", 1, 1, "#FF0000"),
                          ("--discard-detail", 0, 0), ("--collapse", 0, 0)):
            before = self.signature()
            self.edit(*arguments)
            self.assertEqual(self.signature(), before)

    def test_legacy_refinement_without_expanded_field(self) -> None:
        self.project.write_text(json.dumps({
            "canvas_size": 2, "pixels": [["#FF0000", None], [None, None]],
            "refined_cells": [{"x": 0, "y": 0, "children": [
                ["#FF0000", "#0000FF"], [None, "#FF0000"],
            ]}],
        }), encoding="utf-8")
        self.assertEqual(self.report()["layers"][0]["expanded_cells"], 1)
        self.edit("--collapse", 0, 0)
        self.assertEqual(self.report("--sample", 0, 0, "--child", 1, 0)["sample"]["rgba"], list(BLUE))

    def test_malformed_projects_and_io_errors_are_reported(self) -> None:
        for content in (b'{', b'[]', b'null', b'{}', b'\xff\xfe'):
            with self.subTest(content=content):
                self.project.write_bytes(content)
                self.run_cli("inspect", "--project", self.project, code=2)
                self.assertEqual(self.project.read_bytes(), content)
        self.run_cli("inspect", "--project", self.root / "missing.json", code=2)
        self.run_cli("new", "--output", self.root / "missing" / "file.json", code=2)

    def test_failed_atomic_replace_keeps_original_and_removes_temporary(self) -> None:
        self.refined()
        before = self.signature()
        model = load_project(self.project)
        model.paint(0, 0, GREEN)
        with patch("pixel_cli.os.replace", side_effect=OSError("simulated replace failure")):
            with self.assertRaises(OSError):
                save_project(model, self.project)
        self.assertEqual(self.signature(), before)
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_help_for_all_subcommands(self) -> None:
        for command in ("new", "edit", "inspect", "export"):
            self.run_cli(command, "--help")


if __name__ == "__main__":
    unittest.main()
