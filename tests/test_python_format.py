"""Safety contracts of the scoped formatter; no formatter dependency is needed here."""

from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import format_python


# {
#   責務: [PythonFormatTests: 整形対象の限定と非書込CI契約を確認する]
#   フィールド: [なし]
# }
class PythonFormatTests(unittest.TestCase):
    # {
    #   責務: [test_explicit_scope: ディレクトリ・外部・生成物の選択を拒否する]
    #   処理: [1: 一時ソースを作る, 2: 有効パスの重複排除と範囲外の拒否を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_explicit_scope(self):
        # リポジトリ本体を書き換えず、空白を含むパスも対象にする。
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(format_python, "ROOT", Path(directory)),
        ):
            root = Path(directory)
            (root / "src").mkdir()
            source = root / "src" / "space name.py"
            source.write_text("value = 1\n", encoding="utf-8")
            self.assertEqual(
                format_python.validate_paths([str(source), str(source)]), ["src/space name.py"]
            )
            for name in ("src", "missing.py", "../outside.py", "pyproject.toml"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    format_python.validate_paths([name])
            (root / "tools").mkdir()
            (root / "tools/copied.py").write_text("pass\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                format_python.validate_paths(["tools/copied.py"])

    # {
    #   責務: [test_no_implicit_writes: 自動的な全体整形と差分整形を拒否する]
    #   処理: [1: 不正な引数を渡す, 2: Ruffが呼ばれないことを確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_no_implicit_writes(self):
        # 差分比較の入口はcheck専用であり、担当外dirtyの書換えに使わせない。
        with patch.object(format_python.subprocess, "call") as run:
            for arguments in ([], ["--base", "HEAD"], ["--check", "--base", "HEAD", "src/a.py"]):
                with self.subTest(arguments=arguments), self.assertRaises(SystemExit):
                    format_python.main(arguments)
            run.assert_not_called()

    # {
    #   責務: [test_check_preserves_exit_status: check指定・版固定設定・終了値を伝える]
    #   処理: [1: 検査対象を模擬する, 2: shellなしの引数と失敗の伝播を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_check_preserves_exit_status(self):
        # 非0を握り潰すとCI gateを迂回するため、Ruffの値をそのまま維持する。
        with (
            patch.object(format_python, "validate_paths", return_value=["src/a.py"]),
            patch.object(format_python.subprocess, "call", return_value=1) as run,
        ):
            self.assertEqual(format_python.main(["--check", "src/a.py"]), 1)
            command = run.call_args.args[0]
            self.assertIn("--check", command)
            self.assertEqual(command[-2:], ["--", "src/a.py"])
            self.assertIn(str(format_python.ROOT / "pyproject.toml"), command)
            self.assertNotIn("shell", run.call_args.kwargs)

    # {
    #   責務: [test_committed_diff: NUL区切り・削除除外・HEAD固定の比較を確認する]
    #   処理: [1: Git出力を模擬する, 2: Pythonだけの選択と安全な基準解決を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_committed_diff(self):
        # 空白や日本語を分割せず、削除済みや他言語をRuffへ渡さない。
        with (
            patch.object(
                format_python.subprocess,
                "check_output",
                side_effect=["abc\n", "src/日本 語.py\0src/skip.rs\0".encode()],
            ) as git,
            patch.object(format_python, "validate_paths", side_effect=lambda paths: paths),
        ):
            self.assertEqual(format_python.changed_python_paths("--bad"), ["src/日本 語.py"])
            self.assertIn("--end-of-options", git.call_args_list[0].args[0])
            self.assertIn("HEAD", git.call_args_list[1].args[0])
            self.assertIn("--diff-filter=ACMRT", git.call_args_list[1].args[0])

    # {
    #   責務: [test_empty_diff: 変更なしのとき全体整形へフォールバックしない]
    #   処理: [1: 空の差分を返す, 2: Ruffを呼ばず成功することを確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_empty_diff(self):
        # 空のファイル一覧でRuffを起動すると全体走査になるため、入口で止める。
        with (
            patch.object(format_python, "changed_python_paths", return_value=[]),
            patch.object(format_python.subprocess, "call") as run,
        ):
            self.assertEqual(format_python.main(["--check", "--base", "HEAD"]), 0)
            run.assert_not_called()

    # {
    #   責務: [test_git_failure: 基準取得の失敗をCI成功と扱わない]
    #   処理: [1: Git失敗を発生させる, 2: Ruffを呼ばず非0を返すことを確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: [なし]
    # }
    def test_git_failure(self):
        # リモート未取得や存在しない基準でも検査の省略成功にしない。
        with (
            patch.object(
                format_python,
                "changed_python_paths",
                side_effect=subprocess.CalledProcessError(128, "git"),
            ),
            patch.object(format_python.subprocess, "call") as run,
        ):
            self.assertEqual(format_python.main(["--check", "--base", "missing"]), 2)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
