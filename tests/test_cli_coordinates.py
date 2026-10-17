"""CLI文字列と共有APIの整数座標契約の境界を検証する。"""
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pixel_cli
from pixel_backend import PixelCanvas
from pixel_commands import PixelCommandAPI


# {
#   責務: [CliCoordinateTests: 色付きCLI操作の整数変換と不正入力時の保存保護を検証する]
#   フィールド: []
# }
class CliCoordinateTests(unittest.TestCase):
    # {
    #   責務: [test_color_operations_pass_integer_coordinates: 単発・対話構文の色付き操作がAPIへ整数を渡すことを確認する]
    #   処理: [
    #     1: 親描画・子描画・塗りつぶしのCLI文字列を両構文で解析する
    #     2: API呼び出しを捕捉し親座標・子座標・色と実際の型を確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不正な座標型や転送先ならテスト失敗]
    # }
    def test_color_operations_pass_integer_coordinates(self):
        operations = (
            ("--paint", ["2", "1"], "paint", None),
            ("--paint-child", ["2", "1", "1", "0"], "paint", (1, 0)),
            ("--fill", ["2", "1"], "fill", None),
        )
        # APIを模擬することで、旧APIの暗黙変換に成功を依存させない。
        for session in (False, True):
            for option, coordinates, method, child in operations:
                with self.subTest(session=session, option=option):
                    tokens = ["edit"]
                    if not session:
                        tokens += ["--project", "unused.json"]
                    tokens += [option, *coordinates, "#123456"]
                    args = pixel_cli.build_parser(session=session).parse_args(tokens)
                    with patch.object(PixelCommandAPI, method, return_value=1) as operation:
                        self.assertTrue(pixel_cli.edit_project(PixelCanvas(4), args))
                    operation.assert_called_once()
                    self.assertEqual(operation.call_args.args, (2, 1, (18, 52, 86, 255)))
                    for coordinate in operation.call_args.args[:2]:
                        self.assertIs(type(coordinate), int)
                    if child is not None:
                        self.assertEqual(operation.call_args.kwargs["child"], child)
                        for coordinate in operation.call_args.kwargs["child"]:
                            self.assertIs(type(coordinate), int)

    # {
    #   責務: [test_invalid_coordinates_leave_saved_project_unchanged: 色付き操作の不正座標で元JSONと別出力先を変更しないことを確認する]
    #   処理: [
    #     1: 各親・子座標へ小数や非数値を入れた単発CLIを実行する
    #     2: 終了値2と診断を確認し元JSON不変・出力先未作成を確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不正入力が保存された場合はテスト失敗]
    # }
    def test_invalid_coordinates_leave_saved_project_unchanged(self):
        # 作品は各失敗操作の前後でバイト比較し、保存経路まで確認する。
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "original.json"
            output = Path(directory) / "copy.json"
            PixelCommandAPI.new(4).save(project)
            original = project.read_bytes()
            for option, count in (("--paint", 2), ("--paint-child", 4), ("--fill", 2)):
                for index in range(count):
                    for invalid in ("1.5", "not-an-integer"):
                        with self.subTest(option=option, index=index, invalid=invalid):
                            coordinates = ["0"] * count
                            coordinates[index] = invalid
                            errors = io.StringIO()
                            with redirect_stderr(errors), self.assertRaises(SystemExit) as failure:
                                pixel_cli.main([
                                    "edit", "--project", str(project), "--output", str(output),
                                    option, *coordinates, "#123456",
                                ])
                            self.assertEqual(failure.exception.code, 2)
                            self.assertIn("error:", errors.getvalue())
                            self.assertEqual(project.read_bytes(), original)
                            self.assertFalse(output.exists())

    # {
    #   責務: [test_palette_recovers_after_invalid_coordinate: 対話で不正な子座標を拒否した後も正常な親描画を保存できることを確認する]
    #   処理: [
    #     1: 子座標が不正な編集行と正常な描画行を対話入力へ渡す
    #     2: 累積エラー終了値と保存後の正常画素・失敗対象の不変を確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、失敗行の影響や正常行の欠落があればテスト失敗]
    # }
    def test_palette_recovers_after_invalid_coordinate(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "session.json"
            api = PixelCommandAPI.new(4)
            api.save(project)
            before = api.sample(0, 0)
            # 失敗行で加えた分割は、後続の保存へ混入させない。
            commands = io.StringIO(
                "edit --split 0 0 --paint-child 0 0 0.5 0 #FF0000\n"
                "edit --paint 2 1 #123456\nquit\n"
            )
            with (
                patch("sys.stdin", commands),
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()),
            ):
                status = pixel_cli.run_palette(api, project)
            self.assertEqual(status, 2)
            restored = PixelCommandAPI.load(project)
            self.assertEqual(restored.sample(2, 1), (18, 52, 86, 255))
            self.assertEqual(restored.sample(0, 0), before)
            self.assertFalse(restored.is_split(0, 0))
