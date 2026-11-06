"""Check the catalog renderer on a small catalog (no Rust binary needed)."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from render_command_catalog import escape_cell, quote_arg, render_markdown, validate_catalog


# {
#   責務: [sample_catalog: 検査用の小さなカタログを作る]
#   処理: [特殊文字を含む説明と、空白を含む使用例を1コマンドに持たせる]
#   引数: []
#   戻り値: [カタログのdict]
# }
def sample_catalog():
    command = {
        "id": "pixel.paint",
        "path": ["pixel", "paint"],
        "usage": "pixel paint <x> <y> <color>",
        "summary": "paint",
        "summary_ja": "塗る | 特殊`文字`",
        "effect": "edit",
        "requires_project": True,
        "positionals": [{"name": "x", "kind": "integer", "description_ja": "列"}],
        "options": [
            {
                "name": "--child",
                "aliases": ["-c"],
                "kind": "integer",
                "min_values": 2,
                "max_values": 2,
                "required": False,
                "description_ja": "子セル",
            }
        ],
        "side_effects": ["writes_project"],
        "examples": [
            {"argv": ["pixel-cli", "-p", "my art.json", "pixel", "paint"], "description_ja": "例"}
        ],
    }
    return {
        "schema_version": 1,
        "cli_implementation": "rust",
        "cli_version": "9.9.9",
        "entrypoint": "pixel-cli",
        "global_options": [],
        "commands": [command],
    }


# {
#   責務: [CatalogRendererTests: カタログの検証とMarkdown生成の回帰テストを保持する]
#   フィールド: [unittest.TestCaseの検証状態のみ]
# }
class CatalogRendererTests(unittest.TestCase):
    # {
    #   責務: [test_render_is_stable_and_escaped: 出力が安定し、表を壊す文字が処理されることを検証する]
    #   処理: [
    #     1: 同じ入力から2回生成して一致し、LFのみであることを確認する
    #     2: 縦線・バッククォートのエスケープと、空白を含む引数の引用を確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_render_is_stable_and_escaped(self):
        catalog = sample_catalog()
        text = render_markdown(catalog)
        self.assertEqual(text, render_markdown(sample_catalog()))
        self.assertNotIn("\r", text)
        self.assertIn("塗る \\| 特殊\\`文字\\`", text)
        self.assertIn('"my art.json"', text)
        self.assertEqual(escape_cell("a|b\nc"), "a\\|b c")
        self.assertEqual(quote_arg("#FF8800"), '"#FF8800"')
        self.assertEqual(quote_arg("art.json"), "art.json")

    # {
    #   責務: [test_validate_rejects_bad_catalogs: 不正なカタログを拒否することを検証する]
    #   処理: [
    #     1: 未知の版、重複ID、日本語説明の空、必須キーの欠落をそれぞれ拒否することを確認する
    #   ]
    #   引数: [self: テストケース]
    #   戻り値: [なし、不一致なら失敗]
    # }
    def test_validate_rejects_bad_catalogs(self):
        validate_catalog(sample_catalog())
        catalog = sample_catalog()
        catalog["schema_version"] = 2
        with self.assertRaises(SystemExit):
            validate_catalog(catalog)
        catalog = sample_catalog()
        catalog["commands"].append(dict(catalog["commands"][0]))
        with self.assertRaises(SystemExit):
            validate_catalog(catalog)
        catalog = sample_catalog()
        catalog["commands"][0]["summary_ja"] = " "
        with self.assertRaises(SystemExit):
            validate_catalog(catalog)
        catalog = sample_catalog()
        del catalog["commands"][0]["examples"]
        with self.assertRaises(SystemExit):
            validate_catalog(catalog)


if __name__ == "__main__":
    unittest.main()
