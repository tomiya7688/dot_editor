"""Headless regressions for persistent CLI sessions and failed edits."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from pixel_cli import run_palette
from pixel_commands import PixelCommandAPI, save_project

ROOT = Path(__file__).resolve().parents[1] / "src"
RED = (255, 0, 0, 255)
BLUE = (0, 0, 255, 255)


# {
#   責務: [PaletteTests: CLIパレット対話での編集・失敗処理・ファイル保護を検証する]
#   フィールド: [
#     root: テスト用の一時ディレクトリ
#     project: 編集対象のプロジェクトファイル
#   ]
# }
class PaletteTests(unittest.TestCase):
    # {
    #   責務: [setUp: 各テスト用の一時領域とレイヤー付きプロジェクトを用意する]
    #   処理: [一時ディレクトリの後片付けを登録し、その中に空の編集プロジェクトを作成する]
    #   引数: [self: テスト対象のPaletteTestsケース]
    #   戻り値: [なし、rootとprojectを各テスト用に設定する]
    # }
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.project = self.root / "project.json"
        PixelCommandAPI.new(4, layered=True).save(self.project)

    # {
    #   責務: [session: CLIパレットを指定コマンド列で実行し、終了状態を確認する]
    #   処理: [
    #     1: 現在のテストプロジェクトを指定してCLIプロセスを起動する
    #     2: コマンド列を標準入力へ渡し、UTF-8出力を取得する
    #     3: 終了コードと例外痕跡を照合し、実行結果を返す
    #   ]
    #   引数: [self: テストケース、commands: CLIへ渡すコマンド列、code: 期待する終了コード]
    #   戻り値: [標準出力・標準エラー・終了コードを含むCompletedProcess]
    # }
    def session(self, commands: str, code: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(ROOT / "pixel_cli.py"), "palette",
             "--project", str(self.project)],
            input=commands, capture_output=True, text=True, encoding="utf-8",
            cwd=self.root, timeout=20,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        return result

    # {
    #   責務: [test_multiple_edits_inspect_and_export_in_one_process: 1回のCLI起動で複数編集・照会・画像出力が連続することを検証する]
    #   処理: [
    #     1: レイヤー追加・親画素編集・分割・子画素編集・照会・PNG出力を実行する
    #     2: CLI照会結果と保存後のプロジェクトから子画素・選択レイヤーを確認する
    #     3: 出力PNGの寸法と画素色を確認する
    #   ]
    #   引数: [self: テスト対象のPaletteTestsケース]
    #   戻り値: [なし、編集結果や出力内容が期待と異なればassertionで失敗する]
    # }
    def test_multiple_edits_inspect_and_export_in_one_process(self) -> None:
        output = self.root / "完成 image.png"
        result = self.session(
            'edit --add-layer "人物 layer"\n'
            'edit --paint 1 1 #FF0000\n'
            'edit --split 1 1\n'
            'edit --paint-child 1 1 1 0 #0000FF\n'
            'inspect --sample 1 1 --child 1 0\n'
            f'export --output "{output}" --size 8\nquit\n'
        )
        report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith("{")))
        self.assertEqual(report["sample"]["rgba"], list(BLUE))
        model = PixelCommandAPI.load(self.project)
        self.assertEqual(model.canvas.active_layer, "人物 layer")
        self.assertEqual(model.sample(1, 1, child=(1, 0)), BLUE)
        with Image.open(output) as image:
            self.assertEqual(image.size, (8, 8))
            self.assertEqual(image.getpixel((3, 2)), BLUE)

    # {
    #   責務: [test_failed_line_never_leaks_partial_edits_into_later_save: 失敗したコマンド行の途中変更が後続保存へ漏れないことを検証する]
    #   処理: [
    #     1: レイヤー追加と範囲外編集を含む失敗行の後に正常編集と照会を実行する
    #     2: CLIが失敗コードと範囲エラーを返すことを確認する
    #     3: 保存プロジェクトに失敗行のレイヤーがなく、正常編集だけが残ることを確認する
    #   ]
    #   引数: [self: テスト対象のPaletteTestsケース]
    #   戻り値: [なし、失敗行の一部が反映されていればassertionで失敗する]
    # }
    def test_failed_line_never_leaks_partial_edits_into_later_save(self) -> None:
        result = self.session(
            'edit --add-layer leaked --paint 99 0 #FF0000\n'
            'edit --paint 0 0 #0000FF\ninspect\n', code=2,
        )
        self.assertIn("outside", result.stderr)
        model = PixelCommandAPI.load(self.project)
        self.assertEqual(len(model.canvas.layers), 1)
        self.assertEqual(model.sample(0, 0), BLUE)

    # {
    #   責務: [test_help_errors_and_noops_do_not_rewrite_project: ヘルプ・不正入力・変更なし操作がプロジェクトを書き換えないことを検証する]
    #   処理: [
    #     1: ファイル内容と更新時刻を保存し、成功・失敗・構文エラー・変更なし操作を送る
    #     2: 変更なし表示と引用符エラーが報告されることを確認する
    #     3: 実行前後でファイル内容と更新時刻が一致することを確認する
    #   ]
    #   引数: [self: テスト対象のPaletteTestsケース]
    #   戻り値: [なし、出力やファイル状態が期待と異なればassertionで失敗する]
    # }
    def test_help_errors_and_noops_do_not_rewrite_project(self) -> None:
        before = (self.project.read_bytes(), self.project.stat().st_mtime_ns)
        result = self.session(
            'help\nhelp edit\nunknown\nedit --paint 0\n'
            'edit --paint 0 0 #GGGGGG\n"unfinished\n'
            'edit --erase 0 0\ninspect\nquit\n', code=2,
        )
        self.assertIn("no changes", result.stdout)
        self.assertIn("No closing quotation", result.stderr)
        self.assertEqual((self.project.read_bytes(), self.project.stat().st_mtime_ns), before)

    # {
    #   責務: [test_session_cannot_redirect_the_edit_project_or_output: 対話中の引数で編集対象や出力先を差し替えられないことを検証する]
    #   処理: [
    #     1: 保護対象の別ファイルと編集プロジェクトの内容を保存する
    #     2: コマンド内でproject指定・output指定を差し替える操作を試す
    #     3: 失敗終了し両ファイルの内容が保たれることを確認する
    #   ]
    #   引数: [self: テスト対象のPaletteTestsケース]
    #   戻り値: [なし、別ファイルや編集対象が変化すればassertionで失敗する]
    # }
    def test_session_cannot_redirect_the_edit_project_or_output(self) -> None:
        other = self.root / "other.json"
        other.write_text("keep", encoding="utf-8")
        before = self.project.read_bytes()
        self.session(
            f'edit --project "{other}" --paint 0 0 #FF0000\n'
            f'edit --output "{other}" --paint 0 0 #FF0000\nquit\n', code=2,
        )
        self.assertEqual(other.read_text(encoding="utf-8"), "keep")
        self.assertEqual(self.project.read_bytes(), before)

    # {
    #   責務: [test_failed_save_keeps_memory_and_file_ready_for_next_command: 保存失敗後も編集状態を保ち、次のコマンドを保存できることを検証する]
    #   処理: [
    #     1: 1回目だけ失敗する保存関数を用意し、2つの編集コマンドを与える
    #     2: 標準入力・保存関数・出力を差し替えて対話処理を実行する
    #     3: 失敗報告、メモリ上の編集結果、再読み込み後の保存内容を照合する
    #   ]
    #   引数: [self: テスト対象のPaletteTestsケース]
    #   戻り値: [なし、失敗後の状態や次の保存結果が期待と異なればassertionで失敗する]
    # }
    def test_failed_save_keeps_memory_and_file_ready_for_next_command(self) -> None:
        api = PixelCommandAPI.load(self.project)
        calls = 0

        # {
        #   責務: [fail_once: 最初の保存を失敗させ、次の保存では実際にファイルを書き込む]
        #   処理: [
        #     1: 呼び出し回数を増やす
        #     2: 初回のみ一時的なI/Oエラーを送出する
        #     3: 2回目以降は通常のプロジェクト保存を実行する
        #   ]
        #   引数: [canvas: 保存対象の描画データ、path: 保存先]
        #   戻り値: [なし、初回はOSErrorを送出し次回以降は保存する]
        # }
        def fail_once(canvas, path):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("simulated disk failure")
            save_project(canvas, path)

        stream = io.StringIO('edit --paint 0 0 #FF0000\nedit --paint 1 1 #0000FF\n')
        with patch("sys.stdin", stream), patch("pixel_cli.save_project", side_effect=fail_once):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(run_palette(api, self.project), 2)
        self.assertIn("simulated disk failure", errors.getvalue())
        self.assertEqual(api.sample(0, 0)[3], 0)
        self.assertEqual(api.sample(1, 1), BLUE)
        self.assertEqual(PixelCommandAPI.load(self.project).canvas.to_source(), api.canvas.to_source())

    # {
    #   責務: [test_windows_backslashes_and_quoted_spaces_survive_parsing: Windows形式のパスと空白を含む引用符付き引数が保持されることを検証する]
    #   処理: [
    #     1: バックスラッシュと空白を含む出力パスを対話入力へ渡す
    #     2: PNG出力処理を差し替えて引数を記録する
    #     3: Path化後の出力先と省略時解像度を照合する
    #   ]
    #   引数: [self: テスト対象のPaletteTestsケース]
    #   戻り値: [なし、解析された出力引数が期待と異なればassertionで失敗する]
    # }
    def test_windows_backslashes_and_quoted_spaces_survive_parsing(self) -> None:
        api = PixelCommandAPI.load(self.project)
        filename = r"C:\art work\test.png"
        with patch("sys.stdin", io.StringIO(f'export --output "{filename}"\n')):
            with patch.object(api, "export_png") as export, redirect_stdout(io.StringIO()):
                self.assertEqual(run_palette(api, self.project), 0)
        export.assert_called_once_with(Path(filename), None, output_resolution=None)


if __name__ == "__main__":
    unittest.main()
