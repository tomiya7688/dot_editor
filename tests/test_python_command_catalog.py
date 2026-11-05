"""Check that the Python CLI catalog matches the real argparse parser and `--help`."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from command_catalog import OPTION_JA, SUMMARY_JA, build_catalog, cli_version
from pixel_cli import build_parser
from render_command_catalog import render_markdown, validate_catalog


# {
#   責務: [subcommands: 実際のパーサーのサブコマンドの辞書を返す]
#   処理: [argparseのサブパーサー動作を探して、名前とパーサーの対応を返す]
#   引数: []
#   戻り値: [サブコマンド名からパーサーへの辞書]
# }
def subcommands():
    parser = build_parser()
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return dict(action.choices)


# {
#   責務: [PythonCatalogTests: Python CLIのカタログと実パーサーの一致を検証する]
#   フィールド: [unittest.TestCaseの検証状態のみ]
# }
class PythonCatalogTests(unittest.TestCase):
    # {
    #   責務: [test_catalog_covers_every_command_and_option: 全サブコマンドと全オプションが過不足なく載ることを検証する]
    #   処理: [
    #     1: スキーマの必須項目と一意性を検査する
    #     2: コマンド名の集合がパーサーと日本語説明表の両方に一致することを確認する
    #     3: 各コマンドのオプション名と別名がパーサーの定義と一致することを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_catalog_covers_every_command_and_option(self):
        catalog = build_catalog()
        validate_catalog(catalog)
        self.assertEqual(catalog["cli_implementation"], "python")
        real = subcommands()
        self.assertEqual([c["id"] for c in catalog["commands"]], list(real))
        self.assertEqual(set(SUMMARY_JA), set(real))
        used = set()
        for command in catalog["commands"]:
            parser = real[command["id"]]
            expected = {
                tuple(a.option_strings)
                for a in parser._actions
                if a.option_strings and not isinstance(a, argparse._HelpAction)
            }
            listed = {(option["name"], *option["aliases"]) for option in command["options"]}
            self.assertEqual(listed, expected, command["id"])
            used.update(option["name"] for option in command["options"])
            for option in command["options"]:
                self.assertLessEqual(option["min_values"], option["max_values"] or 10**6)
        self.assertEqual(used, set(OPTION_JA))

    # {
    #   責務: [test_catalog_matches_help_and_is_stable: 個別ヘルプと一致し、2回の生成と版が安定していることを検証する]
    #   処理: [
    #     1: 各コマンドを--helpで実行し、カタログの全オプション名が出力に含まれることを確認する
    #     2: 2回の生成とMarkdownが一致し、版がpyproject.tomlの版と一致することを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_catalog_matches_help_and_is_stable(self):
        catalog = build_catalog()
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
        for command in catalog["commands"]:
            run = subprocess.run(
                [sys.executable, "-m", "pixel_cli", command["id"], "--help"],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            self.assertEqual(run.returncode, 0, command["id"])
            for option in command["options"]:
                self.assertIn(option["name"], run.stdout, command["id"])
        self.assertEqual(catalog, build_catalog())
        self.assertEqual(render_markdown(catalog), render_markdown(build_catalog()))
        pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
            encoding="utf-8"
        )
        self.assertIn(f'version = "{cli_version()}"', pyproject)

    # {
    #   責務: [test_catalog_does_not_depend_on_how_it_is_run: 実行方法が違っても同じ内容になることを検証する]
    #   処理: [
    #     1: python -m command_catalog の出力と、同じプロセス内で作った内容が一致することを確認する
    #     2: 実行ファイル名（python.exeや-c）が内容に混ざらないことを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_catalog_does_not_depend_on_how_it_is_run(self):
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
        run = subprocess.run(
            [sys.executable, "-m", "command_catalog"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            check=False,
        )
        self.assertEqual(run.returncode, 0)
        self.assertEqual(json.loads(run.stdout), build_catalog())
        for command in build_catalog()["commands"]:
            for field in (command["usage"], command["summary"]):
                self.assertNotIn("python", field)
                self.assertNotIn(".exe", field)
                self.assertNotIn("-c ", field)


if __name__ == "__main__":
    unittest.main()
