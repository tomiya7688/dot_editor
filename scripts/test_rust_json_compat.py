"""Verify single-canvas JSON interchange in both directions without opening a GUI."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pixel_backend import PixelCanvas
from PIL import Image


def image_rows(image):
    return [[list(image.getpixel((x, y))) for x in range(image.width)]
            for y in range(image.height)]


def check_case(case):
    source = case["source"]
    # Loading validates previews and child compatibility data as well as patches.
    canvas = PixelCanvas.from_source(source)
    restored = PixelCanvas.from_source(json.loads(json.dumps(canvas.to_source())))
    for observation in case["observations"]:
        width, height = observation["resolution"]
        for model in (canvas, restored):
            model.set_resolution(width, height)
            assert image_rows(model.image) == observation["logical"], (case["name"], "logical", width, height)
            assert image_rows(model.render_resolution(width, height)) == observation["detail"], (case["name"], "detail", width, height)
            native = model.render()
            assert list(native.size) == observation["native_resolution"], case["name"]
            assert image_rows(native) == observation["native"], (case["name"], "native", width, height)
    # The clipped raw offsets must still permit subsequent detail edits.
    if case["name"] == "clipped_offsets":
        for model in (canvas, restored):
            model.set_resolution(7, 5)
            model.paint(1, 1, (50, 60, 70, 128))
            assert image_rows(model.render_resolution(16, 12)) == case["edited_detail"], (case["name"], "edited detail")


def main():
    command = [
        "cargo", "run", "--quiet", "--manifest-path", str(ROOT / "rust" / "Cargo.toml"),
        "--example", "json_compat_fixture",
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120)
    if result.returncode:
        raise RuntimeError(result.stderr)
    cases = json.loads(result.stdout)
    for case in cases:
        check_case(case)
    fixture = json.loads((ROOT / "tests" / "fixtures" / "project_json" / "transparent_rectangular_v2.json").read_text(encoding="utf-8"))
    assert cases[0]["source"] == fixture
    imports = [{"name": case["name"], "source": PixelCanvas.from_source(case["source"]).to_source()} for case in cases]
    image = Image.new("RGBA", (16, 12))
    image.putdata([(40 + x * 3, 60 + y * 3, 80 + x, 128) for y in range(12) for x in range(16)])
    python = PixelCanvas(16, 12)
    python.import_image(image)
    python.set_resolution(7, 5)
    python.paint(1, 1, (0, 255, 10, 0))
    python.paint(3, 2, (10, 20, 30, 40), detail_policy="discard")
    python.set_resolution(4, 3)
    python.split_cell(1, 1)
    python.paint(1, 1, (5, 6, 7, 8), child=(1, 0))
    python.collapse_cell(1, 1)
    imports.append({"name": "python_origin_edits", "source": python.to_source()})
    legacy = json.loads((ROOT / "tests" / "fixtures" / "project_json" / "legacy_refinement_v1.json").read_text(encoding="utf-8"))
    imports.append({"name": "legacy_refinement", "source": legacy})
    result = subprocess.run(command + ["--", "--import"], input=json.dumps(imports),
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120)
    if result.returncode:
        raise RuntimeError(result.stderr)
    returned = json.loads(result.stdout)
    assert len(returned) == len(imports)
    for entry, loaded in zip(imports, returned):
        assert entry["name"] == loaded["name"]
        original = PixelCanvas.from_source(entry["source"])
        canonical = loaded["source"]
        check_case(loaded)
        for observation in loaded["observations"]:
            width, height = observation["resolution"]
            original.set_resolution(width, height)
            assert image_rows(original.image) == observation["logical"], entry["name"]
            assert image_rows(original.render_resolution(width, height)) == observation["detail"], entry["name"]
            assert image_rows(original.render()) == observation["native"], entry["name"]
        assert canonical["version"] == 2
    print(f"JSON compatibility: {len(cases)} Rust exports and {len(imports)} Python/legacy imports passed.")


if __name__ == "__main__":
    main()
