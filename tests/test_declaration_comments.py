"""Regression coverage for the repository declaration-comment gate."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_declaration_comments import audit_text, changed_paths

FUNCTION = """{
  責務: [sample: 色を読み出す]
  処理: [1: 画素を参照する]
  引数: []
  戻り値: [RGBA]
}"""
TYPE = """{
  責務: [State: 保存状態を保持する]
  フィールド: [color: 保存色]
}"""


# {
#   責務: [documented: 検査用の構造化コメント付きソースを作る]
#   処理: [
#     1: 各行へ言語のコメント記号を付ける
#     2: 末尾へ宣言を結合する
#   ]
#   引数: [
#     block: コメント本文またはNone
#     declaration: 結合する宣言ソース
#     prefix: 言語のコメント記号
#   ]
#   戻り値: [fixtureのソース文字列]
# }
def documented(block, declaration, prefix):
    return "\n".join(prefix + " " + line for line in block.splitlines()) + "\n" + declaration


# {
#   責務: [DeclarationCommentTests: コメント検査器の正常・異常系を回帰検証する]
#   フィールド: [unittest.TestCaseの検証状態を継承し、独自の共有フィールドは持たない]
# }
class DeclarationCommentTests(unittest.TestCase):
    # {
    #   責務: [test_python_functions_and_decorated_classes: Python関数とデコレータ付きクラスの検出を回帰検証する]
    #   処理: [
    #     1: 検査用ソースを用意する
    #     2: Python関数とデコレータ付きクラスの検出をassertで確認する
    #   ]
    #   引数: [
    #     self: 独立したfixtureを持つテストケース
    #   ]
    #   戻り値: [なし、不一致ならテスト失敗]
    # }
    def test_python_functions_and_decorated_classes(self):
        source = documented(TYPE, "@decorator\nclass State:\n    pass\n", "#")
        source += documented(FUNCTION, "async def sample():\n    return 1\n", "#")
        self.assertEqual(audit_text(source, ".py"), (2, []))

    # {
    #   責務: [test_rust_attributes_and_methods: Rustの複数行属性前のコメント認識を回帰検証する]
    #   処理: [
    #     1: 検査用ソースを用意する
    #     2: Rustの複数行属性前のコメント認識をassertで確認する
    #   ]
    #   引数: [
    #     self: 独立したfixtureを持つテストケース
    #   ]
    #   戻り値: [なし、不一致ならテスト失敗]
    # }
    def test_rust_attributes_and_methods(self):
        source = documented(TYPE, "#[derive(\nClone, Copy\n)]\npub struct State;\n", "///")
        source += documented(FUNCTION, "#[test]\nfn sample() {}\n", "///")
        self.assertEqual(audit_text(source, ".rs"), (2, []))

    # {
    #   責務: [test_missing_comments_fail_for_each_declaration: 宣言ごとのコメント欠落検出を回帰検証する]
    #   処理: [
    #     1: 検査用ソースを用意する
    #     2: 宣言ごとのコメント欠落検出をassertで確認する
    #   ]
    #   引数: [
    #     self: 独立したfixtureを持つテストケース
    #   ]
    #   戻り値: [なし、不一致ならテスト失敗]
    # }
    def test_missing_comments_fail_for_each_declaration(self):
        for suffix, source in ((".rs", "struct State;\nfn sample() {}"),
                               (".py", "class State:\n    def sample(self):\n        pass")):
            with self.subTest(suffix=suffix):
                count, errors = audit_text(source, suffix)
                self.assertEqual(count, 2)
                self.assertEqual(len(errors), 2)

    # {
    #   責務: [test_body_comments_and_docstrings_do_not_document_declarations: 内部コメント・docstringの除外を回帰検証する]
    #   処理: [
    #     1: 検査用ソースを用意する
    #     2: 内部コメント・docstringの除外をassertで確認する
    #   ]
    #   引数: [
    #     self: 独立したfixtureを持つテストケース
    #   ]
    #   戻り値: [なし、不一致ならテスト失敗]
    # }
    def test_body_comments_and_docstrings_do_not_document_declarations(self):
        source = 'def sample():\n    """ordinary documentation"""\n'
        source += "\n".join("    # " + line for line in FUNCTION.splitlines()) + "\n    pass\n"
        self.assertEqual(len(audit_text(source, ".py")[1]), 1)

    # {
    #   責務: [test_missing_duplicate_and_empty_fields_fail: 必須項目の欠落・重複・空説明の拒否を回帰検証する]
    #   処理: [
    #     1: 検査用ソースを用意する
    #     2: 必須項目の欠落・重複・空説明の拒否をassertで確認する
    #   ]
    #   引数: [
    #     self: 独立したfixtureを持つテストケース
    #   ]
    #   戻り値: [なし、不一致ならテスト失敗]
    # }
    def test_missing_duplicate_and_empty_fields_fail(self):
        for block in (FUNCTION.replace("  戻り値: [RGBA]\n", ""),
                      FUNCTION.replace("[RGBA]", "[]"),
                      FUNCTION.replace("  戻り値: [RGBA]", "  戻り値: [RGBA]\n  戻り値: [RGBA]")):
            with self.subTest(block=block):
                source = documented(block, "fn sample() {}", "///")
                self.assertTrue(audit_text(source, ".rs")[1])

    # {
    #   責務: [test_unbalanced_or_detached_comments_fail: 括弧不一致と離れたコメントの拒否を回帰検証する]
    #   処理: [
    #     1: 検査用ソースを用意する
    #     2: 括弧不一致と離れたコメントの拒否をassertで確認する
    #   ]
    #   引数: [
    #     self: 独立したfixtureを持つテストケース
    #   ]
    #   戻り値: [なし、不一致ならテスト失敗]
    # }
    def test_unbalanced_or_detached_comments_fail(self):
        for block, gap in ((FUNCTION.replace("[RGBA]", "[RGBA"), ""), (FUNCTION, "\n")):
            source = documented(block, gap + "fn sample() {}", "///")
            self.assertTrue(audit_text(source, ".rs")[1])

    # {
    #   責務: [test_rust_literals_and_nested_comments_are_not_declarations: Rustリテラルと入れ子コメント内の偽宣言除外を回帰検証する]
    #   処理: [
    #     1: 検査用ソースを用意する
    #     2: Rustリテラルと入れ子コメント内の偽宣言除外をassertで確認する
    #   ]
    #   引数: [
    #     self: 独立したfixtureを持つテストケース
    #   ]
    #   戻り値: [なし、不一致ならテスト失敗]
    # }
    def test_rust_literals_and_nested_comments_are_not_declarations(self):
        source = '''const TEXT: &str = r###"\nfn fake() {}\nstruct Fake;\n"###;
const QUOTED: &str = "\\\"\nfn fake() {}";
/* outer /* nested */
fn fake() {}
*/
// fn fake() {}
'''
        self.assertEqual(audit_text(source, ".rs"), (0, []))

    # {
    #   責務: [test_python_strings_are_not_declarations: Python文字列内の偽宣言除外を回帰検証する]
    #   処理: [
    #     1: 検査用ソースを用意する
    #     2: Python文字列内の偽宣言除外をassertで確認する
    #   ]
    #   引数: [
    #     self: 独立したfixtureを持つテストケース
    #   ]
    #   戻り値: [なし、不一致ならテスト失敗]
    # }
    def test_python_strings_are_not_declarations(self):
        self.assertEqual(audit_text('TEXT = """\ndef fake():\n    pass\n"""', ".py"), (0, []))

    # {
    #   責務: [test_nested_python_function_requires_its_own_comment: 内部Python関数の独立コメント要求を回帰検証する]
    #   処理: [
    #     1: 検査用ソースを用意する
    #     2: 内部Python関数の独立コメント要求をassertで確認する
    #   ]
    #   引数: [
    #     self: 独立したfixtureを持つテストケース
    #   ]
    #   戻り値: [なし、不一致ならテスト失敗]
    # }
    def test_nested_python_function_requires_its_own_comment(self):
        source = documented(FUNCTION, "def sample():\n    def inner():\n        pass\n", "#")
        count, errors = audit_text(source, ".py")
        self.assertEqual(count, 2)
        self.assertEqual(len(errors), 1)
        self.assertIn("inner", errors[0])

    # {
    #   責務: [test_changed_sources_are_selected_without_legacy_exemptions: 既存ファイルを免除しない変更対象の選択を回帰検証する]
    #   処理: [
    #     1: 検査用ソースを用意する
    #     2: 既存ファイルを免除しない変更対象の選択をassertで確認する
    #   ]
    #   引数: [
    #     self: 独立したfixtureを持つテストケース
    #   ]
    #   戻り値: [なし、不一致ならテスト失敗]
    # }
    def test_changed_sources_are_selected_without_legacy_exemptions(self):
        result = type("Result", (), {"stdout": b"src/pixel_backend.py\0README.md\0scripts/no_file.py\0"})()
        with patch("check_declaration_comments.subprocess.run", return_value=result) as run:
            paths = changed_paths("HEAD~1")
        self.assertEqual([path.name for path in paths], ["pixel_backend.py"])
        self.assertIn("HEAD~1", run.call_args.args[0])
        self.assertIn("HEAD", run.call_args.args[0])

    # {
    #   責務: [test_nested_field_does_not_replace_a_required_top_level_field: 入れ子項目による必須項目の代用拒否を回帰検証する]
    #   処理: [
    #     1: 検査用ソースを用意する
    #     2: 入れ子項目による必須項目の代用拒否をassertで確認する
    #   ]
    #   引数: [
    #     self: 独立したfixtureを持つテストケース
    #   ]
    #   戻り値: [なし、不一致ならテスト失敗]
    # }
    def test_nested_field_does_not_replace_a_required_top_level_field(self):
        block = FUNCTION.replace("  戻り値: [RGBA]\n", "").replace(
            "  処理: [1: 画素を参照する]", "  処理: [\n    戻り値: [RGBA]\n  ]")
        self.assertTrue(audit_text(documented(block, "fn sample() {}", "///"), ".rs")[1])

    # {
    #   責務: [test_quoted_keys_and_brackets_in_strings_are_accepted: 引用キーと文字列内の括弧の許可を回帰検証する]
    #   処理: [
    #     1: 検査用ソースを用意する
    #     2: 引用キーと文字列内の括弧の許可をassertで確認する
    #   ]
    #   引数: [
    #     self: 独立したfixtureを持つテストケース
    #   ]
    #   戻り値: [なし、不一致ならテスト失敗]
    # }
    def test_quoted_keys_and_brackets_in_strings_are_accepted(self):
        block = FUNCTION.replace("責務:", '"責務":').replace("[RGBA]", '["[RGBA}]"]')
        self.assertEqual(audit_text(documented(block, "fn sample() {}", "///"), ".rs"), (1, []))

    # {
    #   責務: [test_inline_rust_method_is_not_silently_skipped: 同一行のRustメソッドの欠落検出を回帰検証する]
    #   処理: [
    #     1: 検査用ソースを用意する
    #     2: 同一行のRustメソッドの欠落検出をassertで確認する
    #   ]
    #   引数: [
    #     self: 独立したfixtureを持つテストケース
    #   ]
    #   戻り値: [なし、不一致ならテスト失敗]
    # }
    def test_inline_rust_method_is_not_silently_skipped(self):
        count, errors = audit_text("impl State { fn sample() {} }", ".rs")
        self.assertEqual(count, 1)
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
