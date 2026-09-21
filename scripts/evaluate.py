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

    canvas = PixelCanvas(16)
    assert canvas.paint(0, 0, (80, 30, 30, 255))
    assert canvas.paint(1, 0, (120, 30, 30, 255))
    original = canvas.render_resolution(16, 16).tobytes()

    assert canvas.set_resolution(7, 7)
    assert canvas.resolution == (7, 7)
    assert canvas.set_resolution(16, 16)
    assert canvas.render_resolution(16, 16).tobytes() == original

    assert canvas.set_resolution(7, 7)
    assert canvas.paint(0, 0, (160, 90, 90, 255), detail_policy="preserve")
    assert canvas.sample(0, 0) == (160, 90, 90, 255)
    assert canvas.set_resolution(16, 16)
    assert len({canvas.sample(x, y) for x in range(3) for y in range(3)}) > 1

    assert canvas.set_resolution(23, 17)
    assert canvas.resolution == (23, 17)
    restored = PixelCanvas.from_source(canvas.to_source())
    assert restored.to_source() == canvas.to_source()

    refined = PixelCanvas(4)
    assert refined.paint(1, 1, (100, 20, 20, 255))
    assert refined.split_cell(1, 1)
    assert refined.paint(1, 1, (20, 20, 180, 255), child=(1, 0))
    assert refined.paint(
        1,
        1,
        (140, 100, 80, 255),
        detail_policy="preserve",
    )
    assert len({
        refined.sample(1, 1, (child_x, child_y))
        for child_y in range(2)
        for child_x in range(2)
    }) > 1
    assert refined.collapse_cell(1, 1)
    assert refined.has_detail_at(1, 1)
    collapsed = PixelCanvas.from_source(refined.to_source())
    assert not collapsed.is_split(1, 1)
    assert collapsed.has_detail_at(1, 1)
    assert collapsed.discard_detail(1, 1) == 1
    assert not collapsed.has_detail_at(1, 1)
    assert collapsed.undo()
    assert collapsed.has_detail_at(1, 1)

    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "export.png"
        canvas.save_png(output, (230, 170))
        with Image.open(output) as image:
            assert image.size == (230, 170)
            assert image.mode == "RGBA"


def check_layers() -> None:
    from pixel_layers import LayeredPixelCanvas

    layers = LayeredPixelCanvas(16)
    layers.paint(0, 0, (0, 0, 30, 255))
    layers.add_layer("人物")
    layers.paint(1, 0, (120, 30, 30, 255))
    before = layers.composite((16, 16)).tobytes()

    assert layers.set_resolution(7, 7)
    assert {layer.resolution for layer in layers.layers.values()} == {(7, 7)}
    assert layers.set_resolution(16, 16)
    assert layers.composite((16, 16)).tobytes() == before

    assert layers.set_resolution(23, 17)
    assert layers.resolution == (23, 17)
    restored = LayeredPixelCanvas.from_source(layers.to_source())
    assert restored.to_source() == layers.to_source()


def check_display_resize_and_resolution() -> None:
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
    editor.canvas_height = 480
    editor.num_pixels_x = 4
    editor.num_pixels_y = 3
    editor.zoom_factor = 1.0
    editor.pixel_width = 160.0
    editor.pixel_height = 160.0
    editor.pixel_size = 160
    editor.display_pixel_width = 160.0
    editor.display_pixel_height = 160.0
    editor.display_pixel_size = 160
    editor.detail_policy = "preserve"
    editor.canvas = FakeCanvas()
    editor.backend = LayeredPixelCanvas((4, 3))
    editor.backend.paint(0, 0, (0, 20, 40, 255))
    editor.backend.add_layer("人物")
    editor.backend.paint(1, 1, (100, 20, 20, 255))
    assert editor.backend.split_cell(1, 1)
    assert editor.backend.paint(1, 1, (20, 20, 180, 255), child=(1, 0))
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

    editor.set_display_size(800, 600)
    assert editor.backend is backend
    assert editor.backend.to_source() == before
    assert editor.history == history_before
    assert editor.future == future_before
    assert editor.image.size == (800, 600)

    assert editor.resize_logical_canvas(7, 5)
    assert editor.backend is backend
    assert editor.backend.resolution == (7, 5)
    assert editor.num_pixels_x == 7
    assert editor.num_pixels_y == 5
    assert {layer.resolution for layer in editor.backend.layers.values()} == {(7, 5)}
    assert len(editor.history) == len(history_before) + 1
    assert editor.future == []

    editor.set_detail_policy("discard")
    assert editor.detail_policy == "discard"
    editor.set_detail_policy("preserve")
    assert editor.detail_policy == "preserve"

    source = editor.backend.to_source()
    restored = LayeredPixelCanvas.from_source(source)
    assert restored.to_source() == source

    editor.reset_canvas_model()
    assert editor.backend is not backend
    assert editor.backend.resolution == (7, 5)
    assert editor.history == []
    assert editor.future == []


def check_tool_state_ui() -> None:
    from dot_editor import PixelEditor

    class FakeWidget:
        def __init__(self) -> None:
            self.options: dict[str, object] = {}

        def configure(self, **kwargs: object) -> None:
            self.options.update(kwargs)

    editor = PixelEditor.__new__(PixelEditor)
    editor.tool = "brush"
    editor.current_color = (10, 20, 30)
    editor.tool_buttons = {
        "brush": FakeWidget(),
        "fill": FakeWidget(),
        "eraser": FakeWidget(),
        "picker": FakeWidget(),
    }
    editor.tool_status_label = FakeWidget()

    editor.refresh_tool_state()
    assert editor.tool_buttons["brush"].options["relief"] == "sunken"
    editor.set_tool("eraser")
    assert editor.tool_buttons["eraser"].options["relief"] == "sunken"
    assert editor.current_color == (10, 20, 30)
    editor.activate_eyedropper()
    assert editor.tool == "picker"
    editor.set_palette_color((255, 0, 0))
    assert editor.tool == "brush"

    try:
        editor.set_tool("unknown")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown drawing tools must be rejected")


def run_cli_capture(*arguments: str) -> subprocess.CompletedProcess[str]:
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
    return result


def run_cli(*arguments: str) -> None:
    run_cli_capture(*arguments)


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


def check_cli() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        project = root / "project.json"
        image = root / "image.png"

        run_cli(
            "new",
            "--resolution",
            "16",
            "16",
            "--output",
            str(project),
        )
        run_cli(
            "edit",
            "--project",
            str(project),
            "--paint",
            "0",
            "0",
            "#503030",
        )
        run_cli(
            "edit",
            "--project",
            str(project),
            "--paint",
            "1",
            "0",
            "#783030",
        )
        run_cli(
            "edit",
            "--project",
            str(project),
            "--resolution",
            "7",
            "7",
        )
        run_cli(
            "edit",
            "--project",
            str(project),
            "--paint",
            "0",
            "0",
            "#A05A5A",
            "--detail-policy",
            "preserve",
        )
        inspect = json.loads(
            run_cli_capture("inspect", "--project", str(project)).stdout
        )
        assert inspect["resolution"] == [7, 7]
        assert inspect["has_detail"]

        run_cli(
            "edit",
            "--project",
            str(project),
            "--resolution",
            "23",
            "17",
        )
        inspect = json.loads(
            run_cli_capture("inspect", "--project", str(project)).stdout
        )
        assert inspect["resolution"] == [23, 17]

        run_cli(
            "export",
            "--project",
            str(project),
            "--output",
            str(image),
            "--resolution",
            "230",
            "170",
        )
        with Image.open(image) as exported:
            assert exported.size == (230, 170)

        refined = root / "refined.json"
        run_cli("new", "--size", "4", "--output", str(refined))
        run_cli(
            "edit",
            "--project",
            str(refined),
            "--split",
            "1",
            "1",
            "--paint-child",
            "1",
            "1",
            "1",
            "0",
            "#0000FF",
        )
        inspect = json.loads(
            run_cli_capture("inspect", "--project", str(refined)).stdout
        )
        assert inspect["has_detail"]
        run_cli(
            "edit",
            "--project",
            str(refined),
            "--discard-detail",
            "1",
            "1",
        )
        inspect = json.loads(
            run_cli_capture("inspect", "--project", str(refined)).stdout
        )
        assert not inspect["has_refinements"]

        layered = root / "layered.json"
        run_cli(
            "new",
            "--resolution",
            "23",
            "17",
            "--layered",
            "--output",
            str(layered),
        )
        run_cli("edit", "--project", str(layered), "--add-layer", "人物")
        run_cli(
            "edit",
            "--project",
            str(layered),
            "--select-layer",
            "人物",
            "--paint",
            "1",
            "1",
            "#FF0000",
        )
        inspect = json.loads(
            run_cli_capture("inspect", "--project", str(layered)).stdout
        )
        assert inspect["layered"]
        assert inspect["resolution"] == [23, 17]
        assert set(inspect["layers"]) == {"背景", "人物"}

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
        ("display-resolution", check_display_resize_and_resolution),
        ("tool-state-ui", check_tool_state_ui),
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
