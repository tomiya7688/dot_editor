from __future__ import annotations

import json
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PYTHON = sys.executable
DOT_EDITOR = ROOT / "dot_editor.py"
BACKEND = ROOT / "pixel_backend.py"
CLI = ROOT / "pixel_cli.py"


def check_compile() -> None:
    sources = [
        path
        for path in ROOT.glob("*.py")
        if path.name != "__init__.py"
    ]
    sources += list((ROOT / "scripts").glob("*.py"))
    for path in sources:
        py_compile.compile(str(path), doraise=True)


def check_backend() -> None:
    from pixel_backend import PixelCanvas

    canvas = PixelCanvas(4)
    assert canvas.paint(1, 1, (255, 0, 0, 255))
    assert canvas.sample(1, 1) == (255, 0, 0, 255)
    assert canvas.undo()
    assert canvas.sample(1, 1)[3] == 0
    assert canvas.redo()
    assert canvas.fill(0, 0, (0, 255, 0, 255)) == 15
    assert canvas.upscale()
    assert canvas.size == 8
    assert canvas.sample(2, 2) == (255, 0, 0, 255)

    restored = PixelCanvas.from_source(canvas.to_source())
    assert restored.size == 8
    assert restored.sample(2, 2) == (255, 0, 0, 255)

    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "export.png"
        canvas.save_png(output, 16)
        with Image.open(output) as image:
            assert image.size == (16, 16)
            assert image.mode == "RGBA"


def check_layers() -> None:
    from pixel_layers import LayeredPixelCanvas

    layers = LayeredPixelCanvas(4)
    layers.add_layer("人物")
    layers.paint(1, 1, (255, 0, 0, 255))
    layers.select_layer("背景")
    layers.paint(0, 0, (0, 0, 30, 255))
    assert layers.composite().getpixel((1, 1)) == (255, 0, 0, 255)
    restored = LayeredPixelCanvas.from_source(layers.to_source())
    assert set(restored.layers) == {"背景", "人物"}

def run_cli(*arguments: str) -> None:
    result = subprocess.run(
        [PYTHON, str(CLI), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise AssertionError(
            f"CLI failed: {' '.join(arguments)}\n{result.stdout}\n{result.stderr}"
        )


def check_cli() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        project = root / "project.json"
        image = root / "image.png"

        run_cli("new", "--size", "4", "--output", str(project))
        run_cli(
            "edit",
            "--project",
            str(project),
            "--paint",
            "1",
            "1",
            "#FF0000",
        )
        run_cli("edit", "--project", str(project), "--upscale")
        run_cli(
            "export",
            "--project",
            str(project),
            "--output",
            str(image),
            "--size",
            "16",
        )

        source = json.loads(project.read_text(encoding="utf-8"))
        assert source["canvas_size"] == 8
        with Image.open(image) as exported:
            assert exported.size == (16, 16)


        layered = root / "layered.json"
        layered_png = root / "layered.png"
        run_cli("new", "--size", "4", "--layered", "--output", str(layered))
        run_cli("edit", "--project", str(layered), "--add-layer", "人物")
        run_cli("edit", "--project", str(layered), "--select-layer", "人物", "--paint", "1", "1", "#FF0000")
        run_cli("export", "--project", str(layered), "--output", str(layered_png), "--size", "16")
        run_cli("edit", "--project", str(layered), "--upscale")
        layered_source = json.loads(layered.read_text(encoding="utf-8"))
        assert layered_source["canvas_size"] == 8
        assert {item["name"] for item in layered_source["layers"]} == {"背景", "人物"}
        with Image.open(layered_png) as exported:
            assert exported.getpixel((4, 4))[:3] == (255, 0, 0)


def main() -> int:
    checks = (
        ("compile", check_compile),
        ("backend", check_backend),
        ("layers", check_layers),
        ("cli", check_cli),
    )
    for name, check in checks:
        check()
        print(f"[ok] {name}")
    print("[ok] evaluation complete (GUI was not launched)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
