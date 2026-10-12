from __future__ import annotations

import json
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))
PYTHON = sys.executable
DOT_EDITOR = SOURCE / "dot_editor.py"
BACKEND = SOURCE / "pixel_backend.py"
CLI = SOURCE / "pixel_cli.py"


# {
#   責務: [check_compile: src・scripts・testsのPythonファイルを構文コンパイルする]
#   処理: [対象ディレクトリから__init__.py以外を集め、py_compileで順にコンパイルする]
#   引数: [なし]
#   戻り値: [なし、構文エラーがあればpy_compileの例外を送出する]
# }
def check_compile() -> None:
    sources = [
        path
        for path in SOURCE.glob("*.py")
        if path.name != "__init__.py"
    ]
    sources += list((ROOT / "scripts").glob("*.py"))
    sources += list((ROOT / "tests").glob("*.py"))
    for path in sources:
        py_compile.compile(str(path), doraise=True)


# {
#   責務: [check_backend: PixelCanvasの描画・履歴・細部保持・解像度・PNG出力を評価する]
#   処理: [塗り・Undo/Redo・fill・拡大・JSON復元・子画素編集と保持／破棄・PNG寸法とRGBA形式を照合する]
#   引数: [なし]
#   戻り値: [なし、期待値と異なる場合はassertionで失敗する]
# }
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

    assert restored_refined.paint(
        1,
        1,
        (0, 255, 0, 255),
        detail_policy="preserve",
    )
    preserved = PixelCanvas.from_source(restored_refined.to_source())
    assert preserved.sample(1, 1) == (0, 255, 0, 255)
    assert preserved.sample(1, 1, (1, 0)) == (0, 0, 255, 255)
    assert preserved.collapse_cell(1, 1)
    assert not preserved.is_split(1, 1)
    assert preserved.has_detail_at(1, 1)
    assert preserved.render().size == (4, 4)
    collapsed = PixelCanvas.from_source(preserved.to_source())
    assert not collapsed.is_split(1, 1)
    assert collapsed.has_detail_at(1, 1)
    assert collapsed.split_cell(1, 1)
    assert collapsed.sample(1, 1, (1, 0)) == (0, 0, 255, 255)
    assert preserved.discard_detail(1, 1) == 1
    assert not preserved.is_split(1, 1)
    assert preserved.undo()
    assert not preserved.is_split(1, 1)
    assert preserved.has_detail_at(1, 1)
    assert preserved.sample(1, 1, (1, 0)) == (0, 0, 255, 255)

    assert restored_refined.resize(8)
    assert not restored_refined.has_refinements
    assert restored_refined.sample(3, 2) == (0, 0, 255, 255)

    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "export.png"
        canvas.save_png(output, 16)
        with Image.open(output) as image:
            assert image.size == (16, 16)
            assert image.mode == "RGBA"


# {
#   責務: [check_layers: レイヤー選択・合成・子画素編集・JSON復元を評価する]
#   処理: [背景と人物レイヤーを編集し、合成画素・分割状態・復元後の子画素色を照合する]
#   引数: [なし]
#   戻り値: [なし、期待値と異なる場合はassertionで失敗する]
# }
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

# {
#   責務: [check_display_resize: 表示領域変更と論理解像度変更の状態境界を評価する]
#   処理: [表示サイズ変更で作品・履歴が保たれること、論理解像度変更とリセットで状態が更新されることを照合する]
#   引数: [なし]
#   戻り値: [なし、バックエンド・履歴・画像寸法が期待と異なる場合はassertionで失敗する]
# }
def check_display_resize() -> None:
    from dot_editor import PixelEditor
    from pixel_layers import LayeredPixelCanvas

    # {
    #   責務: [FakeCanvas: 表示サイズ確認でCanvasの設定値を記録するテスト用オブジェクト]
    #   フィールド: [settings: config/configureへ渡された設定値]
    # }
    class FakeCanvas:
        # {
        #   責務: [__init__: Canvas設定記録用の辞書を初期化する]
        #   処理: [空の設定辞書をインスタンスへ割り当てる]
        #   引数: [self: 初期化するFakeCanvas]
        #   戻り値: [なし]
        # }
        def __init__(self) -> None:
            self.settings: dict[str, object] = {}

        # {
        #   責務: [config: Canvas設定をテスト用辞書へ記録する]
        #   処理: [キーワード設定をsettings辞書へ追加または上書きする]
        #   引数: [self: 設定を受け取るFakeCanvas、kwargs: Canvas設定値]
        #   戻り値: [なし]
        # }
        def config(self, **kwargs: object) -> None:
            self.settings.update(kwargs)

        # {
        #   責務: [configure: configと同じ方法でCanvas設定を記録する]
        #   処理: [キーワード設定をsettings辞書へ追加または上書きする]
        #   引数: [self: 設定を受け取るFakeCanvas、kwargs: Canvas設定値]
        #   戻り値: [なし]
        # }
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


# {
#   責務: [check_tool_state_ui: 描画ツール・色の切替がボタン表示と状態へ反映されることを評価する]
#   処理: [ブラシ・消しゴム・スポイト・色選択後の選択ツールと表示状態を照合し、不正ツールの拒否を確認する]
#   引数: [なし]
#   戻り値: [なし、表示または選択状態が期待と異なる場合はassertionで失敗する]
# }
def check_tool_state_ui() -> None:
    from dot_editor import PixelEditor

    # {
    #   責務: [FakeWidget: ツールUIのconfigure設定を記録するテスト用ウィジェット]
    #   フィールド: [options: configureへ渡された設定値]
    # }
    class FakeWidget:
        # {
        #   責務: [__init__: ウィジェット設定記録用の辞書を初期化する]
        #   処理: [空の設定辞書をインスタンスへ割り当てる]
        #   引数: [self: 初期化するFakeWidget]
        #   戻り値: [なし]
        # }
        def __init__(self) -> None:
            self.options: dict[str, object] = {}

        # {
        #   責務: [configure: ツールUIへ渡された設定値を記録する]
        #   処理: [キーワード設定をoptions辞書へ追加または上書きする]
        #   引数: [self: 設定を受け取るFakeWidget、kwargs: ウィジェット設定値]
        #   戻り値: [なし]
        # }
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
    assert editor.tool_buttons["fill"].options["relief"] == "flat"
    assert editor.tool_status_label.options["text"] == "現在: ブラシ"

    editor.set_tool("eraser")
    assert editor.tool == "eraser"
    assert editor.tool_buttons["eraser"].options["relief"] == "sunken"
    assert editor.tool_buttons["brush"].options["relief"] == "flat"
    assert editor.tool_status_label.options["text"] == "現在: 消しゴム"
    assert editor.current_color == (10, 20, 30)

    editor.activate_eyedropper()
    assert editor.tool == "picker"
    assert editor.tool_status_label.options["text"] == "現在: スポイト"

    editor.set_palette_color((255, 0, 0))
    assert editor.current_color == (255, 0, 0)
    assert editor.tool == "brush"
    assert editor.tool_buttons["brush"].options["relief"] == "sunken"

    try:
        editor.set_tool("unknown")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown drawing tools must be rejected")


# {
#   責務: [run_cli_failure: CLIの異常終了と利用者向けエラー出力を確認する]
#   処理: [pixel_cli.pyへ引数を渡して実行し、非ゼロ終了とTraceback非表示を検査する]
#   引数: [arguments: CLIへ渡す引数列]
#   戻り値: [標準出力・標準エラー・終了値を含むCompletedProcess]
# }
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


# {
#   責務: [run_cli: CLIコマンドを実行し正常終了を要求する]
#   処理: [pixel_cli.pyへ引数を渡して実行し、失敗時は引数と出力を含むAssertionErrorを送出する]
#   引数: [arguments: CLIへ渡す引数列]
#   戻り値: [なし]
# }
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


# {
#   責務: [check_cli: CLIの新規作成・編集・細部・レイヤー・エラー処理を評価する]
#   処理: [一時プロジェクトで編集とPNG出力を行い、JSON・画像・不正入力時のエラーを照合する]
#   引数: [なし]
#   戻り値: [なし、CLI結果が期待と異なる場合はassertionで失敗する]
# }
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


# {
#   責務: [check_gui_invalid_project: 不正なレイヤーJSON読込時にGUIの既存バックエンドを保つことを評価する]
#   処理: [不正プロジェクトを一時作成し、ファイル選択を差し替えて読込後のバックエンド同一性を確認する]
#   引数: [なし]
#   戻り値: [なし、読込失敗でバックエンドが置き換わればassertionで失敗する]
# }
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


# {
#   責務: [main: 評価項目を順に実行し成功結果を表示する]
#   処理: [コンパイル・バックエンド・レイヤー・GUI状態・CLIを実行し、各項目の成功表示後に完了を報告する]
#   引数: [なし]
#   戻り値: [全評価が成功した場合の終了コード0、失敗時は例外を呼出元へ送出する]
# }
def main() -> int:
    checks = (
        ("compile", check_compile),
        ("backend", check_backend),
        ("layers", check_layers),
        ("display-resize", check_display_resize),
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
