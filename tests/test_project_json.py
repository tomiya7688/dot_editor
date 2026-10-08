"""Issue #7: reject ambiguous/malformed JSON without losing editor state."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from pixel_commands import PixelCommandAPI, load_project


# {
#   責務: [ProjectJsonTests: 不正・旧形式・現行形式JSONの読込と失敗時の状態保持を検証する]
#   フィールド: [path: 各テストが使用する一時プロジェクトファイル]
# }
class ProjectJsonTests(unittest.TestCase):
    # {
    #   責務: [setUp: 各テストで独立した一時プロジェクトの保存先を用意する]
    #   処理: [一時ディレクトリの後片付けを登録し、project.jsonのパスをselfに保持する]
    #   引数: [self: テスト対象のProjectJsonTestsケース]
    #   戻り値: [なし、pathに一時ファイルの場所を設定する]
    # }
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "project.json"

    # {
    #   責務: [test_duplicate_keys_at_any_depth_are_rejected: 最上位・入れ子・エスケープ表記を含む重複キーを拒否することを検証する]
    #   処理: [
    #     1: 異なる階層とUnicodeエスケープを使った重複キーJSONを順に保存する
    #     2: 読み込みが重複キーのValueErrorになることを確認する
    #     3: 拒否した入力ファイル自体は書き換えられないことを確認する
    #   ]
    #   引数: [self: テスト対象のProjectJsonTestsケース]
    #   戻り値: [なし、重複キーの処理やファイル保持が期待と異なればassertionで失敗する]
    # }
    def test_duplicate_keys_at_any_depth_are_rejected(self):
        for text in ('{"layers":[],"layers":[]}',
                     '{"extra":{"name":"first","name":"second"}}',
                     '{"name":1,"na\\u006de":2}'):
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                    load_project(self.path)
                self.assertEqual(self.path.read_text(encoding="utf-8"), text)

    # {
    #   責務: [test_nonstandard_numbers_are_rejected_even_in_unknown_fields: 未知フィールド内でもNaNと無限大を拒否することを検証する]
    #   処理: [各非標準数値をJSONへ設定し、読み込みが専用のValueErrorになることを確認する]
    #   引数: [self: テスト対象のProjectJsonTestsケース]
    #   戻り値: [なし、数値の拒否結果が期待と異なればassertionで失敗する]
    # }
    def test_nonstandard_numbers_are_rejected_even_in_unknown_fields(self):
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                self.path.write_text('{"extra":' + constant + '}', encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "non-standard JSON constant"):
                    load_project(self.path)

    # {
    #   責務: [test_deep_json_and_cli_failure_do_not_emit_traceback_or_write_output: 過度に深いJSONを読込とCLIの双方で拒否し、出力を作らないことを検証する]
    #   処理: [
    #     1: 入れ子上限を超えるJSONを保存し、API読込がValueErrorになることを確認する
    #     2: 同じ入力をCLIの画像書き出しに渡す
    #     3: 失敗コード・エラー文・Traceback不在・出力未作成を確認する
    #   ]
    #   引数: [self: テスト対象のProjectJsonTestsケース]
    #   戻り値: [なし、読込やCLIの失敗時動作が期待と異なればassertionで失敗する]
    # }
    def test_deep_json_and_cli_failure_do_not_emit_traceback_or_write_output(self):
        self.path.write_text("[" * 10000 + "0" + "]" * 10000, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "nesting is too deep"):
            load_project(self.path)
        output = self.path.with_suffix(".png")
        result = subprocess.run(
            [sys.executable, "-m", "pixel_cli", "export", "--project", str(self.path),
             "--output", str(output)], capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("nesting is too deep", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(output.exists())

    # {
    #   責務: [test_gui_failed_load_preserves_existing_document_and_history: GUIで不正JSONを開いても既存作品とUndo・Redo履歴を保つことを検証する]
    #   処理: [
    #     1: 編集済みCanvasと履歴を持つPixelEditorをGUI起動なしで用意する
    #     2: 重複キーと過深JSONを読み込ませ、既存Canvas・履歴の保持を確認する
    #     3: エラー通知回数・合成更新なし・既存Undo操作の有効性を確認する
    #   ]
    #   引数: [self: テスト対象のProjectJsonTestsケース]
    #   戻り値: [なし、読込失敗が既存状態へ影響すればassertionで失敗する]
    # }
    def test_gui_failed_load_preserves_existing_document_and_history(self):
        from dot_editor import PixelEditor

        editor = PixelEditor.__new__(PixelEditor)
        editor.backend = PixelCommandAPI.new(2, layered=True).canvas
        editor.backend.paint(0, 0, (255, 0, 0, 255))
        original = editor.backend
        before = original.to_source()
        editor.report_error = Mock()
        editor.refresh_composite = Mock()
        editor.history = ["existing undo"]
        editor.future = ["existing redo"]
        for text in ('{"a":1,"a":2}', "[" * 10000 + "0" + "]" * 10000):
            self.path.write_text(text, encoding="utf-8")
            with patch("dot_editor.filedialog.askopenfilename", return_value=str(self.path)):
                editor.load_project()
            self.assertIs(editor.backend, original)
            self.assertEqual(editor.backend.to_source(), before)
            self.assertEqual(editor.history, ["existing undo"])
            self.assertEqual(editor.future, ["existing redo"])
        self.assertEqual(editor.report_error.call_count, 2)
        editor.refresh_composite.assert_not_called()
        self.assertTrue(editor.backend.undo())
        self.assertEqual(editor.backend.sample(0, 0)[3], 0)

    # {
    #   責務: [test_valid_legacy_and_current_projects_still_load: 旧形式と現行形式の正常なプロジェクトを読み込めることを検証する]
    #   処理: [旧形式と現行Canvasから得たJSONを順に保存し、読込後の論理解像度を照合する]
    #   引数: [self: テスト対象のProjectJsonTestsケース]
    #   戻り値: [なし、どちらかの形式を読めないか解像度が異なればassertionで失敗する]
    # }
    def test_valid_legacy_and_current_projects_still_load(self):
        legacy = {"canvas_size": 2, "pixels": [[None, None], [None, None]]}
        for source in (legacy, PixelCommandAPI.new(2, layered=True).canvas.to_source()):
            self.path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(load_project(self.path).resolution, (2, 2))

    # {
    #   責務: [test_depth_limit_boundary: 128階層の上限を受け入れ、129階層を拒否する境界を検証する]
    #   処理: [
    #     1: ルートObjectと未知フィールドを含む合計128コンテナのJSONを読み込む
    #     2: さらにListを1階層追加したJSONを作り、上限超過エラーを確認する
    #   ]
    #   引数: [self: テスト対象のProjectJsonTestsケース]
    #   戻り値: [なし、上限境界の受け入れや拒否が異なればassertionで失敗する]
    # }
    def test_depth_limit_boundary(self):
        source = {"canvas_size": 2, "pixels": [[None, None], [None, None]]}
        # ルートObjectをコンテナ1個として数え、未知フィールドも受け入れる。
        source["extra"] = json.loads("[" * 127 + "0" + "]" * 127)
        self.path.write_text(json.dumps(source), encoding="utf-8")
        self.assertEqual(load_project(self.path).resolution, (2, 2))
        source["extra"] = [source["extra"]]
        self.path.write_text(json.dumps(source), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "maximum 128"):
            load_project(self.path)


if __name__ == "__main__":
    unittest.main()
