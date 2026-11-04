"""Check the task-brief, hotspot-index and PR-body helper scripts."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hotspots import PATTERNS, index_symbols
from pr_body import build_body, main as pr_main
from task_brief import find_designs, issue_numbers


# {
#   責務: [TaskToolTests: 作業用の補助スクリプトの回帰テストを保持する]
#   フィールド: [unittest.TestCaseの検証状態のみ]
# }
class TaskToolTests(unittest.TestCase):
    # {
    #   責務: [test_issue_ranges: 範囲と複数番号の展開を確認する]
    #   処理: [1: 範囲表記を展開する 2: 単独番号を拾う]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_issue_ranges(self):
        self.assertEqual(issue_numbers("#26 〜 #30"), {26, 27, 28, 29, 30})
        self.assertEqual(issue_numbers("#34 #39 #40"), {34, 39, 40})

    # {
    #   責務: [test_find_designs: 一覧から設計書の行を探せることを確認する]
    #   処理: [1: 表を用意する 2: 範囲内と範囲外の番号を引く]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_find_designs(self):
        listing = "| Issue | 内容 | 設計書 | 状態 |\n| --- | --- | --- | --- |\n| #26 〜 #30 | x | [k](k.md) | 設計案 |\n"
        self.assertEqual(find_designs(28, listing), [("[k](k.md)", "設計案")])
        self.assertEqual(find_designs(99, listing), [])

    # {
    #   責務: [test_hotspot_index: 記号索引が名前と行番号を返すことを確認する]
    #   処理: [1: 一時のPythonファイルを作る 2: 索引を取る]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_hotspot_index(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a.py"
            path.write_text("class A:\n    def f(self):\n        pass\n", encoding="utf-8")
            self.assertEqual(index_symbols(path, PATTERNS[".py"]), [(1, "A"), (2, "f")])

    # {
    #   責務: [test_pr_body: 生成した本文が検査を通り、不備は拒否されることを確認する]
    #   処理: [1: 正常な本文をLFで書く 2: 短すぎる欄を拒否する]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_pr_body(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "body.md"
            arguments = [
                "--issue",
                "Closes #75 (canvas input)",
                "--summary",
                "Move canvas input registration into init.",
                "--validation",
                "python -m unittest passed.",
                "--risks",
                "GUI only, no data format change.",
                "--handoff",
                "Claude branch fix/75, ready.",
                "--out",
                str(out),
            ]
            self.assertEqual(pr_main(arguments), 0)
            self.assertNotIn(b"\r", out.read_bytes())
            arguments[1] = "no reference"
            self.assertEqual(pr_main(arguments), 1)
        self.assertIn("## Handoff", build_body("#1", "s", "v", "r", "h"))
