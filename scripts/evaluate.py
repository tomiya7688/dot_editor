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

    refined = PixelCanvas(4)
    refined.paint(1, 1, (255, 0, 0, 255))
    assert refined.split_cell(1, 1)
    assert refined.paint(1, 1, (0, 0, 255, 255), child=(1, 0))
    restored_refined = PixelCanvas.from_source(refined.to_source())
    assert restored_refined.is_split(1, 1)
    assert restored_refined.sample(1, 1, (1, 0)) == (0, 0, 255, 255)
    assert restored_refined.render().getpixel((3, 2)) == (0, 0, 255, 255)
    assert restored_refined.resize(8)
    assert not restored_refined.has_refinements
    assert restored_refined.sample(3, 2) == (0, 0, 255, 255)

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
    layers.select_layer("人物")
    assert layers.split_cell(1, 1)
    assert layers.paint(1, 1, (0, 0, 255, 255), child=(1, 0))
    composite = layers.composite()
    assert composite.size == (8, 8)
    assert composite.getpixel((3, 2)) == (0, 0, 255, 255)

    restored = LayeredPixelCanvas.from_source(layers.to_source())
    assert set(restored.layers) == {"背景", "人物"}
    restored.select_layer("人物")
    assert restored.is_split(1, 1)
    assert restored.sample(1, 1, (1, 0)) == (0, 0, 255, 255)

def check_display_resize() -> None:
    from dot_editor import PixelEditor
    from pixel_layers import LayeredPixelCanvas

    class FakeCanvas:
        def __init__(self) -> None:
            self.settings: dict[str, object] = {}

        def config(self, **kwargs: object) -> None:
            self.settings.update(kwargs)

        def configure(self, **kwargs: object) -> None:
            self.settings.update(kwargs)

    editor = PixelEditor.__new__(PixelEditor)
    editor.canvas_width = 640
    editor.canvas_height = 640
    editor.num_pixels_x = 4
    editor.num_pixels_y = 4
    editor.zoom_factor = 1.0
    editor.pixel_size = 160
    editor.display_pixel_size = 160
    editor.canvas = FakeCanvas()
    editor.backend = LayeredPixelCanvas(4)
    editor.backend.paint(0, 0, (0, 20, 40, 255))
    editor.backend.add_layer("人物")
    editor.backend.paint(1, 1, (255, 0, 0, 255))
    assert editor.backend.split_cell(1, 1)
    assert editor.backend.paint(1, 1, (0, 0, 255, 255), child=(1, 0))
    editor.selected_cell = (1, 1)
    editor.history = [("history",)]
    editor.future = [("future",)]
    editor.create_grid = lambda: None
    editor.update_canvas = lambda: None
    editor.refresh_layer_list = lambda: None

    backend = editor.backend
    before = backend.to_source()
    history_before = list(editor.history)
    future_before = list(editor.future)

    editor.set_display_size(800, 480)

    assert editor.backend is backend
    assert editor.backend.to_source() == before
    assert editor.history == history_before
    assert editor.future == future_before
    assert editor.canvas_width == 800
    assert editor.canvas_height == 480
    assert editor.image.size == (800, 480)
    assert set(editor.backend.layers) == {"背景", "人物"}
    assert editor.backend.is_split(1, 1)

    assert editor.resize_logical_canvas(8)
    assert editor.backend is backend
    assert editor.backend.size == 8
    assert {layer.size for layer in editor.backend.layers.values()} == {8}
    assert not editor.backend.has_refinements
    assert editor.backend.sample(3, 2) == (0, 0, 255, 255)
    assert len(editor.history) == len(history_before) + 1
    assert editor.future == []
    resized_source = editor.backend.to_source()
    restored_resized = LayeredPixelCanvas.from_source(resized_source)
    assert restored_resized.to_source() == resized_source

    editor.reset_canvas_model()
    assert editor.backend is not backend
    assert editor.backend.to_source() != before
    assert editor.history == []
    assert editor.future == []


def run_cli_failure(*arguments: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [PYTHON, str(CLI), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr
    return result


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

        refined = root / "refined.json"
        refined_png = root / "refined.png"
        run_cli("new", "--size", "4", "--output", str(refined))
        run_cli(
            "edit",
            "--project",
            str(refined),
            "--split",
            "1",
            "1",
            "--paint",
            "1",
            "1",
            "#FF0000",
            "--paint-child",
            "1",
            "1",
            "1",
            "0",
            "#0000FF",
            "--erase-child",
            "1",
            "1",
            "0",
            "1",
        )
        run_cli(
            "export",
            "--project",
            str(refined),
            "--output",
            str(refined_png),
            "--size",
            "8",
        )

        refined_source = json.loads(refined.read_text(encoding="utf-8"))
        assert refined_source["canvas_size"] == 4
        assert len(refined_source["refined_cells"]) == 1
        children = refined_source["refined_cells"][0]["children"]
        assert children[0][1] == "#0000FF"
        assert children[1][0] is None
        with Image.open(refined_png) as exported:
            assert exported.size == (8, 8)
            assert exported.getpixel((3, 2)) == (0, 0, 255, 255)
            assert exported.getpixel((2, 3))[3] == 0

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

        malformed = root / "malformed.json"
        malformed.write_text("{not valid json", encoding="utf-8")
        failure = run_cli_failure(
            "edit",
            "--project",
            str(malformed),
            "--upscale",
        )
        assert "failed to read project" in failure.stderr

        invalid_layered = root / "invalid-layered.json"
        invalid_layered.write_text(
            json.dumps(
                {
                    "canvas_size": 2,
                    "active_layer": "missing",
                    "layers": [
                        {
                            "name": "背景",
                            "source": {
                                "canvas_size": 2,
                                "pixels": [[None, None], [None, None]],
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        failure = run_cli_failure(
            "export",
            "--project",
            str(invalid_layered),
            "--output",
            str(root / "invalid.png"),
        )
        assert "active_layer" in failure.stderr


def check_gui_invalid_project() -> None:
    import dot_editor
    from dot_editor import PixelEditor
    from pixel_layers import LayeredPixelCanvas

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "invalid.json"
        path.write_text(
            json.dumps(
                {
                    "canvas_size": 2,
                    "active_layer": "missing",
                    "layers": [
                        {
                            "name": "背景",
                            "source": {
                                "canvas_size": 2,
                                "pixels": [[None, None], [None, None]],
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        editor = PixelEditor.__new__(PixelEditor)
        editor.backend = LayeredPixelCanvas(2)
        original_backend = editor.backend
        original_dialog = dot_editor.filedialog.askopenfilename
        dot_editor.filedialog.askopenfilename = lambda **_kwargs: str(path)
        try:
            editor.load_project()
        finally:
            dot_editor.filedialog.askopenfilename = original_dialog
        assert editor.backend is original_backend


def main() -> int:
    checks = (
        ("compile", check_compile),
        ("backend", check_backend),
        ("layers", check_layers),
        ("display-resize", check_display_resize),
        ("cli", check_cli),
        ("gui-invalid-project", check_gui_invalid_project),
    )
    for name, check in checks:
        check()
        print(f"[ok] {name}")
    print("[ok] evaluation complete (GUI was not launched)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
