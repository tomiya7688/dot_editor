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

ROOT = Path(__file__).resolve().parents[1] / "src"
RED = (255, 0, 0, 255)
GREEN = (0, 255, 0, 255)
BLUE = (0, 0, 255, 255)


# {
#   責務: [CommandApiTests: 共通Command APIの直接利用・GUI/CUI接続・失敗時の安全性を検証する]
#   フィールド: [
#     directory: テスト用一時ディレクトリと後片付け登録
#     root: テスト用ファイルを保存するディレクトリ
#   ]
# }
class CommandApiTests(unittest.TestCase):
    # {
    #   責務: [setUp: 各テスト専用の一時ディレクトリを作成する]
    #   処理: [TemporaryDirectoryを作り、テスト終了時の削除を登録してrootへパスを保存する]
    #   引数: [self: テスト対象のCommandApiTestsケース]
    #   戻り値: [なし、一時領域とそのPathをselfに設定する]
    # }
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    # {
    #   責務: [cli: pixel_cli.pyを別プロセスで実行し、終了状態と例外出力を検証する]
    #   処理: [
    #     1: 引数を文字列化し、UTF-8・色なし環境でCLIを起動する
    #     2: 標準入力を閉じ、標準出力と標準エラーを取得する
    #     3: 期待終了コードとTraceback不在を確認して結果を返す
    #   ]
    #   引数: [self: テストケース、arguments: CLI引数列、code: 期待する終了コード]
    #   戻り値: [出力と終了コードを含むCompletedProcess]
    # }
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

    # {
    #   責務: [test_direct_api_matches_backend_for_core_edits: 共通APIの基本編集結果がレイヤーバックエンドと一致することを検証する]
    #   処理: [
    #     1: 同じCanvasに描画・分割・子画素編集・折りたたみ・レイヤー追加・解像度変更を行う
    #     2: APIとバックエンドの保存表現を比較する
    #     3: 照会結果の解像度・文書種別・選択レイヤーを確認する
    #   ]
    #   引数: [self: テスト対象のCommandApiTestsケース]
    #   戻り値: [なし、編集結果や照会結果が一致しなければassertionで失敗する]
    # }
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

    # {
    #   責務: [test_execute_is_stable_for_automation_callers: execute経由の編集・照会・レイヤー操作と未知コマンド拒否を検証する]
    #   処理: [
    #     1: paint・sample・split・eraseをexecuteで実行して結果を照合する
    #     2: レイヤー追加・移動・表示切替・名前変更と再照会を確認する
    #     3: 未知コマンドがValueErrorになることを確認する
    #   ]
    #   引数: [self: テスト対象のCommandApiTestsケース]
    #   戻り値: [なし、実行結果や拒否動作が期待と異なればassertionで失敗する]
    # }
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

    # {
    #   責務: [test_project_io_and_export_share_api: 共通APIによるプロジェクト保存・復元とPNG出力を検証する]
    #   処理: [
    #     1: レイヤーCanvasへ編集を加え、JSONプロジェクトとして保存する
    #     2: 読み戻したCanvasが保存前と一致することを確認する
    #     3: PNGを出力し画像寸法と子画素の色を照合する
    #   ]
    #   引数: [self: テスト対象のCommandApiTestsケース]
    #   戻り値: [なし、保存復元や画像出力が期待と異なればassertionで失敗する]
    # }
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

    # {
    #   責務: [test_layer_sample_does_not_change_active_layer: 指定レイヤーのサンプル取得が選択中レイヤーを変えないことを検証する]
    #   処理: [
    #     1: 背景と追加レイヤーへ別々の色を描く
    #     2: 非選択レイヤーを指定してサンプルし、選択状態を比較する
    #     3: 省略時のサンプルが選択中レイヤーの色を返すことを確認する
    #   ]
    #   引数: [self: テスト対象のCommandApiTestsケース]
    #   戻り値: [なし、選択レイヤーや画素色が変化すればassertionで失敗する]
    # }
    def test_layer_sample_does_not_change_active_layer(self) -> None:
        api = PixelCommandAPI.new(4, layered=True)
        api.paint(0, 0, RED)
        api.add_layer("人物")
        api.paint(0, 0, BLUE)
        before = api.canvas.active_layer
        self.assertEqual(api.sample(0, 0, layer="背景"), RED)
        self.assertEqual(api.canvas.active_layer, before)
        self.assertEqual(api.sample(0, 0), BLUE)

    # {
    #   責務: [test_flat_layer_operations_are_rejected: レイヤー非対応Canvasでレイヤー操作を拒否することを検証する]
    #   処理: [各レイヤー操作とレイヤー指定サンプルを実行し、それぞれValueErrorになることを確認する]
    #   引数: [self: テスト対象のCommandApiTestsケース]
    #   戻り値: [なし、非対応操作が受理されればassertionで失敗する]
    # }
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

    # {
    #   責務: [test_split_region_validates_rectangular_resolution_correctly: 長方形Canvasの分割予算を正方形と誤認せず検証する]
    #   処理: [分割後が3600x1000となる1800x500 Canvasを作り、領域分割と分割状態を確認する]
    #   引数: [self: テスト対象のCommandApiTestsケース]
    #   戻り値: [なし、長方形の有効な分割を拒否すればassertionで失敗する]
    # }
    def test_split_region_validates_rectangular_resolution_correctly(self) -> None:
        # 1800x500の分割後は3600x1000で有効となる。
        # 3600x3600の正方形として検査すると、画素数上限を誤って超過する。
        api = PixelCommandAPI.new(1800, 500)
        self.assertEqual(api.split_region(0, 0, 1, 1), 1)
        self.assertTrue(api.is_split(0, 0))

    # {
    #   責務: [test_split_region_prevalidates_split_budget: 領域分割の上限超過を変更適用前に拒否することを検証する]
    #   処理: [分割上限を一時的に1へ設定して領域分割を試し、例外後も保存表現と対象セルが変わらないことを確認する]
    #   引数: [self: テスト対象のCommandApiTestsケース]
    #   戻り値: [なし、上限超過が状態を変更すればassertionで失敗する]
    # }
    def test_split_region_prevalidates_split_budget(self) -> None:
        api = PixelCommandAPI.new(4)
        api.split(0, 0)
        before = api.canvas.to_source()
        with patch.object(PixelCanvas, "MAX_SPLITS", 1):
            with self.assertRaisesRegex(ValueError, "too many"):
                api.split_region(1, 0, 2, 1)
        self.assertEqual(api.canvas.to_source(), before)
        self.assertFalse(api.is_split(1, 0))

    # {
    #   責務: [fake_editor: GUIを起動せず、Command API経路のテスト用PixelEditorを構築する]
    #   処理: [LayeredPixelCanvas・表示寸法・Mock Canvas・履歴・工具状態とGUI更新用代替関数を設定する]
    #   引数: [self: CommandApiTestsケース。失敗報告関数からテスト失敗を通知する]
    #   戻り値: [編集イベントを呼び出せるPixelEditorのテスト用インスタンス]
    # }
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

    # {
    #   責務: [test_canvas_image_is_centered_only_when_it_fits: 表示領域に収まる画像だけを中央配置することを検証する]
    #   処理: [画像が表示領域より大きい場合と小さい場合のimage_originを比較する]
    #   引数: [self: テスト対象のCommandApiTestsケース]
    #   戻り値: [なし、画像原点が期待と異なればassertionで失敗する]
    # }
    def test_canvas_image_is_centered_only_when_it_fits(self) -> None:
        from dot_editor import PixelEditor

        self.assertEqual(PixelEditor.image_origin(1000, 800, 640, 480), (180, 160))
        self.assertEqual(PixelEditor.image_origin(500, 300, 640, 480), (0, 0))

    # {
    #   責務: [test_gui_handlers_route_through_command_api: GUIの描画・分割・解像度変更処理が共通Command APIを使うことを検証する]
    #   処理: [
    #     1: テスト用Editorと元のAPIメソッドを用意する
    #     2: API呼び出しを記録するspyへ差し替える
    #     3: GUIイベント処理を呼び出し、呼び出し順と最終解像度を確認する
    #   ]
    #   引数: [self: テスト対象のCommandApiTestsケース]
    #   戻り値: [なし、API経路や変更後解像度が期待と異なればassertionで失敗する]
    # }
    def test_gui_handlers_route_through_command_api(self) -> None:
        from pixel_commands import PixelCommandAPI as Commands
        editor = self.fake_editor()
        calls: list[str] = []

        original_paint = Commands.paint
        original_split = Commands.split
        original_resolution = Commands.set_resolution

        # {
        #   責務: [spy_paint: paint APIの呼び出しを記録して元の編集処理へ渡す]
        #   処理: [呼び出し名を記録し、元のpaintメソッドへ全引数を転送する]
        #   引数: [api: 対象Command API、args: 位置引数、kwargs: 名前付き引数]
        #   戻り値: [元のpaintメソッドの結果]
        # }
        def spy_paint(api, *args, **kwargs):
            calls.append("paint")
            return original_paint(api, *args, **kwargs)

        # {
        #   責務: [spy_split: split APIの呼び出しを記録して元の分割処理へ渡す]
        #   処理: [呼び出し名を記録し、元のsplitメソッドへ全引数を転送する]
        #   引数: [api: 対象Command API、args: 位置引数、kwargs: 名前付き引数]
        #   戻り値: [元のsplitメソッドの結果]
        # }
        def spy_split(api, *args, **kwargs):
            calls.append("split")
            return original_split(api, *args, **kwargs)

        # {
        #   責務: [spy_resolution: 解像度変更APIの呼び出しを記録して元の処理へ渡す]
        #   処理: [呼び出し名を記録し、元のset_resolutionメソッドへ全引数を転送する]
        #   引数: [api: 対象Command API、args: 位置引数、kwargs: 名前付き引数]
        #   戻り値: [元のset_resolutionメソッドの結果]
        # }
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

    # {
    #   責務: [test_cli_adapter_routes_edit_through_command_api: CLI編集アダプターが共通Command API経由で編集することを検証する]
    #   処理: [
    #     1: テスト用プロジェクトを保存し、paint API呼び出しを記録するspyを用意する
    #     2: CLIの編集サブコマンドを実行して終了コードを確認する
    #     3: 呼び出し座標と保存後の画素色を照合する
    #   ]
    #   引数: [self: テスト対象のCommandApiTestsケース]
    #   戻り値: [なし、CLIのAPI経路や保存結果が期待と異なればassertionで失敗する]
    # }
    def test_cli_adapter_routes_edit_through_command_api(self) -> None:
        import pixel_cli
        project = self.root / "adapter.json"
        PixelCommandAPI.new(4, layered=True).save(project)
        calls: list[tuple[int, int]] = []
        original = PixelCommandAPI.paint

        # {
        #   責務: [spy: paint APIの座標を記録して元の描画メソッドを実行する]
        #   処理: [座標を整数化して記録し、元のpaintメソッドへ引数を転送する]
        #   引数: [api: 対象Command API、x: 横座標、y: 縦座標、color: RGBA色、kwargs: 追加編集指定]
        #   戻り値: [元のpaintメソッドの結果]
        # }
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

    # {
    #   責務: [test_required_cui_roundtrip_scenario: CLIで保持細部を含む作品を編集・解像度変更・保存・再読込・画像出力できることを検証する]
    #   処理: [
    #     1: レイヤー作品を作成し、離れた2セルの細部を編集する
    #     2: 複数の解像度へ変更して照会し、片方の細部だけを破棄して元解像度へ戻す
    #     3: 再読込した細部・画素色を確認し、複製JSONとPNGを書き出して照合する
    #   ]
    #   引数: [self: テスト対象のCommandApiTestsケース]
    #   戻り値: [なし、CLIの編集・保存・再読込・出力が期待と異なればassertionで失敗する]
    # }
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

    # {
    #   責務: [test_invalid_command_inputs_do_not_mutate_document: 不正な編集・照会入力が文書状態を変更しないことを検証する]
    #   処理: [
    #     1: 初期文書の保存表現を記録する
    #     2: 範囲外描画・不正領域・不正な細部破棄・未定義レイヤー照会を実行する
    #     3: 各例外の後に文書状態が初期状態と一致することを確認する
    #   ]
    #   引数: [self: テスト対象のCommandApiTestsケース]
    #   戻り値: [なし、不正入力が文書を変更すればassertionで失敗する]
    # }
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
