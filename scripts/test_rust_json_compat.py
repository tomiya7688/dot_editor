"""Verify Rust version 2 exports using the Python reference without opening a GUI."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pixel_backend import PixelCanvas


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
    result = subprocess.run([
        "cargo", "run", "--quiet", "--manifest-path", str(ROOT / "rust" / "Cargo.toml"),
        "--example", "json_compat_fixture",
    ], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120)
    if result.returncode:
        raise RuntimeError(result.stderr)
    cases = json.loads(result.stdout)
    for case in cases:
        check_case(case)
    fixture = json.loads((ROOT / "tests" / "fixtures" / "project_json" / "transparent_rectangular_v2.json").read_text(encoding="utf-8"))
    assert cases[0]["source"] == fixture
    print(f"Rust to Python JSON compatibility: {len(cases)} cases passed (load, render, save/reload).")


if __name__ == "__main__":
    main()
